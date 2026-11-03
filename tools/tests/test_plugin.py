#!/usr/bin/env python3
"""Less S - the test suite.

Drives the product's offline renderer (harness-contract.md v3) and asserts on its JSON and
WAVs with dspkit. Run directly, or through CTest:

    HARNESS=build/LessSHarness_artefacts/Release/LessSHarness python3 tools/tests/test_plugin.py --label fast
    ctest --preset fast

Labels (D.3.1): fast = contract, rate/block matrix, health, properties (every build, < 60 s);
render = goldens, the presence tests of the brief's defining features, and the G5 null
against the prototype (every commit); the host validators are not here (validate_plugin.py).
Every test is a rule or a DoD line from the core card, or a line of `docs/brief.md`; the name
says which. Per-test seconds are printed; a `fast` test over FAST_BUDGET_S fails.

Test material and the null reference come from `sound design/proto/` - the same generator and
the same model the design was measured with, so a number here and a number in
`measure.py` mean the same thing. They are design reference material, never compiled into
the product (CLAUDE.md).
"""
import json
import math
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.environ.get("DSPKIT", str(Path(__file__).resolve().parent)))
import dspkit as K  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "sound design" / "proto"))

HARNESS = os.environ.get("HARNESS", "build/LessSHarness_artefacts/Release/LessSHarness")
GOLDEN_DIR = Path(os.environ.get("GOLDEN_DIR", "tools/tests/golden"))   # committed goldens + sidecars
GOLDEN_ARCH = os.environ.get("GOLDEN_ARCH", "x86_64")                # D.2.1: the slice the host runs
#: Rates are ints, and the harness echoes an integral rate as an integer, because
#: `dspkit.assert_echo` compares the echo to the request *as a string* - so `48000` against
#: a JUCE double echo of `48000.0` fails rule 13's own check. A numeric comparison in the
#: kit would be the real fix (a skills-bob item; this repo may not edit the kit).
DEFAULT = dict(seed=1, sample_rate=48000, block=512, seconds=2.0)
#: Pink noise at -12 dBFS, not the template's full-scale impulse: a de-esser passes its
#: input at unity, so an impulse comes out at exactly 0.0 dBFS and the generic
#: "peak below 0 dBFS" check cannot pass. Noise also gives the detector something to do at
#: every rate, which is the point of the matrix. The tests that need an impulse ask for it.
SOURCE = dict(signal="noise:pink:-12")
PARAM = ("range", 0.5)               # one real parameter ID and a non-default value (12 dB)
RATES = (44100, 48000, 88200, 96000, 176400, 192000)
#: The DoD asks for block 0 too. `--block=0` is refused by the harness contract (a render
#: of zero-length blocks never advances), so the zero-length case is covered by
#: `test_random_block_sizes_from_zero`, where `--block=random:` does produce 0-sample
#: blocks, and `processBlock` returns early on them.
BLOCKS = (1, 13, 32, 64, 512, 4096)
INSTRUMENT = "notes" in SOURCE
FAST_BUDGET_S = float(os.environ.get("FAST_BUDGET_S", "20"))   # one test; the whole `fast` label stays under 60 s
# F.8 tolerances (peak of the residual, absolute dBFS, no alignment): same machine and
# compiler bit-exact; across slices feed-forward -100, feedback tails -80.
GOLDEN_PEAK_DB = {"same": -140.0, "cross-feedforward": -100.0, "cross-feedback": -80.0}


def run(params=None, **flags):
    f = dict(DEFAULT, **SOURCE)
    f.update(flags)
    res = K.render(HARNESS, params, **f)
    echo = {k: v for k, v in f.items() if k in ("seed", "sample_rate", "block", "seconds", "preset")
            and not (k == "block" and str(v).startswith("random:"))}
    K.assert_echo(res, params, **echo)                                     # rule 13
    return res


# ---------------------------------------------------------------- plain-unit settings
# The harness takes normalised 0..1 parameter values, which says nothing about Hz or dB.
# A preset file carries *plain* units through the product's own State.h, so the tests set
# parameters the way a user does and the numbers in a failure message are readable.
_PRESET_DIR = None


def plain(slug="t", **values):
    """Write a temp preset with these plain values and return the flags to render it."""
    global _PRESET_DIR
    if _PRESET_DIR is None:
        _PRESET_DIR = tempfile.mkdtemp(prefix="less-s-tests-")
        os.environ["FACTORY_PRESETS"] = _PRESET_DIR
        (Path(_PRESET_DIR).parent / "presets.csv").write_text(
            "slug,name,category,tags,edge,author,notes\n")
        os.environ["PRESETS_CSV"] = str(Path(_PRESET_DIR).parent / "presets.csv")
    rows = "\n".join('      <PARAM id="%s" value="%s"/>' % (k, v) for k, v in values.items())
    (Path(_PRESET_DIR) / (slug + ".oberlipreset")).write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<OberliPreset name="%s" author="tests" category="Lead" description="" '
        'pluginVersion="0" created="2026-11-01" factory="false">\n'
        '  <LessSState version="1" dspVersion="1">\n    <PARAMETERS>\n%s\n'
        '    </PARAMETERS>\n    <Extra/>\n  </LessSState>\n</OberliPreset>\n' % (slug, rows))
    return dict(preset=slug)


class factory_bank:
    """Point the harness at the *real* `presets/` for one block, whatever `plain()` has
    already done to FACTORY_PRESETS in this process."""

    def __enter__(self):
        self.saved = {k: os.environ.get(k) for k in ("FACTORY_PRESETS", "PRESETS_CSV")}
        os.environ["FACTORY_PRESETS"] = str(REPO / "presets")
        os.environ["PRESETS_CSV"] = str(REPO / "presets.csv")
        return self

    def __exit__(self, *_):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


# ---------------------------------------------------------------- material
_MATERIAL = {}


def material(kind, fs=48000.0, **kw):
    """A WAV of the design's own test material, written once per session."""
    key = (kind, fs, tuple(sorted(kw.items())))
    if key in _MATERIAL:
        return _MATERIAL[key]
    import material as M
    import numpy as np
    global _PRESET_DIR
    if _PRESET_DIR is None:
        plain("warmup")
    if kind == "phrase":
        x, labels = M.phrase(fs, **kw)
    elif kind == "burst_pair":
        x, labels = M.burst_pair(fs, **kw)
    elif kind == "noise":
        x, labels = M.white_noise(fs, **kw)
    else:
        raise KeyError(kind)
    path = Path(_PRESET_DIR) / ("%s-%g.wav" % (kind, fs))
    K.write_wav(path, np.asarray(x), fs)
    # hand back what was *written*, not what was generated: the WAV is float32 and the
    # prototype must see the same samples the harness reads, or the G5 null compares two
    # different inputs and the ess map counts a marginal event on one side only
    x32, _ = K.read_wav(path)
    _MATERIAL[key] = (path, labels, x32)
    return _MATERIAL[key]


class Timed(unittest.TestCase):
    label = "fast"

    def setUp(self):
        self._t0 = time.time()

    def tearDown(self):
        dt = time.time() - self._t0
        print("  [%s %.1f s]" % (self.label, dt), end="", flush=True)
        if self.label == "fast" and dt > FAST_BUDGET_S:
            self.fail("fast test took %.0f s; budget %.0f s (D.3.6: move it to a slower tier, do not delete it)" % (dt, FAST_BUDGET_S))


class Contract(Timed):
    def test_harness_echoes_params(self):                                  # rule 13
        pid, val = PARAM
        res = run({pid: val})
        self.assertAlmostEqual(res["applied"]["params"][pid], val, places=6)

    def test_seeded_runs_are_bit_identical(self):                          # DoD: reset + seed
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.wav", Path(d) / "b.wav"
            run(out=a)
            run(out=b)
            xa, _ = K.read_wav(a)
            xb, _ = K.read_wav(b)
            self.assertTrue((xa == xb).all(), "two seeded renders differ")


class RateAndBlock(Timed):
    def test_rate_block_matrix_is_clean(self):                             # DoD: 42 combinations
        for fs in RATES:
            for blk in BLOCKS:
                with self.subTest(fs=fs, block=blk):
                    res = run(sample_rate=fs, block=blk, seconds=0.25)
                    self.assertEqual(res["health"]["nan"] + res["health"]["inf"], 0)
                    self.assertLess(res["levels"]["peak_dbfs"], 0.0)

    def test_random_block_sizes_from_zero(self):                           # D.5.1, fuzz
        res = run(block="random:7", max_block=1024, seconds=0.5)
        self.assertEqual(res["health"]["nan"], 0)

    def test_block_larger_than_announced(self):                            # D.5.1
        # NaN-free is not enough: a plugin that renders only the announced part of an oversized
        # block leaves a silent gap. Compare, window by window, against the same render in
        # announced-size blocks (seen once: a 6 dB drop in one window, whole-file
        # RMS within 1 dB).
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "ref.wav", Path(d) / "big.wav"
            run(block=256, max_block=256, seconds=0.5, out=a)
            res = run(block=1024, max_block=256, seconds=0.5, out=b)
            self.assertEqual(res["health"]["nan"], 0)
            xa, fs = K.read_wav(a)
            xb, _ = K.read_wav(b)
            self.assertLess(K.dropout_db(xa, xb, fs), 3.0, "an oversized block rendered quieter than its announced-size twin")


class Health(Timed):
    def test_silence_after_audio_has_no_denormal_storm_or_dc(self):        # DoD: silence test, 48 k/64
        """One second of noise, then nine of silence: nothing may ring on, no DC may be
        left behind, and the worst block must still fit the deadline.

        The template measured `levels.dc_dbfs` over the whole render, which for an effect
        is the *input's* DC: the harness's pink-noise generator sits at -65 dBFS of DC, and
        a Range 0 render (where the output is the input) reports the same -65, so the check
        was failing on the test signal. What the DoD line is about is DC the plugin adds,
        so it is measured on the silent tail of the output.
        """
        import numpy as np
        import material as M
        fs = 48000.0
        noise, _ = M.white_noise(fs, dbfs=-12.0, seconds=1.0)
        x = np.concatenate([noise, np.zeros((int(9.0 * fs), 2))])
        if _PRESET_DIR is None:
            plain("warmup")
        src = Path(_PRESET_DIR) / "silence-tail.wav"
        K.write_wav(src, x, fs)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "y.wav"
            res = K.render(HARNESS, None, seed=1, sample_rate=int(fs), block=64, seconds=10.0,
                           profile=1, warmup=200, **plain("sil", range=8.0, autoLearn=0),
                           **{"in": str(src), "out": str(out)})
            y, _ = K.read_wav(out)
        tail = y[int(1.5 * fs):]
        self.assertEqual(res["health"]["nan"] + res["health"]["inf"], 0)
        self.assertLess(K.peak_dbfs(tail), -120.0, "the output rings on after the input stops")
        self.assertLess(K.dc_offset_dbfs(tail), -120.0, "DC is left behind in the silence")
        self.assertLess(res["profile"]["p999_pct"], 25.0)                  # rule 20: p99.9 judged
        print("\n    48 k/64: p50 %.1f %%  p99 %.1f %%  p99.9 %.1f %%  max %.1f %%  "
              "over_deadline %d (reported, not judged, rule 20)"
              % (res["profile"]["p50_pct"], res["profile"]["p99_pct"], res["profile"]["p999_pct"],
                 res["profile"]["max_pct"], res["profile"]["over_deadline"]), end="")

    def test_latency_matches_impulse(self):                                # rule 7
        if INSTRUMENT:
            self.skipTest("effects only")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "imp.wav"
            res = run(signal="impulse", out=out)
            x, fs = K.read_wav(out)
            ref = x[:, :1] * 0.0
            ref[0, 0] = 0.5
            measured = K.latency_samples(ref, x[:, :1])
            self.assertEqual(measured, res["applied"]["latency_samples"])

    def test_tail_is_silent_after_reported_tail(self):                     # D.2.5, D.5.1
        if not INSTRUMENT:
            self.skipTest("instruments; effects feed an impulse instead")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "tail.wav"
            res = run(seconds=6.0, gate=1.0, out=out)
            x, fs = K.read_wav(out)
            after = x[int((1.0 + res["applied"]["tail_seconds"]) * fs):]
            self.assertLess(K.peak_dbfs(after) if after.size else -400.0, -90.0)


class Properties(Timed):
    def test_state_round_trip_is_bytewise(self):                           # D.5.3
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            pid, val = PARAM
            run({pid: val}, state_out=d / "a.state", out=d / "a.wav", seconds=0.5)
            rb = run(state_in=d / "a.state", state_out=d / "b.state", out=d / "b.wav", seconds=0.5)
            self.assertEqual((d / "a.state").read_bytes(), (d / "b.state").read_bytes())
            self.assertAlmostEqual(rb["applied"]["params"][pid], val, places=6)
            xa, _ = K.read_wav(d / "a.wav")
            xb, _ = K.read_wav(d / "b.wav")
            self.assertTrue((xa == xb).all())

    def test_state_round_trip_is_bytewise_for_every_parameter(self):       # D.5.3, rule 19
        """The kit's test (test_template.py): the defaults, then every parameter at an odd
        normalised value, saved three times: one text. A skewed range (a second float round
        trip on save) or a compiler that fuses start + span * n into one FMA (arm64) moves a
        value here."""
        import subprocess
        listed = json.loads(subprocess.run(K.harness_cmd(HARNESS) + ["--list-params"],
                                           capture_output=True, text=True, check=True).stdout)
        odd = {p["id"]: 0.3 if p.get("steps", 0) in (0, None) else round(0.3 * (p["steps"] - 1)) / (p["steps"] - 1)
               for p in listed if p.get("steps", 0) != 2}           # bools (and bypass) stay at their default
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name, params in (("defaults", None), ("odd", odd)):
                run(params, state_out=d / "a.state", seconds=0.1)
                run(state_in=d / "a.state", state_out=d / "b.state", seconds=0.1)
                run(state_in=d / "b.state", state_out=d / "c.state", seconds=0.1)
                a, b, c = ((d / n).read_bytes() for n in ("a.state", "b.state", "c.state"))
                self.assertEqual(a, b, "%s: the state changed on the first load and save" % name)
                self.assertEqual(b, c, "%s: the state drifts on every load and save" % name)

    def test_init_preset_equals_the_table_defaults(self):                  # F.14.3
        """Init is the parameter table, with nothing of its own.

        `presetlint bank --harness` owns this check in the kit, but its version compares a
        normalised echo against a plain choice index, so Mode (1 of 3) and Speed read as
        errors there. This one asks the plugin for its own defaults (`--list-params`,
        JUCE's `getDefaultValue`) and compares like for like, which is also the comparison
        that would catch a real drift between `presets/init.oberlipreset` and the table.
        """
        import subprocess
        listing = json.loads(subprocess.run(K.harness_cmd(HARNESS) + ["--list-params"],
                                            capture_output=True, text=True, check=True).stdout)
        with factory_bank():
            res = K.render(HARNESS, None, **dict(DEFAULT, preset="init"), **SOURCE)
        applied = res["applied"]["params"]
        for p in listing:
            self.assertAlmostEqual(applied[p["id"]], p["default"], places=5,
                                   msg="init has %s at %r, the table default is %r"
                                       % (p["id"], applied[p["id"]], p["default"]))

    def test_preset_listing_matches_the_csv(self):                         # F.14.3
        """`--list-presets` equals presets.csv, in order: the drawer and the bank are one
        list, and a renamed file must not vanish silently."""
        import csv
        with open(REPO / "presets.csv", newline="") as f:
            want = [r["slug"] for r in csv.DictReader(f)]
        with factory_bank():
            have = [p["slug"] for p in K.list_presets(HARNESS)]
        self.assertEqual(have, want)
        for slug in want:
            self.assertTrue((REPO / "presets" / (slug + ".oberlipreset")).exists(),
                            "presets.csv lists %s but presets/%s.oberlipreset is missing" % (slug, slug))

    def test_corrupted_state_does_not_crash(self):                         # D.5.3, fuzz
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            run(state_out=d / "good.state", seconds=0.25)
            good = (d / "good.state").read_bytes()
            cases = {"empty": b"", "truncated": good[: len(good) // 2], "garbage": bytes(range(256)) * 4,
                     "flipped": bytes(b ^ 0x55 for b in good)}
            for name, blob in cases.items():
                with self.subTest(case=name):
                    (d / "bad.state").write_bytes(blob)
                    try:
                        res = K.render(HARNESS, state_in=d / "bad.state", seconds=0.25, **{k: v for k, v in DEFAULT.items() if k != "seconds"}, **SOURCE)
                    except RuntimeError as e:
                        # a clean refusal (non-zero exit with a message) is acceptable; a crash is not
                        self.assertNotIn("Segmentation", str(e))
                        self.assertNotIn("-11", str(e).split(")")[0])
                        continue
                    self.assertEqual(res["health"]["nan"], 0)


class Goldens(Timed):
    """F.13.6: a golden per defining feature, rendered on GOLDEN_ARCH, with a sidecar."""
    label = "render"

    def test_goldens_match(self):
        sidecars = sorted(GOLDEN_DIR.glob("*.json")) if GOLDEN_DIR.exists() else []
        if not sidecars:
            self.skipTest("no goldens in %s yet (render them with the harness, write <name>.json beside each)" % GOLDEN_DIR)
        for sc in sidecars:
            meta = json.loads(sc.read_text())
            with self.subTest(golden=sc.stem), tempfile.TemporaryDirectory() as d:
                out = Path(d) / "now.wav"
                flags = dict(meta["flags"])
                flags["out"] = out
                res = K.render(HARNESS, meta.get("params"), **flags)
                arch = res["applied"].get("build", {}).get("arch")
                kind = "same" if arch == meta.get("arch") else ("cross-feedback" if meta.get("feedback") else "cross-feedforward")
                now, fs = K.read_wav(out)
                gold, _ = K.read_wav(sc.with_suffix(".wav"))
                r = K.null_residual(gold, now, align=False)                   # a latency change must fail
                self.assertLess(r["peak_dbfs"], GOLDEN_PEAK_DB[kind],
                                "%s: residual against the golden (%s) - regenerate only with a changelog line (D.3.5)" % (sc.stem, kind))


class MustDo(Timed):
    """The brief's must_do list, one test each. These are `fast`: they are what breaks a
    friend's session, and they run on every build."""

    def test_range_zero_nulls_in_every_mode(self):      # must_do: "Null at Range 0 dB in every mode"
        path, _, _ = material("phrase")
        for mode, limit in (("Wide", -110.0), ("Split", -110.0), ("Spectral", -100.0)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                out = Path(d) / "y.wav"
                flags = plain("null" + mode, mode=("Wide", "Split", "Spectral").index(mode),
                              range=0.0, autoLearn=0)
                res = K.render(HARNESS, None, **dict(DEFAULT, **flags), **{"in": str(path), "out": str(out)})
                y, fs = K.read_wav(out)
                x, _ = K.read_wav(path)
                lat = res["applied"]["latency_samples"]
                n = min(len(y) - lat, len(x))
                r = K.null_residual(x[:n], y[lat:lat + n], align=False)
                self.assertLess(r["peak_dbfs"], limit,
                                "%s: Range 0 must give the input back (residual %.1f dBFS)"
                                % (mode, r["peak_dbfs"]))

    def test_bypass_nulls_latency_compensated(self):                       # rule 7
        path, _, _ = material("phrase")
        for mode in ("Split", "Spectral"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as d:
                out = Path(d) / "y.wav"
                flags = plain("byp" + mode, mode=("Wide", "Split", "Spectral").index(mode),
                              bypass=1, autoLearn=0)
                res = K.render(HARNESS, None, **dict(DEFAULT, **flags), **{"in": str(path), "out": str(out)})
                y, fs = K.read_wav(out)
                x, _ = K.read_wav(path)
                lat = res["applied"]["latency_samples"]
                n = min(len(y) - lat, len(x))
                r = K.null_residual(x[:n], y[lat:lat + n], align=False)
                self.assertLess(r["peak_dbfs"], -110.0)

    def test_zero_latency_in_wide_and_split(self):      # must_do: "Zero latency ... with Lookahead 0"
        for mode in (0, 1):
            with self.subTest(mode=mode):
                res = run(**plain("lat%d" % mode, mode=mode, lookahead=0.0, autoLearn=0),
                          seconds=0.2)
                self.assertEqual(res["applied"]["latency_samples"], 0)

    def test_reported_latency_equals_measured(self):                       # rule 7
        for mode in (0, 1, 2):
            for look in (0.0, 1.5, 5.0):
                with self.subTest(mode=mode, lookahead=look), tempfile.TemporaryDirectory() as d:
                    out = Path(d) / "imp.wav"
                    res = run(signal="impulse", out=out, seconds=0.2,
                              **plain("l%d_%g" % (mode, look), mode=mode, lookahead=look,
                                      range=0.0, autoLearn=0))
                    x, fs = K.read_wav(out)
                    ref = x[:, :1] * 0.0
                    ref[0, 0] = 1.0
                    self.assertEqual(K.latency_samples(ref, x[:, :1]),
                                     res["applied"]["latency_samples"])


class DefiningFeatures(Timed):
    """Rule 13: one presence test per defining feature of `docs/brief.md`. Each was shown
    failing on a build without the feature (D.3.8) before it was trusted - the notes in
    docs/failures.md say how."""
    label = "render"

    def _band_db(self, x, fs, f0, bw_oct, t0, t1):
        import numpy as np
        seg = np.asarray(x)[int(t0 * fs):int(t1 * fs)]
        mono = seg[:, 0] if seg.ndim > 1 else seg
        X = np.fft.rfft(mono)
        f = np.fft.rfftfreq(len(mono), 1.0 / fs)
        sel = (f >= f0 * 2 ** (-bw_oct / 2)) & (f <= f0 * 2 ** (bw_oct / 2))
        e = 2.0 * float(np.sum(np.abs(X[sel]) ** 2)) / len(mono) ** 2
        return 10 * math.log10(e) if e > 0 else -400.0

    def test_split_reduces_the_band_and_leaves_the_rest(self):
        """defining_features: "Split mode ... only the band, phase-coherent"."""
        path, lab, _ = material("burst_pair")
        s0, s1 = lab["s"]
        with tempfile.TemporaryDirectory() as d:
            dry, wet = Path(d) / "dry.wav", Path(d) / "wet.wav"
            K.render(HARNESS, None, **dict(DEFAULT, **plain("sd", mode=1, range=0.0, autoLearn=0)),
                     **{"in": str(path), "out": str(dry)})
            K.render(HARNESS, None, **dict(DEFAULT, **plain("sw", mode=1, range=8.0,
                                                            threshold=-33.0, speed=0, autoLearn=0)),
                     **{"in": str(path), "out": str(wet)})
            xd, fs = K.read_wav(dry)
            xw, _ = K.read_wav(wet)
            at7 = self._band_db(xw, fs, 7000.0, 1 / 3, s0, s1) - self._band_db(xd, fs, 7000.0, 1 / 3, s0, s1)
            at2 = self._band_db(xw, fs, 2000.0, 1 / 3, s0, s1) - self._band_db(xd, fs, 2000.0, 1 / 3, s0, s1)
            self.assertLess(at7, -6.0, "the band at 7 kHz is not reduced (%.2f dB)" % at7)
            # 2 kHz may only move by the bell's own skirt. For an 8 dB cut at 7 kHz with
            # Width 1.2 the designed value is 0.29 dB, so anything past 0.5 dB means the
            # band is not where Width says it is.
            import less_s as P
            designed = -20 * math.log10(1.0 / float(P.bell_magnitude(2000.0, 7000.0,
                                                                     P.q_for_bandwidth(1.2),
                                                                     10 ** (-8.0 / 20))))
            self.assertLess(abs(at2), max(0.5, abs(designed) + 0.2),
                            "2 kHz moved by %.2f dB; the bell's skirt there is %.2f dB"
                            % (at2, -abs(designed)))

    def test_ess_map_counts_the_esses_and_not_the_breaths(self):
        """defining_features: "Ess map: every caught ess as a bar of its depth"; brief
        other: "13 esses in the test phrase give 13 events, none on breaths"."""
        path, lab, x = material("phrase")
        import less_s as P
        import measure as Q
        # The threshold a user sets from the histogram: the median *peak* band level inside
        # the esses, less what the gain law needs to reach Range, less a margin
        # (measure.threshold_for, so the suite and the design use one derivation).
        _, info = P.render(x, 48000.0, range_db=0.0, auto_learn=False)
        thr = Q.threshold_for(info.band_db, 48000.0, lab["ess"], 10.0)
        seconds = len(x) / 48000.0          # the whole phrase, or the later esses never play
        res = K.render(HARNESS, None,
                       **{**DEFAULT, **plain("em", range=10.0, threshold=thr, speed=0, autoLearn=0),
                          "seconds": seconds},
                       **{"in": str(path)})
        events = res["product"]["ess_events"] or []   # the JSON holds null for an empty list
        for e in events:
            on_breath = any(e["start_s"] + e["duration_s"] > b0 and e["start_s"] < b1
                            for b0, b1 in lab["breath"])
            self.assertFalse(on_breath, "an event at %.3f s sits on a breath" % e["start_s"])
            on_f = any(e["start_s"] + e["duration_s"] > f0 and e["start_s"] < f1
                       for f0, f1 in lab["f"])
            self.assertFalse(on_f, "an event at %.3f s (%.2f dB) sits on an /f/ burst"
                             % (e["start_s"], e["depth_db"]))
        # every labelled ess gets exactly one bar, which is a stronger statement than the
        # count alone: 13 events could be 12 esses and one /f/
        for s0, s1, _ in lab["ess"]:
            hits = [e for e in events if e["start_s"] + e["duration_s"] > s0 and e["start_s"] < s1 + 0.06]
            self.assertEqual(len(hits), 1, "the ess at %.3f s got %d events" % (s0, len(hits)))
        self.assertEqual(len(events), len(lab["ess"]),
                         "%d events for %d esses" % (len(events), len(lab["ess"])))
        self.assertGreater(res["product"]["ess_events_at_range"], 0,
                           "no event reached the Range ceiling, so the red tick is untested")

    def test_histogram_band_level_tracks_the_detector(self):
        """defining_features: "Band-level histogram with the Threshold line"; the number
        the strip bins is product.band_level_db."""
        path, lab, _ = material("burst_pair")
        loud = K.render(HARNESS, None, **{**DEFAULT, **plain("h1", range=0.0, autoLearn=0), "seconds": 0.45},
                        **{"in": str(path)})
        quiet = K.render(HARNESS, None, **{**DEFAULT, **plain("h2", range=0.0, autoLearn=0), "seconds": 0.9},
                         **{"in": str(path)})
        self.assertGreater(loud["product"]["band_level_db"], quiet["product"]["band_level_db"] + 20.0,
                           "the band level does not fall between the bursts, so the histogram "
                           "would show one hump where there are two")

    def test_learn_finds_the_band_once(self):
        """must_do: "Auto finds Frequency and Width once (Learn), then leaves the knobs";
        brief other: "Frequency lands 6.5-8.5 kHz on the female test phrase; silence moves
        nothing"."""
        path, _, x = material("phrase")
        # The whole phrase, not three seconds of it: Learn captures two seconds of audio
        # *above the gate* (sketch 4.2), and the phrase has a gap between every syllable,
        # so three seconds of material hold well under two seconds of speech. A 3 s render
        # reported `sibilant_frames: 0` - the window had never filled.
        res = K.render(HARNESS, None,
                       **{**DEFAULT, **plain("lrn", frequency=4000.0, autoLearn=1),
                          "seconds": len(x) / 48000.0},
                       **{"in": str(path)})
        learn = res["product"]["learn"]
        self.assertTrue(learn["found"], "Learn found nothing on a phrase with 13 esses")
        self.assertGreaterEqual(learn["frequency_hz"], 6500.0)
        self.assertLessEqual(learn["frequency_hz"], 8500.0)
        self.assertGreaterEqual(learn["width_oct"], 0.6)
        self.assertLessEqual(learn["width_oct"], 2.0)
        silent = run(signal="silence", seconds=3.0, **plain("lrn0", frequency=4000.0, autoLearn=1))
        self.assertFalse(silent["product"]["learn"]["found"], "silence moved the knobs")

    def test_relative_threshold_follows_a_20_db_level_change(self):
        """must_do: "Relative threshold follows the singer across a 20 dB level change"."""
        import numpy as np
        depths = []
        _, _, x = material("phrase")
        for level_db in (-30.0, -10.0):
            scaled = np.asarray(x) * 10 ** ((level_db - (-14.0)) / 20)
            p = Path(_PRESET_DIR) / ("rel%g.wav" % level_db)
            K.write_wav(p, scaled, 48000.0)
            res = K.render(HARNESS, None,
                           **{**DEFAULT, **plain("rel%g" % level_db, relative=1, threshold=-6.0,
                                                 range=12.0, autoLearn=0),
                              "seconds": len(x) / 48000.0},
                           **{"in": str(p)})
            events = res["product"]["ess_events"] or []
            self.assertTrue(events, "no ess was caught at %g dBFS, so there is nothing to "
                                    "compare: Relative did not fire at all" % level_db)
            depths.append(max(e["depth_db"] for e in events))
        self.assertLess(abs(depths[0] - depths[1]), 1.0,
                        "20 dB of input level changed the reduction by %.2f dB" % abs(depths[0] - depths[1]))


class NullAgainstPrototype(Timed):
    """G5: the port against `sound design/proto/less_s.py`, the signed-off design.

    The prototype is float64 and the port float32 with recursive filter state, so the
    threshold is F.8's "same structure, same arithmetic order, float with long IIR or
    feedback state": peak under -100 dBFS. A residual that tracks the signal envelope
    would be a gain difference, one rising with frequency a filter-structure difference,
    one in the first samples a state-initialisation difference (F.8)."""
    label = "render"

    def _null(self, mode, **params):
        import less_s as P
        fs = 48000.0
        src, _, full = material("phrase")
        del src
        x = full[:int(2.0 * fs)]            # float32 values, the ones the harness will read
        path = Path(_PRESET_DIR) / "null-in.wav"
        K.write_wav(path, x, fs)
        ref, info = P.render(x, fs, block=512, mode=mode, auto_learn=False, **params)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "port.wav"
            names = dict(range_db="range", lookahead="lookahead", threshold="threshold",
                         frequency="frequency", width="width", mix="mix", speed="speed",
                         relative="relative", listen="listen", stereo="stereo")
            flags = plain("n%d" % mode, mode=mode, autoLearn=0,
                          **{names[k]: (int(v) if isinstance(v, bool) else v) for k, v in params.items()})
            res = K.render(HARNESS, None, **{**DEFAULT, **flags, "seconds": 2.0},
                           **{"in": str(path), "out": str(out)})
            got, _ = K.read_wav(out)
        self.assertEqual(res["applied"]["latency_samples"], info.latency,
                         "the port reports %d samples of latency, the prototype %d"
                         % (res["applied"]["latency_samples"], info.latency))
        n = min(len(got), len(ref))
        r = K.null_residual(ref[:n], got[:n], align=False)
        return r

    def test_null_split(self):
        r = self._null(1, range_db=8.0, threshold=-33.0)
        self.assertLess(r["peak_dbfs"], -100.0, "Split residual %.1f dBFS peak, %.1f RMS"
                        % (r["peak_dbfs"], r["residual_dbfs"]))

    def test_null_wide(self):
        r = self._null(0, range_db=8.0, threshold=-33.0)
        self.assertLess(r["peak_dbfs"], -100.0, "Wide residual %.1f dBFS peak, %.1f RMS"
                        % (r["peak_dbfs"], r["residual_dbfs"]))

    def test_null_spectral(self):
        # juce::dsp::FFT is float; the prototype's numpy transform is double, so the
        # Spectral residual is dominated by the transform's own precision
        r = self._null(2, range_db=8.0, threshold=-33.0)
        self.assertLess(r["peak_dbfs"], -90.0, "Spectral residual %.1f dBFS peak, %.1f RMS"
                        % (r["peak_dbfs"], r["residual_dbfs"]))

    def test_null_relative_and_mix(self):
        r = self._null(1, range_db=12.0, threshold=-6.0, relative=True, mix=50.0)
        self.assertLess(r["peak_dbfs"], -100.0, "Relative/Mix residual %.1f dBFS peak, %.1f RMS"
                        % (r["peak_dbfs"], r["residual_dbfs"]))


class PresetBank(Timed):
    """F.14.3 and the release gate's `presetlint render` line, for an effect (EX-3).

    `presetlint render` drives an effect with the harness's default impulse, so its loudness,
    true-peak and click figures are the impulse's. These tests render every row of presets.csv
    the way a friend uses it - the test phrase through the preset - and judge the bank on that.
    The CPU per preset is `perf.py run --presets all`, the release gate's own row."""
    label = "render"
    SPREAD_LU = 1.0          # Tier P: every preset within +/-1 LU of the bank median (F.14.3)
    CEILING_DBTP = -1.0      # the phrase peaks at -8.5 dBTP; a de-esser only takes away
    CLICK_PEAK_DBFS = -70.0  # time-domain peak above the band; bank -79.4 at worst, a stepped gain -53 at best

    @staticmethod
    def _bank():
        import csv
        from xml.etree import ElementTree as ET
        with open(REPO / "presets.csv", newline="") as f:
            slugs = [r["slug"] for r in csv.DictReader(f)]
        values = {}
        for slug in slugs:
            root = ET.parse(REPO / "presets" / (slug + ".oberlipreset")).getroot()
            values[slug] = {p.get("id"): float(p.get("value")) for p in root.iter("PARAM")}
        return slugs, values

    def _render(self, slug, src, out, seconds, **flags):
        res = K.render(HARNESS, None, **{**DEFAULT, "preset": slug, "seconds": seconds},
                       **{"in": str(src), "out": str(out)}, **flags)
        K.assert_echo(res, None, preset=slug)                              # rule 13
        return res

    def test_every_preset_is_healthy_and_level_matched(self):
        """NaN/Inf 0, no clipped sample, true peak under the ceiling, integrated LUFS within
        +/-1 LU of the bank median - Init included: Less S's Init is a working setting."""
        import statistics
        path, _, x = material("phrase")
        seconds = len(x) / 48000.0
        slugs, _ = self._bank()
        lufs = {}
        with factory_bank(), tempfile.TemporaryDirectory() as d:
            for slug in slugs:
                with self.subTest(preset=slug):
                    out = Path(d) / (slug + ".wav")
                    res = self._render(slug, path, out, seconds)
                    y, fs = K.read_wav(out)
                    self.assertEqual(res["health"]["nan"] + res["health"]["inf"], 0, "%s: NaN/Inf" % slug)
                    self.assertEqual(res["health"]["clipped_samples"], 0, "%s: clipped samples" % slug)
                    tp = K.true_peak_dbtp(y, fs)
                    self.assertLess(tp, self.CEILING_DBTP, "%s: true peak %.2f dBTP" % (slug, tp))
                    lufs[slug] = K.integrated_lufs(y, fs)
        med = statistics.median(lufs.values())
        print("\n    bank median %.2f LUFS; " % med
              + ", ".join("%s %+.2f" % (s, v - med) for s, v in lufs.items()), end="")
        for slug, v in lufs.items():
            self.assertLess(abs(v - med), self.SPREAD_LU,
                            "%s is %+.2f LU from the bank median (Tier P allows +/-%.1f)"
                            % (slug, v - med, self.SPREAD_LU))

    def test_no_preset_clicks_when_it_works(self):
        """No click: a raised-cosine burst train at the preset's own Frequency, so its detector
        fires and its gain moves. A gain step is broadband; smooth ballistics only put
        sidebands next to the tone. So the output, brick-wall high-passed above
        max(12 kHz, 1.7 x Frequency), must peak under CLICK_PEAK_DBFS in the *time domain*,
        against an input whose own peak there is under -120 dBFS.

        Time domain, not the FFT bin the brief's sideband figure uses: a click's energy is
        spread over every bin, so a planted 0.25-step gain read under -90 dBFS per bin and
        passed. Measured (2026-11-02, arm64): the bank peaks at -79.4 dBFS at worst (Spoken
        Word), the stepped-gain build at -53.0 to -42.5 on every time-domain preset.
        (`max_click_db` cannot judge this either: the phrase's noise esses read -0.2 dB dry.)"""
        import numpy as np
        slugs, values = self._bank()
        fs, n = 48000.0, 48000
        t = np.arange(n) / fs
        phase = (t * 4.0) % 1.0                               # 4 bursts a second, 125 ms each, like esses
        gate = np.where(phase < 0.5, 0.5 - 0.5 * np.cos(2 * np.pi * phase / 0.5), 0.0)
        f = np.fft.rfftfreq(n, 1.0 / fs)

        def hf_peak_dbfs(x, fc):
            X = np.fft.rfft(x, n)
            X[f <= fc] = 0.0
            return 20 * math.log10(float(np.max(np.abs(np.fft.irfft(X, n)))) + 1e-30)

        peaks = {}
        with factory_bank(), tempfile.TemporaryDirectory() as d:
            for slug in slugs:
                with self.subTest(preset=slug):
                    f0 = values[slug]["frequency"]
                    fc = max(12000.0, 1.7 * f0)
                    mono = np.sin(2 * np.pi * f0 * t) * gate * 10 ** (-12.0 / 20)
                    src = Path(d) / ("burst-%s.wav" % slug)
                    K.write_wav(src, np.stack([mono, mono], axis=1), fs)
                    x32, _ = K.read_wav(src)
                    floor = hf_peak_dbfs(x32[:, 0], fc)
                    self.assertLess(floor, -120.0, "%s: the test signal's own floor is %.1f dBFS" % (slug, floor))
                    out = Path(d) / ("y-%s.wav" % slug)
                    self._render(slug, src, out, 1.0)
                    y, _ = K.read_wav(out)
                    # the gain must have moved, or nothing was tested. Not the ess-map count:
                    # with Natural's or Smooth's release the reduction never falls back between
                    # bursts 125 ms apart, so the one event stays open until the input stops
                    taken = K.rms_dbfs(x32) - K.rms_dbfs(y[:n])
                    self.assertGreater(taken, 1.0, "%s: took %.2f dB off the bursts, so the gain "
                                                   "never moved and nothing was tested" % (slug, taken))
                    peaks[slug] = hf_peak_dbfs(y[:n, 0], fc)
                    self.assertLess(peaks[slug], self.CLICK_PEAK_DBFS,
                                    "%s: peaks at %.1f dBFS above %.0f Hz while the gain moves (a click)"
                                    % (slug, peaks[slug], fc))
        print("\n    peak above the band: " + ", ".join("%s %.1f" % kv for kv in peaks.items()), end="")

    def test_every_preset_round_trips_its_state(self):
        """D.5.3 per preset: state out, in, out is bytewise identical and the render after the
        load is bit-identical to the preset's own."""
        path, _, _ = material("phrase")
        slugs, _ = self._bank()
        with factory_bank(), tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for slug in slugs:
                with self.subTest(preset=slug):
                    self._render(slug, path, d / "a.wav", 1.0, state_out=d / "a.state")
                    res = K.render(HARNESS, None, **{**DEFAULT, "seconds": 1.0},
                                   **{"in": str(path), "out": str(d / "b.wav"),
                                      "state_in": d / "a.state", "state_out": d / "b.state"})
                    self.assertEqual((d / "a.state").read_bytes(), (d / "b.state").read_bytes(),
                                     "%s: the state changed on load and save" % slug)
                    xa, _ = K.read_wav(d / "a.wav")
                    xb, _ = K.read_wav(d / "b.wav")
                    self.assertTrue(xa.shape == xb.shape and (xa == xb).all(),
                                    "%s: the render after the state load differs" % slug)
                    self.assertEqual(res["health"]["nan"], 0)


# CTest registration (CMakeLists.txt of the project):
#   add_test(NAME py-fast   COMMAND ${Python3_EXECUTABLE} tools/tests/test_template.py --label fast)
#   add_test(NAME py-render COMMAND ${Python3_EXECUTABLE} tools/tests/test_template.py --label render)
#   set_tests_properties(py-fast PROPERTIES LABELS "fast" TIMEOUT 60 ENVIRONMENT "HARNESS=$<TARGET_FILE:MyPluginHarness>")
#   set_tests_properties(py-render PROPERTIES LABELS "render" TIMEOUT 600 ENVIRONMENT "HARNESS=$<TARGET_FILE:MyPluginHarness>")
# Then: ctest -L fast (inner loop), ctest -L render, ctest -LE validation.

if __name__ == "__main__":
    label = None
    if "--label" in sys.argv:
        i = sys.argv.index("--label")
        label = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    if label:
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for cls in (Contract, RateAndBlock, Health, Properties, MustDo, Goldens,
                    DefiningFeatures, NullAgainstPrototype, PresetBank):
            if cls.label == label:
                suite.addTests(loader.loadTestsFromTestCase(cls))
        t0 = time.time()
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        dt = time.time() - t0
        print("label %s: %.0f s" % (label, dt))
        sys.exit(0 if result.wasSuccessful() and (label != "fast" or dt < 3.0 * FAST_BUDGET_S) else 1)
    unittest.main(verbosity=2)
