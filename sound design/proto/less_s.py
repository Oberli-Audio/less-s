#!/usr/bin/env python3
"""Less S - the G2 prototype, in the structure the C++ port will use.

sound-design-bob G2: "in the port's structure (F.8): Faust for sound, numpy for
analysis". Faust is not installed in the container this was built in, and F.15.1 allows
a numpy model for an effect with an STFT stage, so this file *is* the prototype and the
G5 null reference. It is written to be ported by structure, class for class, with every
constant named and commented where it was chosen:

    Svf            TPT state-variable filter, unity-peak band-pass  (rule 6)
    OnePole        one-pole smoother, tau in seconds                (rule 12)
    LevelFollower  the peak and mean-square level estimate per channel
    GainComputer   soft knee, ratio, Range ceiling, in dB           (E.1 log domain)
    Ballistics     attack/release on the control signal in dB
    Stft           Hann WOLA, window in seconds, exact reconstruction
    Learn          the one-shot band finder, off the audio thread
    LessS          the processor: prepare / reset / set_params / process

Deliberate properties, each with the test that holds it (tools/measure/):
  * Range 0 nulls against the input in every mode (brief must_do).
  * Nothing is specified in samples (rule 12): every time is seconds, every band is Hz
    and octaves, the STFT window is seconds and becomes a power of two per rate.
  * The gain is computed and applied per sample (rule 2); parameters are smoothed and
    coefficients recomputed once per CONTROL_BLOCK (the table's control_rate "block").
  * The result does not depend on the block size (D.5.1): the loop is per sample and
    the STFT carries its own partial hop between calls.
  * No allocation inside process(): every buffer is sized in prepare(). The prototype
    keeps that discipline so the port can be checked against it (rule 1).

Usage:
    from less_s import LessS, render
    y, info = render(x, 48000.0, mode=1, range_db=8.0)
"""
import math
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------- constants
# Every number here is a design choice, not a magic value. The comment says where it
# comes from; the port repeats these as named constants beside the C++ (G4).

CONTROL_BLOCK = 8           # samples between parameter smoothing and coefficient updates.
                            # parameters.csv says control_rate = block and rule 2 allows up
                            # to 32, but 32 is measurable: sweeping Frequency over the whole
                            # range at 10 Hz puts a sideband at the update rate itself
                            # (7000 - 48000/32 = 5500 Hz) at -50 dB. Measured against the
                            # tone: 32 -> -50 dB, 8 -> -65 dB, 1 -> -91 dB. 8 costs about
                            # 42k tan() per second for the seven filters (under 0.1 % CPU)
                            # and is the knee of that curve, so 8 it is.
                            # `measure.py zipper` holds it at < -60 dB.
KNEE_DB = 6.0               # soft knee of the gain computer (sketch 4.1)
RATIO = 4.0                 # fixed ratio up to the Range ceiling (sketch 4.1)
PEAK_RELEASE_S = 0.002      # decoupled peak detector's release: level estimation, not ballistics (E.1)
FULL_TAU_S = 0.050          # full-band mean-square window for Relative mode
FULL_FLOOR_DBFS = -50.0     # below this full-band level Relative mode does nothing (sketch 4.1)
PROGRAM_HOLD_S = 0.030      # Natural: after this long in release the release slows (E.1, two-stage opto)
CONFIG_FADE_S = 0.015       # crossfade for Mode / Listen / Stereo switches (rule 2: 10-20 ms)
STFT_WINDOW_S = 256.0 / 48000.0   # 5.333 ms -> 256 samples at 48 kHz; see Stft for why not 512
STFT_OVERLAP = 4            # Hann^2 is COLA at hop = N/4, so Range 0 reconstructs exactly
LOOKAHEAD_MAX_S = 0.005     # the table's Lookahead maximum; the ring is sized for it in prepare
EVENT_OPEN_DB = 1.0         # an ess-map event opens above this much reduction (sketch 4.4)
EVENT_CLOSE_DB = 0.5        # and closes below this
EVENT_RANGE_MARGIN_DB = 0.25   # "it hit the Range ceiling" tolerance for the red tick
LEARN_SECONDS = 2.0         # the Learn window (sketch 4.2)
LEARN_GATE_DBFS = -40.0     # only audio above this is captured
LEARN_SPLIT_HZ = 3000.0     # "energy above 3 kHz exceeds energy below by 6 dB" (sketch 4.2)
LEARN_SIBILANT_DB = 6.0
LEARN_MIN_FRAMES = 5        # fewer than this: leave the knobs alone
LEARN_WIDTH_ENERGY = 0.80   # the octave span that holds 80 % of the sibilant energy
LEARN_WIDTH_CLAMP = (0.6, 2.0)
LEARN_FRAME_S = 1024.0 / 48000.0   # 21.3 ms, a power of two per rate (rule 12)

# Speed: the three ballistics sets of sketch 4.1, with the detector blend each implies.
# attack_s / release_s are the control-signal time constants; rms_tau_s is the level
# estimator's window; peak_blend is how much of the level estimate is the peak path;
# release_slow is the second release stage's multiplier (1.0 = no second stage).
SPEEDS = (
    dict(name="Fast",    attack_s=0.0002, release_s=0.040, rms_tau_s=0.001, peak_blend=1.00, release_slow=1.0),
    dict(name="Natural", attack_s=0.0005, release_s=0.080, rms_tau_s=0.005, peak_blend=0.60, release_slow=2.5),
    dict(name="Smooth",  attack_s=0.0020, release_s=0.150, rms_tau_s=0.015, peak_blend=0.25, release_slow=1.0),
)

LESS_S_VERSION_NOTE = "prototype 1, G2, 2026-11-01"

# parameters.csv smoothing_domain = log: these smoothers hold log2(value), not the value
_LOG_SMOOTHED = ("frequency", "width")

MODE_WIDE, MODE_SPLIT, MODE_SPECTRAL = 0, 1, 2
LISTEN_OFF, LISTEN_ESS, LISTEN_DELTA = 0, 1, 2
STEREO_LINK, STEREO_MID, STEREO_DUAL = 0, 1, 2

# Band-pass Q from a bandwidth in octaves for one unity-peak 2nd-order band-pass:
# |H|^2 = 1/(1 + u^2) with u = Q (f/f0 - f0/f), the -3 dB edges at u = 1, and
# f_hi/f0 - f0/f_hi = 2 sinh(ln2 * bw/2). This is the *applier's* bell.
def q_for_bandwidth(bw_oct):
    bw_oct = max(1e-3, float(bw_oct))
    return 1.0 / (2.0 * math.sinh(math.log(2.0) / 2.0 * bw_oct))


# The *detector's* band is a different filter for a different job: a 4th-order
# Butterworth band-pass (high-pass at the lower edge, low-pass at the upper one), which
# is the sketch's "24 dB/oct skirts". Two resonant band-passes in cascade would only
# give 12 dB/oct and leak the vowels: measured at 2 kHz with the default band, the
# Butterworth pair rejects 29 dB where the cascade rejected 16 dB, and "leave 1-4 kHz
# untouched" is in the brief. The two Butterworth section Qs:
BUTTER4_Q = (1.0 / (2.0 * math.cos(math.pi / 8.0)), 1.0 / (2.0 * math.cos(3.0 * math.pi / 8.0)))


def butter4_hp_mag(f_hz, fc):
    r = np.asarray(f_hz, dtype=np.float64) / fc
    r4 = r ** 4
    return r4 / np.sqrt(1.0 + r4 * r4)


def butter4_lp_mag(f_hz, fc):
    r = np.asarray(f_hz, dtype=np.float64) / fc
    r4 = r ** 4
    return 1.0 / np.sqrt(1.0 + r4 * r4)


def detector_magnitude(f_hz, f0_hz, bw_oct):
    """|H| of the detector's band-pass, normalised to unity at f0 - so Threshold means
    the same level however wide the band is (at Width 0.3 the un-normalised pair is
    3.1 dB down at its own centre)."""
    lo, hi = f0_hz * 2.0 ** (-bw_oct / 2.0), f0_hz * 2.0 ** (bw_oct / 2.0)
    at_f0 = butter4_hp_mag(f0_hz, lo) * butter4_lp_mag(f0_hz, hi)
    return butter4_hp_mag(f_hz, lo) * butter4_lp_mag(f_hz, hi) / max(float(at_f0), 1e-12)


def band_magnitude(f_hz, f0_hz, q):
    """|H| of the unity-peak 2nd-order band-pass (analog prototype)."""
    f = np.maximum(np.asarray(f_hz, dtype=np.float64), 1e-9)
    u = q * (f / f0_hz - f0_hz / f)
    return 1.0 / np.sqrt(1.0 + u * u)


def bell_magnitude(f_hz, f0_hz, q, g):
    """|H| of the parallel-form bell `1 + (g-1) * BP` at gain `g`: the magnitude response
    Split actually has, which is the classic peaking-EQ magnitude

        |H| = sqrt((1-W^2)^2 + (g W / q)^2) / sqrt((1-W^2)^2 + (W / q)^2),  W = f / f0.

    Spectral weights every bin with *this*, not with |BP|. Weighting with |BP| - the
    obvious reading of "the gain per bin weighted by the band's shape" - gives a wider
    cut than Split has, because the bell is minimum-phase and the phase narrows its
    skirts: at 4 kHz with the default band and an 8 dB cut, |BP| weighting took 3.8 dB
    where Split takes 1.6 dB. Switching Mode would then change how much a nearby /f/ is
    touched, which is not what "Wide ducks all, Split the band, Spectral only the hissing
    bins" promises. At g = 1 this is exactly 1, so the Range 0 null still holds.
    """
    w = np.maximum(np.asarray(f_hz, dtype=np.float64), 1e-9) / f0_hz
    a = 1.0 - w * w
    return np.sqrt(a * a + (g * w / q) ** 2) / np.sqrt(a * a + (w / q) ** 2)


def detector_response(fs, f0_hz, bw_oct, probes):
    """The detector band's **digital** magnitude in dB at `probes`, measured by running an
    impulse through a fresh chain of the very filters the audio uses.

    `detector_magnitude` is the analog prototype, and the two part company near Nyquist:
    the TPT discretisation warps the frequency axis, so at 14 kHz and 48 kHz the real
    filter rejects 14.0 dB where the analog prototype says 9.8. This function is what the
    editor must draw its detection band from (rule 9: the picture comes from the same
    coefficients as the audio), and what a response test must compare against.
    """
    n = 1 << 15
    x = np.zeros(n)
    x[0] = 1.0
    lo, hi = f0_hz * 2.0 ** (-bw_oct / 2.0), f0_hz * 2.0 ** (bw_oct / 2.0)
    sections = [Svf(), Svf(), Svf(), Svf()]
    sections[0].set(fs, lo, BUTTER4_Q[0])
    sections[1].set(fs, lo, BUTTER4_Q[1])
    sections[2].set(fs, hi, BUTTER4_Q[0])
    sections[3].set(fs, hi, BUTTER4_Q[1])
    norm = 1.0 / max(float(butter4_hp_mag(f0_hz, lo) * butter4_lp_mag(f0_hz, hi)), 1e-12)
    y = np.empty(n)
    for i in range(n):
        y[i] = sections[3].low(sections[2].low(sections[1].high(sections[0].high(x[i])))) * norm
    spec = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    mag = np.abs(spec)
    return [20.0 * np.log10(mag[np.argmin(np.abs(freqs - p))] + 1e-30) for p in probes]


def db(x):
    return 20.0 * math.log10(max(float(x), 1e-30))


def undb(d):
    return 10.0 ** (float(d) / 20.0)


# ---------------------------------------------------------------- parameters
@dataclass
class Params:
    """Plain units, exactly the rows of parameters.csv (`range` and `auto` are Python
    and C++ keywords, hence range_db and auto_learn; the ids are `range`/`autoLearn`)."""
    frequency: float = 7000.0
    width: float = 1.2
    threshold: float = -28.0
    range_db: float = 8.0
    mode: int = MODE_SPLIT
    auto_learn: bool = True
    relative: bool = False
    speed: int = 1
    lookahead: float = 0.0          # ms
    listen: int = LISTEN_OFF
    stereo: int = STEREO_LINK
    mix: float = 100.0              # %
    bypass: bool = False


# ---------------------------------------------------------------- building blocks
class Svf:
    """TPT / ZDF state-variable filter (Simper). The band output is normalised to unity
    peak gain, so `1 + (G-1) * band` is an exact bell (rule 6: the band moves with
    Frequency and Width, so never a biquad with interpolated coefficients)."""

    def __init__(self):
        self.ic1 = 0.0
        self.ic2 = 0.0
        self.a1 = self.a2 = self.a3 = 0.0
        self.k = 1.0

    def reset(self):
        self.ic1 = 0.0
        self.ic2 = 0.0

    def set(self, fs, hz, q):
        hz = min(max(float(hz), 10.0), fs * 0.45)
        g = math.tan(math.pi * hz / fs)
        self.k = 1.0 / max(q, 1e-4)
        self.a1 = 1.0 / (1.0 + g * (g + self.k))
        self.a2 = g * self.a1
        self.a3 = g * self.a2

    def band(self, x):
        v3 = x - self.ic2
        v1 = self.a1 * self.ic1 + self.a2 * v3
        v2 = self.ic2 + self.a2 * self.ic1 + self.a3 * v3
        self.ic1 = 2.0 * v1 - self.ic1
        self.ic2 = 2.0 * v2 - self.ic2
        return self.k * v1

    def low(self, x):
        v3 = x - self.ic2
        v1 = self.a1 * self.ic1 + self.a2 * v3
        v2 = self.ic2 + self.a2 * self.ic1 + self.a3 * v3
        self.ic1 = 2.0 * v1 - self.ic1
        self.ic2 = 2.0 * v2 - self.ic2
        return v2

    def high(self, x):
        v3 = x - self.ic2
        v1 = self.a1 * self.ic1 + self.a2 * v3
        v2 = self.ic2 + self.a2 * self.ic1 + self.a3 * v3
        self.ic1 = 2.0 * v1 - self.ic1
        self.ic2 = 2.0 * v2 - self.ic2
        return x - self.k * v1 - v2


class OnePole:
    """y = x + (y - x) * exp(-dt/tau); tau in seconds, dt in samples (rule 12)."""

    def __init__(self, value=0.0):
        self.y = float(value)
        self.coef = 0.0

    def set(self, fs, tau_s, dt_samples=1.0):
        self.coef = 0.0 if tau_s <= 0.0 else math.exp(-dt_samples / (tau_s * fs))

    def process(self, x):
        self.y = x + (self.y - x) * self.coef
        return self.y

    def reset(self, value=0.0):
        self.y = float(value)


class LevelFollower:
    """One channel's band level: a decoupled peak path and a mean-square path, blended
    by Speed in the linear domain and converted to dB once (E.1)."""

    def __init__(self):
        self.peak = 0.0
        self.ms = 0.0
        self.peak_coef = 0.0
        self.ms_coef = 0.0
        self.blend = 1.0

    def set(self, fs, rms_tau_s, blend):
        self.peak_coef = math.exp(-1.0 / (PEAK_RELEASE_S * fs))
        self.ms_coef = math.exp(-1.0 / (max(rms_tau_s, 1e-6) * fs))
        self.blend = float(blend)

    def reset(self):
        self.peak = 0.0
        self.ms = 0.0

    def process(self, x):
        a = abs(x)
        self.peak = a if a > self.peak else a + (self.peak - a) * self.peak_coef
        xx = x * x
        self.ms = xx + (self.ms - xx) * self.ms_coef
        return self.blend * self.peak + (1.0 - self.blend) * math.sqrt(self.ms if self.ms > 0.0 else 0.0)


class Ballistics:
    """Attack and release on the control signal in dB (E.1: ballistics after the gain
    computer, in the log domain). Natural's release is program-dependent: after
    PROGRAM_HOLD_S of continuous release the time constant is multiplied by
    `release_slow` - E.1's two-stage optical release, which is what keeps a long ess
    from dipping back up in the middle."""

    def __init__(self):
        self.value = 0.0            # current reduction in dB, >= 0
        self.att = 0.0
        self.rel = 0.0
        self.rel_slow = 0.0
        self.hold_samples = 0
        self.releasing = 0

    def set(self, fs, attack_s, release_s, release_slow):
        self.att = math.exp(-1.0 / (max(attack_s, 1e-6) * fs))
        self.rel = math.exp(-1.0 / (max(release_s, 1e-6) * fs))
        self.rel_slow = math.exp(-1.0 / (max(release_s * release_slow, 1e-6) * fs))
        self.hold_samples = int(round(PROGRAM_HOLD_S * fs))

    def reset(self):
        self.value = 0.0
        self.releasing = 0

    def process(self, target_db):
        if target_db > self.value:
            self.releasing = 0
            coef = self.att
        else:
            self.releasing += 1
            coef = self.rel_slow if self.releasing > self.hold_samples else self.rel
        self.value = target_db + (self.value - target_db) * coef
        return self.value


class GainComputer:
    """dB over threshold in, dB of reduction out. Soft knee, fixed ratio, hard Range
    ceiling: "the most it ever takes away, so no ess vanishes"."""

    @staticmethod
    def reduction_db(over_db, range_db):
        half = KNEE_DB * 0.5
        slope = 1.0 - 1.0 / RATIO
        if over_db <= -half:
            r = 0.0
        elif over_db < half:
            r = slope * (over_db + half) ** 2 / (2.0 * KNEE_DB)
        else:
            r = slope * over_db
        return min(r, max(range_db, 0.0))


class Stft:
    """Hann WOLA with the window given in **seconds** (rule 12) and 4x overlap.

    Why not the sketch's 512/4x: a WOLA's algorithmic delay is the window, and with the
    partial hop that a host's arbitrary block sizes force you to carry it is exactly N
    samples. A 512-sample window therefore measures 512 samples of latency and the
    brief's latency_budget for Spectral is 256. A 5.33 ms window is 256 samples at
    48 kHz (256 of latency, 5.33 ms - the budget, exactly), 512 at 96 kHz and 1024 at
    192 kHz, so the *time* behaviour is identical at every rate. 5.33 ms also resolves a
    /t/ better than 10.7 ms, which is what a de-esser is for.

    Analysis and synthesis windows are both periodic Hann and the sum of their product
    is constant at hop = N/4, so with every bin gain at 1 the output is the input: the
    Range 0 null holds in Spectral too (brief: within -100 dBFS)."""

    def __init__(self):
        self.n = 0
        self.hop = 0

    def prepare(self, fs, window_s=STFT_WINDOW_S, overlap=STFT_OVERLAP):
        self.n = max(64, int(2 ** int(round(np.log2(window_s * fs)))))
        self.hop = max(1, self.n // overlap)
        self.window = np.hanning(self.n + 1)[:-1]          # periodic Hann: COLA at N/4
        w2 = self.window ** 2
        self.cola = float(sum(w2[k] for k in range(0, self.n, self.hop)))
        self.inbuf = np.zeros(self.n)
        self.outbuf = np.zeros(self.n)
        self.carry_in = np.zeros(self.hop)                 # the partial hop between calls
        self.carry_n = 0
        self.out_q = np.zeros(self.n + self.hop)           # ring: emitted samples waiting
        self.out_r = 0
        self.out_w = 0
        self.freqs = np.fft.rfftfreq(self.n, 1.0 / fs)
        self.reset()

    def reset(self):
        self.inbuf[:] = 0.0
        self.outbuf[:] = 0.0
        self.carry_in[:] = 0.0
        self.carry_n = 0
        self.out_q[:] = 0.0
        self.out_r = 0
        # the extra hop of pre-roll that makes the stream 1:1 whatever the block size;
        # it is what turns the WOLA's N - H into exactly N (see the docstring)
        self.out_w = self.hop
        self.frames = 0

    @property
    def latency(self):
        return self.n           # N - hop of WOLA delay plus the hop of pre-roll

    def _emit(self, x_hop, bin_gain):
        h = self.hop
        self.inbuf[:-h] = self.inbuf[h:]
        self.inbuf[-h:] = x_hop
        spec = np.fft.rfft(self.inbuf * self.window)
        self.outbuf += np.fft.irfft(spec * bin_gain, self.n) * self.window
        out = self.outbuf[:h] / self.cola
        self.outbuf[:-h] = self.outbuf[h:]
        self.outbuf[-h:] = 0.0
        for v in out:
            self.out_q[self.out_w % len(self.out_q)] = v
            self.out_w += 1
        self.frames += 1

    def push(self, x, bin_gain_for_frame):
        """Feed `len(x)` samples, get `len(x)` samples back. `bin_gain_for_frame(k)` is
        called once per frame with the index of the frame's first new sample inside x."""
        out = np.zeros(len(x))
        for i, v in enumerate(x):
            self.carry_in[self.carry_n] = v
            self.carry_n += 1
            if self.carry_n == self.hop:
                self._emit(self.carry_in, bin_gain_for_frame(i))
                self.carry_n = 0
            if self.out_r < self.out_w:
                out[i] = self.out_q[self.out_r % len(self.out_q)]
                self.out_r += 1
        return out


class Delay:
    """The dry path's delay line: stateful across blocks, so it compensates the reported
    latency (rule 7: "the dry path of every wet/dry mix is delay-compensated"). The
    first version of this was a per-block shift, which looked right on a single block
    and zeroed the first `latency` samples of *every* block - see docs/failures.md."""

    def prepare(self, max_delay, channels=2):
        self.tail = np.zeros((int(max_delay) + 1, channels))

    def reset(self):
        self.tail[:] = 0.0

    def process(self, x, delay):
        m = len(self.tail)
        delay = int(min(max(delay, 0), m - 1))
        combined = np.concatenate([self.tail, x])
        out = combined[m - delay: m - delay + len(x)].copy()
        self.tail = combined[-m:].copy()
        return out


class Learn:
    """The one-shot band finder (sketch 4.2). `processBlock` only copies the sidechain
    into a preallocated ring (rule 1); `analyse()` runs on the message thread - or, in
    the harness, synchronously after the render - and its result is written to the
    Frequency and Width parameters through begin/perform/end edit, so the host records
    one undo step and the preset shows modified."""

    def __init__(self):
        self.fs = 48000.0
        self.captured = 0
        self.armed = False

    def prepare(self, fs):
        self.fs = float(fs)
        self.buffer = np.zeros(int(round(LEARN_SECONDS * self.fs)))
        self.reset()

    def reset(self):
        self.captured = 0
        self.armed = False

    def arm(self):
        self.captured = 0
        self.armed = True

    def capture(self, mono_block):
        """Audio-thread side: a bounded copy into the ring, nothing else."""
        if not self.armed or self.captured >= len(self.buffer) or len(mono_block) == 0:
            return
        if db(float(np.max(np.abs(mono_block)))) < LEARN_GATE_DBFS:
            return                                   # silence moves nothing
        n = min(len(mono_block), len(self.buffer) - self.captured)
        self.buffer[self.captured:self.captured + n] = mono_block[:n]
        self.captured += n

    @property
    def ready(self):
        return self.armed and self.captured >= len(self.buffer)

    def analyse(self):
        """A pure function of the ring. Returns
        {found, frequency, width, sibilant_frames}."""
        n = max(64, int(2 ** int(round(np.log2(LEARN_FRAME_S * self.fs)))))
        hop = n // 2
        x = self.buffer[:self.captured]
        w = np.hanning(n + 1)[:-1]
        freqs = np.fft.rfftfreq(n, 1.0 / self.fs)
        hi = freqs >= LEARN_SPLIT_HZ
        lo = (freqs < LEARN_SPLIT_HZ) & (freqs >= 50.0)
        acc = np.zeros(freqs.shape)
        frames = 0
        for s in range(0, max(0, len(x) - n + 1), hop):
            spec = np.abs(np.fft.rfft(x[s:s + n] * w)) ** 2
            e_hi, e_lo = float(spec[hi].sum()), float(spec[lo].sum())
            # "energy above 3 kHz exceeds energy below by 6 dB", as a power ratio
            if e_hi > 0.0 and 10.0 * np.log10(e_hi / max(e_lo, 1e-30)) > LEARN_SIBILANT_DB:
                acc += spec
                frames += 1
        if frames < LEARN_MIN_FRAMES or float(acc[hi].sum()) <= 0.0:
            return dict(found=False, frequency=None, width=None, sibilant_frames=frames)
        f, e = freqs[hi], acc[hi]
        centroid = float((f * e).sum() / e.sum())
        # the octave span centred on the centroid that holds LEARN_WIDTH_ENERGY of it
        order = np.argsort(np.abs(np.log2(np.maximum(f, 1.0) / centroid)))
        cum = np.cumsum(e[order]) / e.sum()
        k = min(int(np.searchsorted(cum, LEARN_WIDTH_ENERGY)), len(order) - 1)
        span = 2.0 * float(abs(np.log2(max(f[order[k]], 1.0) / centroid)))
        return dict(found=True, frequency=float(np.clip(centroid, 2000.0, 16000.0)),
                    width=float(np.clip(span, *LEARN_WIDTH_CLAMP)), sibilant_frames=frames)


# ---------------------------------------------------------------- the processor
@dataclass
class Info:
    """What the editor and the tests read back. In the plugin the first three cross the
    thread boundary as atomics and a lock-free ring of PODs (D.1), never as arrays."""
    gain_db: np.ndarray = field(default_factory=lambda: np.zeros(0))   # applied reduction, dB, per sample
    band_db: np.ndarray = field(default_factory=lambda: np.zeros(0))   # the histogram's value, dB
    events: list = field(default_factory=list)          # ess map: (t0, t1, depth_db, hit_range)
    latency: int = 0
    learn: dict = field(default_factory=dict)


class LessS:
    def __init__(self):
        self.p = Params()
        self.fs = 48000.0
        self.prepared = False
        self.learn = Learn()
        self._learn_result = {}

    # -------------------------------------------------- lifecycle
    def prepare(self, fs, max_block=512):
        self.fs = float(fs)
        self.max_block = int(max_block)
        # 2 channels x (2 high-pass + 2 low-pass) Butterworth sections = 24 dB/oct skirts
        self.det = [[Svf(), Svf(), Svf(), Svf()] for _ in range(2)]
        self.bell = [Svf(), Svf(), Svf()]                # the appliers: L, R, M
        self.level = {k: LevelFollower() for k in ("L", "R", "M")}
        self.full = {k: OnePole() for k in ("L", "R", "M")}
        self.ball = {k: Ballistics() for k in ("link", "L", "R", "M")}
        self.stft = [Stft(), Stft()]
        for s in self.stft:
            s.prepare(self.fs)
        self.look_len = int(round(LOOKAHEAD_MAX_S * self.fs)) + 2
        self.look = np.zeros((self.look_len, 2))
        # the dry path has to cover the largest latency any mode reports
        self.dry_delay = Delay()
        self.dry_delay.prepare(max(self.look_len, self.stft[0].n + 2))
        self.band_delay = Delay()      # the same delay for Listen Ess in Spectral
        self.band_delay.prepare(max(self.look_len, self.stft[0].n + 2))
        self.gain_hist = np.zeros(max(4 * self.stft[0].n, 8))   # for the Spectral frame alignment
        self.learn.prepare(self.fs)
        # the smoothed parameters: tau from the table, updated once per CONTROL_BLOCK;
        # frequency and width in the log domain, threshold and range in dB, mix linear
        self.sm = {}
        for key, tau in (("frequency", 0.020), ("width", 0.020), ("threshold", 0.020),
                         ("range_db", 0.020), ("mix", 0.020)):
            op = OnePole()
            op.set(self.fs, tau, CONTROL_BLOCK)
            self.sm[key] = op
        self.fade_len = max(1, int(round(CONFIG_FADE_S * self.fs)))
        self.reset()
        self.prepared = True

    def reset(self):
        """rule 8: every piece of state, delay memory included."""
        for pair in self.det:
            for f in pair:
                f.reset()
        for b in self.bell:
            b.reset()
        for f in self.level.values():
            f.reset()
        for f in self.full.values():
            f.reset(0.0)
        for b in self.ball.values():
            b.reset()
        for s in self.stft:
            s.reset()
        self.look[:] = 0.0
        self.look_pos = 0
        self.dry_delay.reset()
        self.band_delay.reset()
        self.gain_hist[:] = 1.0
        self.gain_pos = 0
        self.learn.reset()
        self._learn_result = {}
        self._first_audio = False
        for key, op in self.sm.items():
            # the log-domain smoothers hold log2(value), so reset has to match the domain
            # (they held the linear value once: 2 ** 7000 overflowed on the first block)
            v = float(getattr(self.p, key))
            op.reset(math.log2(max(v, 1e-3)) if key in _LOG_SMOOTHED else v)
        self._mode = self.p.mode
        self._listen = self.p.listen
        self._stereo = self.p.stereo
        self._prev = (self._mode, self._listen, self._stereo)
        self._fade = 1.0
        self._event = None
        self._events = []
        self._t = 0
        self._update_coefficients()

    def set_params(self, **kw):
        for k, v in kw.items():
            if not hasattr(self.p, k):
                raise KeyError("no parameter %r (the table is parameters.csv)" % k)
            setattr(self.p, k, v)
        if not self.prepared:
            return
        cfg = (self.p.mode, self.p.listen, self.p.stereo)
        if cfg != (self._mode, self._listen, self._stereo):
            # rule 2: a switch is crossfaded, never stepped. A change of Mode to or from
            # Spectral also changes the reported latency; the host re-measures and the
            # sketch (4.7) accepts one click there.
            self._prev = (self._mode, self._listen, self._stereo)
            self._mode, self._listen, self._stereo = cfg
            self._fade = 0.0
            if MODE_SPECTRAL in (self._prev[0], cfg[0]) and self._prev[0] != cfg[0]:
                self._fade = 1.0
                for s in self.stft:
                    s.reset()

    # -------------------------------------------------- reported latency (rule 7)
    @property
    def latency(self):
        if self.p.mode == MODE_SPECTRAL:
            return self.stft[0].latency      # the Lookahead knob is disabled here: the frame is the look-ahead
        return int(round(self.p.lookahead * 1e-3 * self.fs))

    # -------------------------------------------------- the render
    def process(self, x):
        """x: (n, 1 or 2). Returns (y, Info)."""
        x = np.asarray(x, dtype=np.float64)
        if x.ndim == 1:
            x = x[:, None]
        if x.shape[1] == 1:
            x = np.repeat(x, 2, axis=1)
        n = x.shape[0]
        latency = self.latency
        if n == 0:
            return np.zeros((0, 2)), Info(np.zeros(0), np.zeros(0), [], latency, dict(self._learn_result))
        # the dry line is fed exactly once per block, whatever happens next, or its state
        # drifts out of step with the wet path
        x_lat = self.dry_delay.process(x, latency)
        if self.p.bypass:
            # rule 7: bypass is latency-compensated and nulls against the input
            return x_lat, Info(np.zeros(n), np.zeros(n), [], latency, dict(self._learn_result))

        # Learn: the audio thread's share is one bounded copy (rule 1)
        mono = 0.5 * (x[:, 0] + x[:, 1])
        if self.p.auto_learn and not self._first_audio and not self._learn_result \
                and db(float(np.max(np.abs(mono)))) > LEARN_GATE_DBFS:
            self._first_audio = True
            self.learn.arm()
        self.learn.capture(mono)

        y = np.zeros((n, 2))
        dry = np.zeros((n, 2))          # the input as the appliers see it (lookahead-delayed)
        gain_db = np.zeros(n)
        band_db = np.zeros(n)
        band_sig = np.zeros((n, 2))     # the detector's band signal, for Listen Ess
        mix_series = np.zeros(n)        # the smoothed Mix, per sample (rule 2)

        look = 0 if self.p.mode == MODE_SPECTRAL else int(round(self.p.lookahead * 1e-3 * self.fs))
        look = min(max(look, 0), self.look_len - 1)

        # locals: the loop runs once per sample, so every lookup is hoisted out of it
        hpl0, hpl1, lpl0, lpl1 = self.det[0]
        hpr0, hpr1, lpr0, lpr1 = self.det[1]
        det_norm = self._det_norm
        bell_l, bell_r, bell_m = self.bell
        lev_l, lev_r, lev_m = self.level["L"], self.level["R"], self.level["M"]
        ful_l, ful_r, ful_m = self.full["L"], self.full["R"], self.full["M"]
        b_link, b_l, b_r, b_m = self.ball["link"], self.ball["L"], self.ball["R"], self.ball["M"]
        reduction = GainComputer.reduction_db
        relative = self.p.relative
        look_x, look_len = self.look, self.look_len
        hist, hist_n = self.gain_hist, len(self.gain_hist)
        fade_step = 1.0 / self.fade_len
        xl, xr = x[:, 0], x[:, 1]

        for i in range(n):
            if (self._t % CONTROL_BLOCK) == 0:
                self._update_coefficients()
            thr, rng = self._thr, self._rng
            l = xl[i]
            r = xr[i]

            # ---- detector: a 4th-order Butterworth band-pass per channel (high-pass at
            # the lower edge, low-pass at the upper one), normalised to unity at the
            # centre so Threshold means the same level at every Width. The band-pass is
            # linear, so BP(M) = (BP(L) + BP(R)) / 2: the Mid detector costs no state.
            bl = lpl1.low(lpl0.low(hpl1.high(hpl0.high(l)))) * det_norm
            br = lpr1.low(lpr0.low(hpr1.high(hpr0.high(r)))) * det_norm
            bm = 0.5 * (bl + br)
            band_sig[i, 0] = bl
            band_sig[i, 1] = br
            lv_l = lev_l.process(bl)
            lv_r = lev_r.process(br)
            lv_m = lev_m.process(bm)
            f_l = ful_l.process(l * l)
            f_r = ful_r.process(r * r)
            f_m = ful_m.process(0.25 * (l + r) * (l + r))

            if relative:
                fl_link = db(math.sqrt(max(f_l, f_r, 0.0)))
                show_link = db(max(lv_l, lv_r)) - fl_link
                red_link = 0.0 if fl_link < FULL_FLOOR_DBFS else reduction(show_link - thr, rng)
                fl = db(math.sqrt(f_l if f_l > 0.0 else 0.0))
                show_l = db(lv_l) - fl
                red_l = 0.0 if fl < FULL_FLOOR_DBFS else reduction(show_l - thr, rng)
                fr = db(math.sqrt(f_r if f_r > 0.0 else 0.0))
                show_r = db(lv_r) - fr
                red_r = 0.0 if fr < FULL_FLOOR_DBFS else reduction(show_r - thr, rng)
                fm = db(math.sqrt(f_m if f_m > 0.0 else 0.0))
                show_m = db(lv_m) - fm
                red_m = 0.0 if fm < FULL_FLOOR_DBFS else reduction(show_m - thr, rng)
            else:
                show_link = db(lv_l if lv_l > lv_r else lv_r)
                red_link = reduction(show_link - thr, rng)
                show_l = db(lv_l)
                red_l = reduction(show_l - thr, rng)
                show_r = db(lv_r)
                red_r = reduction(show_r - thr, rng)
                show_m = db(lv_m)
                red_m = reduction(show_m - thr, rng)
            g_link = undb(-b_link.process(red_link))
            g_l = undb(-b_l.process(red_l))
            g_r = undb(-b_r.process(red_r))
            g_m = undb(-b_m.process(red_m))

            # ---- lookahead: the audio is delayed, the detector is not (E.2)
            look_x[self.look_pos, 0] = l
            look_x[self.look_pos, 1] = r
            rd = (self.look_pos - look) % look_len
            dl = look_x[rd, 0]
            dr = look_x[rd, 1]
            self.look_pos = (self.look_pos + 1) % look_len
            dry[i, 0] = dl
            dry[i, 1] = dr

            # ---- the time-domain appliers, crossfaded on a Mode / Listen / Stereo change
            o0 = o1 = 0.0
            fade = self._fade
            for cfg, w in (((self._mode, self._listen, self._stereo), fade),
                           (self._prev, 1.0 - fade)):
                if w <= 0.0:
                    continue
                mode, listen, stereo = cfg
                if stereo == STEREO_LINK:
                    gc1 = gc2 = g_link
                elif stereo == STEREO_DUAL:
                    gc1, gc2 = g_l, g_r
                else:
                    gc1 = gc2 = g_m
                if listen == LISTEN_ESS:
                    c0 = c1 = bm
                    if stereo != STEREO_MID:
                        c0, c1 = bl, br
                elif mode == MODE_SPECTRAL:
                    c0 = c1 = 0.0                       # written by the STFT path below
                elif stereo == STEREO_MID:
                    m = 0.5 * (dl + dr)
                    s = 0.5 * (dl - dr)
                    m2 = m * gc1 if mode == MODE_WIDE else m + (gc1 - 1.0) * bell_m.band(m)
                    c0, c1 = m2 + s, m2 - s
                elif mode == MODE_WIDE:
                    c0, c1 = dl * gc1, dr * gc2
                else:
                    c0 = dl + (gc1 - 1.0) * bell_l.band(dl)
                    c1 = dr + (gc2 - 1.0) * bell_r.band(dr)
                if listen == LISTEN_DELTA and mode != MODE_SPECTRAL:
                    c0, c1 = dl - c0, dr - c1
                o0 += w * c0
                o1 += w * c1
            y[i, 0] = o0
            y[i, 1] = o1

            if self._stereo == STEREO_LINK:
                g_show, show = g_link, show_link
            elif self._stereo == STEREO_DUAL:
                g_show, show = 0.5 * (g_l + g_r), 0.5 * (show_l + show_r)
            else:
                g_show, show = g_m, show_m
            gain_db[i] = -db(g_show)
            band_db[i] = show
            mix_series[i] = self.sm["mix"].y
            hist[self.gain_pos % hist_n] = g_show
            self.gain_pos += 1
            if self._fade < 1.0:
                self._fade = min(1.0, self._fade + fade_step)
            self._t += 1

        band_lat = self.band_delay.process(band_sig, latency)
        if self.p.mode == MODE_SPECTRAL:
            y = self._spectral(dry, band_lat, x_lat)

        # ---- Mix: a linear blend of the delayed dry and the wet. EX-1 in status.md:
        # rule 5 asks for an equal-power crossfade, which is right for an uncorrelated
        # wet path; here dry and wet are the same voice minus a little band, so
        # equal-power would add to +3 dB at Mix 50 %. Linear keeps the level flat.
        # Per sample, from the smoothed series, not once per block from its final value:
        # the port applies it per sample and the G5 null has to close while Mix moves.
        m = np.clip(mix_series, 0.0, 100.0)[:, None] / 100.0
        if self.p.listen == LISTEN_OFF and float(np.min(m)) < 1.0:
            y = x_lat * (1.0 - m) + y * m

        self._collect_events(gain_db)
        if self.learn.ready:
            self._learn_result = self.learn.analyse()
            self.learn.armed = False
            if self._learn_result.get("found"):
                self.p.frequency = self._learn_result["frequency"]
                self.p.width = self._learn_result["width"]
        return y, Info(gain_db, band_db, list(self._events), latency, dict(self._learn_result))

    # -------------------------------------------------- helpers
    def _update_coefficients(self):
        p = self.p
        f0 = 2.0 ** self.sm["frequency"].process(math.log2(max(p.frequency, 1.0)))
        wd = 2.0 ** self.sm["width"].process(math.log2(max(p.width, 1e-3)))
        self._thr = self.sm["threshold"].process(p.threshold)
        self._rng = self.sm["range_db"].process(p.range_db)
        self.sm["mix"].process(p.mix)
        q_bell = q_for_bandwidth(wd)
        lo, hi = f0 * 2.0 ** (-wd / 2.0), f0 * 2.0 ** (wd / 2.0)
        for sections in self.det:
            sections[0].set(self.fs, lo, BUTTER4_Q[0])
            sections[1].set(self.fs, lo, BUTTER4_Q[1])
            sections[2].set(self.fs, hi, BUTTER4_Q[0])
            sections[3].set(self.fs, hi, BUTTER4_Q[1])
        self._det_norm = 1.0 / max(float(butter4_hp_mag(f0, lo) * butter4_lp_mag(f0, hi)), 1e-12)
        for b in self.bell:
            b.set(self.fs, f0, q_bell)
        sp = SPEEDS[int(np.clip(p.speed, 0, 2))]
        for f in self.level.values():
            f.set(self.fs, sp["rms_tau_s"], sp["peak_blend"])
        for f in self.full.values():
            f.set(self.fs, FULL_TAU_S)
        for b in self.ball.values():
            b.set(self.fs, sp["attack_s"], sp["release_s"], sp["release_slow"])
        self._f0, self._q_bell = f0, q_bell

    def _spectral(self, dry, band_lat, x_lat):
        """The STFT path. Every bin of a frame gets `1 + (G-1) * W(bin)`, with W the band
        shape of the same bell and G the control gain at the frame's centre - so the
        reduction lands on the ess and the frame itself is the look-ahead."""
        n = dry.shape[0]
        out = np.zeros((n, 2))
        for ch in (0, 1):
            s = self.stft[ch]

            def bin_gain(i, s=s):
                # the weights are taken per *frame*, from the coefficients current at that
                # frame - not once per process() call, or a moving Frequency would make
                # the output depend on the host's block size (D.5.1)
                centre = self.gain_pos - n + i - s.n // 2
                g = float(self.gain_hist[centre % len(self.gain_hist)]) if centre >= 0 else 1.0
                return bell_magnitude(s.freqs, self._f0, self._q_bell, g)

            out[:, ch] = s.push(dry[:, ch], bin_gain)
        if self.p.listen == LISTEN_ESS:
            return band_lat
        if self.p.listen == LISTEN_DELTA:
            return x_lat - out
        return out

    def _collect_events(self, gain_db):
        """The ess map: an event opens above EVENT_OPEN_DB of reduction and closes below
        EVENT_CLOSE_DB; the bar is the deepest reduction inside it (sketch 4.4)."""
        rng = float(self.sm["range_db"].y)
        base = self._t - len(gain_db)
        for i, g in enumerate(gain_db):
            t = (base + i) / self.fs
            if self._event is None:
                if g > EVENT_OPEN_DB:
                    self._event = dict(t0=t, depth=g)
            else:
                self._event["depth"] = max(self._event["depth"], g)
                if g < EVENT_CLOSE_DB:
                    e = self._event
                    self._events.append((e["t0"], t, e["depth"],
                                         e["depth"] >= rng - EVENT_RANGE_MARGIN_DB))
                    self._event = None


# ---------------------------------------------------------------- convenience
def render(x, fs, block=512, **params):
    """One render through a fresh instance, in blocks, the way a host calls it."""
    x = np.asarray(x, dtype=np.float64)
    p = LessS()
    p.prepare(fs, block)
    p.set_params(**params)
    p.reset()                       # the smoothers start at the chosen values, not at the defaults
    n = x.shape[0]
    out = np.zeros((n, 2))
    gain_db, band_db = np.zeros(n), np.zeros(n)
    info = Info()
    i = 0
    while i < n:
        k = min(block, n - i)
        y, inf = p.process(x[i:i + k])
        out[i:i + k] = y
        gain_db[i:i + k] = inf.gain_db
        band_db[i:i + k] = inf.band_db
        info = inf
        i += k
    return out, Info(gain_db, band_db, info.events, info.latency, info.learn)
