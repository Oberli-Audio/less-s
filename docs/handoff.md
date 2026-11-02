# Handoff: from the cloud session to Visual Studio

Less S is at **G6**. G0-G5 are closed with evidence (`docs/status.md`); what is left needs
the validators, the hosts and Björn's own machines, which a Linux cloud container does not
have. This file is the prompt for the session that takes it from here, plus the context that
prompt assumes.

Branch: `claude/less-s-oberli-audio-af2rb9`. Pull it, do not start from `main`.

---

## The prompt

Paste this into the Claude session in Visual Studio (or VS Code), with the repository open:

```
Take over Less S (Oberli Audio, de-esser) at gate G6. Tier P.

Read first, in this order: CLAUDE.md, docs/status.md (the whole file - the gates table, the
metric table, the three open exceptions and the Waiting for Björn list), docs/brief.md,
docs/failures.md. Then load sound-design-bob; load ship-bob when you reach the release gate
and plugin-ui-bob when the editor lands. State the tier and the gate at the start of every
answer.

What is done: G1-G5. The DSP is ported and nulls against the signed-off numpy design to
-145 dBFS or better in all three modes (sound design/proto/less_s.py is the reference, not a
sketch - it is the G5 null reference and the suite drives it). `ctest --preset all` is 5 of 5
on Linux. The 9-preset factory bank exists. The editor is still the template's generic stub,
on purpose: the shared Source/oberli/ code is not in plugin-template yet.

Your job, in order:

1. Build and re-run the evidence on this machine, and say whether it agrees with
   docs/status.md:
       cmake --preset release && cmake --build --preset release
       ctest --preset all
   On Windows the malloc trap is the real-time check (sound-design-bob rule 1, D.1.6); on the
   Mac use the rtsan preset where LLVM 20+ is available. Record what you ran.

2. Finish the one piece of G5 that is still open, EX-3 in docs/status.md: `presetlint render`
   cannot check an effect's bank (it drives it with the harness's default impulse, so its
   true-peak and click figures are the impulse's). Write `class PresetBank` in
   tools/tests/test_plugin.py, label "render": for every row of presets.csv, render the test
   phrase through the preset and assert NaN/Inf 0, no clipped samples, true peak under
   -1 dBTP, no click, integrated LUFS within +/-1 LU of the bank median, and a bytewise state
   round trip. Use the `plain()`, `factory_bank()` and `material()` helpers that are already
   in that file. Show it failing on a deliberately broken preset before you trust it
   (rule 13), and add the row to docs/failures.md.

3. Run the unattended part of the release gate and fix what it finds:
       python3 scripts/dsp-kit/validate_plugin.py full
       python3 scripts/dsp-kit/paramgen.py check parameters.csv --manual docs/parameters.md
   plus pluginval L10 on the signed binary, the Steinberg validator, and `auval` on the Mac.
   The format set is ship.toml's.

4. Measure the CPU row on the machine the brief is written for (an M3 Pro), not on CI:
       python3 scripts/dsp-kit/perf.py run --harness <harness> --arch x86_64
   one row at 48 k/64, three runs, on the heaviest preset (Studio Spectral 2 ms). Rule 20:
   p99.9 under 25 %, recurring max under 50 %, idle under 2 %; report `over_deadline`, do not
   judge it. Replace the placeholder CPU line in docs/status.md with the real numbers.

5. Stop and ask Björn for: the listening checkpoint (the renders and what to listen for are
   in docs/status.md under Listening debt; `python3 "sound design/proto/render_references.py"`
   writes them), the two Ableton host checks, and a decision on each line of Waiting for
   Björn - the two that touch the sketch are Split's filter structure and the Spectral window
   size, and both are decided by measurements that are already in the repo.

Rules for you, from the kickoff: pass a gate on your own when its evidence is green and log
it in docs/status.md with the command behind every number. Stop for Björn only for listening
checkpoints, the Ableton host checks, a conflict with a structural decision in docs/sketch.md,
and before any release. Everything that needs him goes in "Waiting for Björn" at the top of
docs/status.md, one line each, newest first; keep working on whatever is not blocked.
Never write your own version of the shared Source/oberli/ code and never edit bob-skills or
scripts/dsp-kit (they are byte copies of the kit - report a kit bug instead; there are already
three in the list). Commit and push to claude/less-s-oberli-audio-af2rb9 at every checkpoint.
```

---

## Context that prompt assumes

### What was built
- `Source/dsp/` - the port, by structure from the prototype, class for class:
  `Svf.h` (TPT state-variable filter), `Dynamics.h` (one-pole, level follower, gain computer,
  ballistics, delay line), `Stft.h` (Hann WOLA, window in seconds), `Learn.h` (the band
  finder, off the audio thread), `Constants.h` (**every** DSP constant with the reason it has
  that value), `Engine.h` (the whole signal flow).
- `Source/PluginProcessor.*` - parameters in, meters out, reported latency, the Learn timer.
  It does nothing to the audio itself.
- `sound design/proto/` - `less_s.py` (the design, and the G5 null reference), `material.py`
  (seeded labelled test material), `measure.py` (82 checks, the G3 artefact),
  `g1_structure.py` (the G1 evidence), `render_references.py` (the listening renders).
- `tools/tests/test_plugin.py` - the suite: the template's contract tests plus `MustDo`
  (the brief's must_do list), `DefiningFeatures` (one presence test per defining feature) and
  `NullAgainstPrototype` (G5).
- `tools/harness/Main.cpp` - the product hooks are filled in: `--solo=band|delta` and a
  `product` object carrying the gain reduction, the band level, the drained ess map and the
  Learn result.

### What the editor needs, and already has
The DSP publishes everything the sketch's display asks for, so the editor is wiring, not DSP:
- `gainReductionDb()` - the GR meter.
- `bandLevelDb()` - the number the histogram strip bins; it is dB **relative** when Relative
  is on, which is what makes the two humps separate.
- `popEssEvent()` - the ess map, a lock-free ring of `{startSeconds, durationSeconds,
  depthDb, hitRange}`; `hitRange` is the red tick.
- `lesss::dsp::k::detectorMagnitude()` and `bellMagnitude()` - draw the detection band and
  the curve from these, never from a formula of the editor's own (rule 9). For the band's
  **digital** response near Nyquist use the filters themselves, as
  `less_s.detector_response()` does in the prototype: at 14 kHz and 48 kHz the analog
  prototype says -9.8 dB where the real filter rejects -15.4.
- `requestLearn()` - the Learn button under the Frequency knob.

### Three things to be careful about
1. **`scripts/dsp-kit/` and `scripts/ship/` are byte copies of the kit.** Three bugs were
   found in them (listed in docs/status.md); each is worked around in this repo's own files
   and reported, never patched in place.
2. **The prototype and the port must stay nulled.** Any change to the DSP changes both or it
   changes neither; `ctest -R suite_render` is the check. A change that is meant to alter the
   sound needs a `Sounds different:` changelog line and a new golden (ship-bob).
3. **Every number in docs/status.md has a command next to it.** Keep it that way; a number
   without the command that produced it is not evidence.
