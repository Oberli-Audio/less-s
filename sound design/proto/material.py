#!/usr/bin/env python3
"""Test material for Less S - synthetic, seeded, labelled.

The brief's test material is "a sibilant female and male vocal phrase plus synthetic s
and f bursts". Real vocal recordings live in OneDrive, not in git (.gitignore), and the
listening checkpoint is where they belong. Every *number* in G2 and G3 therefore comes
from synthetic material built here, because it is seeded (rule 8), reproducible on any
machine, and - the point for a de-esser - **labelled**: the script knows where every
sibilant is, so "13 esses give 13 events, none on breaths" is a test and not an opinion.

    from material import phrase, burst_pair
    x, labels = phrase(48000.0)

Everything returns float64 (n, 2) and dBFS levels as named. Nothing here is part of the
product; it is design reference material (CLAUDE.md, `sound design/`).
"""
import numpy as np

# One phrase: alternating voiced syllables and sibilants, two breaths, 13 esses.
# Times in seconds, so the material is rate-independent (rule 12 applies to test
# material too: a burst specified in samples would move when the rate changes).
ESS_COUNT = 13


def _env(n, fs, attack_s, release_s):
    """A burst envelope: raised-cosine attack, exponential release, both in seconds."""
    a = max(1, int(round(attack_s * fs)))
    e = np.ones(n)
    a = min(a, n)
    e[:a] = 0.5 - 0.5 * np.cos(np.pi * np.arange(a) / a)
    tau = max(release_s, 1e-6)
    t = np.arange(n) / fs
    e *= np.exp(-np.maximum(0.0, t - (n / fs - 3 * tau)) / tau)
    return e


def _band_noise(n, fs, f0, bw_oct, rng):
    """Band-limited noise by shaping white noise in the frequency domain (no filter state)."""
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / fs)
    lo, hi = f0 * 2 ** (-bw_oct / 2), f0 * 2 ** (bw_oct / 2)
    # a smooth log-Gaussian skirt: no brick wall, so the material has no artificial edges
    with np.errstate(divide="ignore"):
        logf = np.log2(np.maximum(f, 1.0) / f0)
    sigma = bw_oct / 2.355                      # bw_oct as the full width at half maximum
    X *= np.exp(-0.5 * (logf / sigma) ** 2)
    X[f < 20.0] = 0.0
    y = np.fft.irfft(X, n)
    p = np.max(np.abs(y))
    return y / p if p > 0 else y


def _voiced(n, fs, f0, rng):
    """A vowel surrogate: a harmonic series through three formants, slight vibrato."""
    t = np.arange(n) / fs
    f = f0 * (1.0 + 0.01 * np.sin(2 * np.pi * 5.0 * t + rng.uniform(0, 6.28)))
    phase = 2 * np.pi * np.cumsum(f) / fs
    y = np.zeros(n)
    for h in range(1, 41):
        if f0 * h > fs / 2 * 0.95:
            break
        y += np.sin(h * phase + rng.uniform(0, 6.28)) / h ** 1.1
    # three formants (a loose /a/), as resonant gains on the harmonic sum
    Y = np.fft.rfft(y)
    fr = np.fft.rfftfreq(n, 1.0 / fs)
    g = np.ones_like(fr) * 0.05
    for fc, bw, amp in ((700.0, 120.0, 1.0), (1200.0, 180.0, 0.6), (2600.0, 300.0, 0.25)):
        g += amp / (1.0 + ((fr - fc) / bw) ** 2)
    g *= 1.0 / (1.0 + (fr / 6000.0) ** 2)        # the voice's own roll-off: no energy where the esses go
    y = np.fft.irfft(Y * g, n)
    p = np.max(np.abs(y))
    return y / p if p > 0 else y


def _place(dst, start_s, fs, seg, gain):
    i = int(round(start_s * fs))
    if i < 0 or i + len(seg) > len(dst):
        raise AssertionError(
            "the material does not fit: a segment at %.3f s needs %.3f s but the buffer is %.3f s. "
            "The labels would name audio that is not there." % (start_s, (i + len(seg)) / fs, len(dst) / fs))
    dst[i:i + len(seg)] += gain * seg


def phrase(fs, seed=1, voice="female", stereo=True):
    """A labelled phrase of about 8 s (the grid decides; the buffer is sized to fit it).
    Returns (x (n,2), labels).

    labels: {"ess": [(t0, t1, centre_hz)], "breath": [(t0, t1)], "voiced": [(t0, t1)],
             "f": [(t0, t1)]}
    The esses sit at `ess_centre_hz` (7 kHz for the female surrogate, 5.6 kHz for the
    male one, the band the brief expects Learn to find); the two breaths and the three
    /f/ bursts are the negatives the ess map must *not* fire on.
    """
    rng = np.random.default_rng(seed)
    labels = {"ess": [], "breath": [], "voiced": [], "f": []}

    ess_hz = 7000.0 if voice == "female" else 5600.0
    f0 = 220.0 if voice == "female" else 115.0

    # The grid is planned first and the buffer sized from it. A fixed 6 s buffer silently
    # dropped the last three esses while still labelling them, so the ess-map test asked
    # for 13 events from audio that held 10 (docs/failures.md); `_place` now also refuses
    # anything that would fall outside.
    plan = []
    t = 0.30
    for k in range(ESS_COUNT):
        vow_len = 0.22 + 0.10 * rng.random()
        plan.append(("voiced", t, vow_len, f0 * (0.9 + 0.2 * rng.random()), -12.0))
        t += vow_len
        ess_len = 0.07 + 0.05 * rng.random()
        # the esses are not all the same: 13 dB of spread, so Range and Threshold have work to do
        plan.append(("ess", t, ess_len, ess_hz, -14.0 + rng.uniform(-6.0, 7.0)))
        t += ess_len + 0.06 + 0.08 * rng.random()
        if k in (4, 9):                                    # a breath between phrases
            plan.append(("breath", t, 0.30, 1500.0, -34.0))
            t += 0.30 + 0.10
        if k in (2, 6, 11):                                # an /f/: 4 kHz, 10 dB under the esses
            plan.append(("f", t, 0.08, 4000.0, -24.0))
            t += 0.08 + 0.07

    n = int(round((t + 0.40) * fs))
    mono = np.zeros(n)
    for kind, start, length, hz, level in plan:
        seg = int(round(length * fs))
        if kind == "voiced":
            body = _voiced(seg, fs, hz, rng) * _env(seg, fs, 0.02, 0.05)
            labels["voiced"].append((start, start + length))
        elif kind == "ess":
            body = _band_noise(seg, fs, hz, 1.1, rng) * _env(seg, fs, 0.004, 0.02)
            labels["ess"].append((start, start + length, hz))
        elif kind == "breath":
            body = _band_noise(seg, fs, hz, 4.0, rng) * _env(seg, fs, 0.08, 0.10)
            labels["breath"].append((start, start + length))
        else:
            # 1.0 octave, the same /f/ as `burst_pair` uses. At the 1.6 octaves this had
            # first, the burst's upper skirt reached 5.9 kHz - inside the detection band -
            # and the loudest of the three opened an ess-map event of 1.05 dB, so the two
            # generators disagreed about what "an /f/ at 4 kHz" is while the brief's
            # selectivity target is written against one /f/.
            body = _band_noise(seg, fs, hz, 1.0, rng) * _env(seg, fs, 0.006, 0.02)
            labels["f"].append((start, start + length))
        _place(mono, start, fs, body, 10 ** (level / 20))

    if stereo:
        # the same voice in both channels with a touch of decorrelation, so the Stereo
        # modes have something to tell apart; no delay, so mono-sum stays honest
        x = np.stack([mono, mono * 0.92 + 0.08 * np.roll(mono, 7)], axis=1)
    else:
        x = mono[:, None]
    return x, labels


def burst_pair(fs, s_hz=7000.0, f_hz=4000.0, s_dbfs=-14.0, gap_db=10.0, seed=1):
    """The selectivity signal of the brief: an "s" burst, then an "f" `gap_db` quieter.

    Returns (x (n,2), labels) with labels["s"] and labels["f"] as (t0, t1).
    """
    rng = np.random.default_rng(seed)
    seconds = 1.6
    n = int(round(seconds * fs))
    mono = np.zeros(n)
    length = 0.20
    seg = int(round(length * fs))
    s = _band_noise(seg, fs, s_hz, 1.0, rng) * _env(seg, fs, 0.004, 0.03)
    ff = _band_noise(seg, fs, f_hz, 1.0, rng) * _env(seg, fs, 0.004, 0.03)
    _place(mono, 0.30, fs, s, 10 ** (s_dbfs / 20))
    _place(mono, 1.00, fs, ff, 10 ** ((s_dbfs - gap_db) / 20))
    x = np.stack([mono, mono], axis=1)
    return x, {"s": (0.30, 0.30 + length), "f": (1.00, 1.00 + length)}


def white_noise(fs, dbfs=-20.0, seconds=2.0, seed=1):
    """Full-band noise: the signal for measuring a filter's own response, where a band
    burst has nothing to measure with outside its own band."""
    rng = np.random.default_rng(seed)
    n = int(round(seconds * fs))
    mono = rng.standard_normal(n)
    mono *= 10 ** (dbfs / 20) / max(float(np.std(mono)), 1e-30)
    return np.stack([mono, mono], axis=1), {}


def tone_burst(fs, hz=7000.0, dbfs=-14.0, on_s=0.5, off_s=0.5, seconds=2.0):
    """A gated sine in the band: the ballistics signal (attack and release 10-90 %)."""
    n = int(round(seconds * fs))
    t = np.arange(n) / fs
    y = np.sin(2 * np.pi * hz * t) * 10 ** (dbfs / 20)
    gate = ((t >= off_s) & (t < off_s + on_s)).astype(float)
    y *= gate
    return np.stack([y, y], axis=1), {"on": (off_s, off_s + on_s)}


def segment_rms_db(x, fs, t0, t1):
    i, j = int(round(t0 * fs)), int(round(t1 * fs))
    seg = np.asarray(x)[i:j]
    if seg.size == 0:
        return -400.0
    return 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-300)
