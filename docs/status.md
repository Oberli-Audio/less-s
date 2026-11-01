# Status - Less S 0.1.0 (2026-11-01)
Tier P, track E (effect), at gate G6. Recipe D.8.1.

G1 to G5 are closed with evidence; G6 needs the validators and the two hosts, which only
exist on Björn's machines. Everything was built in a Linux cloud container, so every number
below comes from an x86_64 Linux Release build - the sound numbers carry over, the CPU row
does not (see Waiting for Björn).

## Waiting for Björn
One line each, newest first. Nothing here blocks the rest of the work.

- 2026-11-01: **G6 needs your machines.** pluginval L10, the Steinberg validator, `auval`,
  Plugalyzer, the arm64 smoke test and the two-host list (Live 10.1 under Rosetta, Live on
  Windows) cannot run in a Linux container. `docs/handoff.md` has the prompt for the
  Visual Studio session that takes it from here.
- 2026-11-01: **The CPU row is not Björn's machine.** On this container at 48 k/64 the
  figures are p50 1.5 %, p99 4.5 %, p99.9 10.1 %, max 100.7 %, `over_deadline` 1 (reported,
  not judged - an offline normal-priority harness gets preempted). The brief's budget is
  written for an M3 Pro, so `perf.py run --harness ... --arch x86_64` has to be re-run there
  on the heaviest preset (Studio Spectral 2 ms) before the release gate can be called green.
- 2026-11-01: **Three kit bugs found, none fixable here** (`scripts/dsp-kit/` is a byte copy
  of the kit; a skills-bob item each):
  1. `paramgen.py check` accepts a C++ keyword as an id. `auto` passed the lint and the
     generated `Params.h` would not compile. Suggested fix: reject the C++ keyword list.
  2. `dspkit.assert_echo` compares the echo to the request **as a string**, so
     `sample_rate=48000` against a JUCE double echo of `48000.0` fails - `dspkit.py smoke`
     fails for any product. Worked around in `tools/harness/Main.cpp` by echoing an integral
     rate as an integer. Suggested fix: compare numerically.
  3. `presetlint.py` `check_init` compares the harness's **normalised** echo against the
     **plain** choice index, so any `choice` whose default is neither first nor last reads as
     an error (Less S: Mode 1 of 3, Speed 1 of 3). And `presetlint render` has no way to give
     an effect an input signal, so it drives one with the harness's default impulse and then
     measures the impulse: true peak -0.0 dBTP and `max_click_db` 0.0 dB for every preset.
     Suggested fix: `fdefault / (steps - 1)` for choices, and an `--in`/`--signal` passthrough.
     See EX-3.
- 2026-11-01: **No real vocal material.** Every number comes from the seeded synthetic
  phrase in `sound design/proto/material.py` (13 labelled esses, 2 breaths, 3 /f/ bursts).
  It is reproducible and labelled, which is why the ess-map and selectivity targets are
  testable at all, but it is not a voice. The listening checkpoint needs the OneDrive
  material: a sibilant female and male phrase.
- 2026-11-01: **Listening checkpoint due.** `python3 "sound design/proto/render_references.py"`
  writes eight files to `sound design/renders/` (gitignored) with what to listen for in each.
  Nothing has been heard yet.
- 2026-11-01: **Spectral STFT size.** The sketch says "STFT 512/4x". A WOLA's algorithmic
  delay is the window once the partial hop a host's block sizes force you to carry is
  included, so 512 measures **512** samples of latency and the brief's `latency_budget` for
  Spectral is 256. Less S uses a 5.33 ms window: 256 samples at 48 kHz - the budget exactly -
  512 at 96 kHz, 1024 at 192 kHz, so the behaviour in time is the same at every rate.
  Confirm, or raise the budget to 512 and I switch back.
- 2026-11-01: **Split mode's filter structure.** The sketch's structural decision 1 names an
  LR4 three-way split. Measured (`python3 "sound design/proto/g1_structure.py"`): an LR4 split
  sums to an *allpass*, not to the input, so at Range 0 the residual against the input peaks
  at **-0.7 dBFS** (RMS -42.5) - the brief's `must_do` "Null at Range 0 dB in every mode" and
  the sketch's own acceptance test 1 cannot both hold with LR4. At band gain -8 dB it also
  delivers only -5.4 dB at 7 kHz instead of -8. Less S applies the band gain in the
  **parallel form** `y = x + (G-1)*BP(x)` (dsp-reference-bob E.2): exact null at Range 0,
  -8.00 dB at the centre, no crossover phase modulation, and *narrower* at 4 kHz than the
  LR4 split was (-1.63 against -2.05). Mode name and meaning unchanged. Confirm the wording.
- 2026-11-01: **Parameter id `auto` renamed to `autoLearn`.** `auto` is a C++ keyword, so the
  generated `Source/Params.h` could not compile. The user-facing name stays "Auto"; no release
  and no tag exists, so no ID freeze is broken (rule 19).
- 2026-11-01: **Shared editor code is missing.** `Source/oberli/` (LookAndFeel, Strip frame,
  meters, Loudness, Analysis/FFT, References, RenderSafety) is not in `plugin-template` yet.
  The editor is still the template's generic stub - every parameter as a plain rotary - with
  the accent corrected to sage. The DSP publishes everything the real editor needs:
  `gainReductionDb()`, `bandLevelDb()` (the histogram's number, dB relative when Relative is
  on) and `popEssEvent()` (the ess map, a lock-free ring). Refresh `Source/oberli/` from the
  template, then plugin-ui-bob wires it.
- 2026-11-01: **Faust is not installed in this container.** The G2 prototype is a numpy model,
  which F.15.1 allows for an effect (and asks for anyway for the STFT stage). No `.dsp` file
  exists for Less S; `sound design/proto/less_s.py` is the signed-off design and the G5 null
  reference.

## Gates
| Gate | State | Evidence (command -> number, test name, log) |
|---|---|---|
| G0 | closed 2026-11-01 | `docs/brief.md` owner-confirmed, from `docs/sketch.md` |
| G1 | closed 2026-11-01 | see Decisions; `python3 "sound design/proto/g1_structure.py"` -> LR4 null residual -0.7 dBFS FAIL, parallel bell exact PASS, -8.00 dB at the centre |
| G2 | closed 2026-11-01 | `sound design/proto/less_s.py` renders real audio; `python3 "sound design/proto/render_references.py"` -> 8 files (gitignored, OneDrive) |
| G3 | closed 2026-11-01 | `python3 -W error::RuntimeWarning "sound design/proto/measure.py"` -> **82 checks, 0 failed**; the metric table below |
| G4 | closed 2026-11-01 | `cmake --preset release && cmake --build --preset release` clean (VST3, Standalone, harness); the port is `Source/dsp/` |
| G5 | closed 2026-11-01 | `ctest --preset all` -> 5/5. `NullAgainstPrototype`, peak / RMS of the residual, no alignment, lag 0 in all four: Split **-148.9 / -173.0**, Wide **-162.4 / -180.4**, Spectral **-144.5 / -165.5**, Relative+Mix **-150.2 / -175.6** dBFS. F.8 asks for < -100 (float with recursive state); the port is two orders of magnitude inside it because the filters are double and only the buffers are float, so the residual sits at the float output's own quantisation. Two goldens in `tools/tests/golden/` |
| G6 | open | `ctest --preset all` -> 5/5 here. Still to run on Björn's machines: `validate_plugin.py full`, `paramgen.py check --frozen`, pluginval L10, the Steinberg validator, `auval`, Plugalyzer, arm64 smoke, Live 10.1 Rosetta + Live Windows |
| G7 | - | bank exists (9 presets, `presetlint bank` green); README, manual and notices still to write |

## Metric table (G3, on the prototype; the port is held to the same numbers by the suite)
| Target (docs/brief.md) | Command | Number | Verdict |
|---|---|---|---|
| `thd_n_db`: null at Range 0, every mode | `measure.py null` | Wide and Split exact, Spectral -319 dBFS | pass |
| bypass nulls, latency-compensated (rule 7) | `measure.py bypass` | exact in Split and Spectral | pass |
| `response_error_db`: s at 7 kHz reduced by Range | `measure.py selectivity` | Wide -7.89, Split -7.24, Spectral -7.37 dB (target -8 +/-1) | pass |
| `response_error_db`: f at 4 kHz unchanged | `measure.py selectivity` | Split -0.44, Spectral -0.51 dB (target < 0.5 +/-0.1 resolution); Wide -1.63 | pass / EX-2 |
| `other.relative`: 20 dB level change | `measure.py relative` | Relative on: 0.00 dB difference. Off: 11.87 dB, so the switch is worth flipping | pass |
| latency reported = measured, every mode and lookahead (rule 7) | `measure.py latency` | 9 of 9 exact: 0, 72, 240 samples; Spectral 256 | pass |
| `other.ess map`: 13 esses -> 13 events, none on breaths | `measure.py essmap` | 13 events, 13 on a labelled ess, 0 on a breath, 0 on an /f/, 8 at the Range ceiling | pass |
| `other.auto`: Learn lands 6.5-8.5 kHz; silence moves nothing | `measure.py learn` | female 7501 Hz / 0.85 oct, male 6088 Hz, silence no result. Port: 7460 Hz / 0.86 oct | pass |
| `alias_floor_db`: Wide gain-modulation sidebands | `measure.py sidebands` | Wide -156, Split -155 dBFS above 12 kHz (test signal's own floor -160; target < -90) | pass |
| no zipper at maximum automation rate (rule 2) | `measure.py zipper` | -64.9 dB sidebands with Frequency swept over the whole range at 10 Hz (target < -60) | pass |
| Mix does not change the level (rule 5's purpose) | `measure.py level` | 0.00 dB over Mix 0-100 % at Range 0 | pass / EX-1 |
| ballistics 10-90 % against the labels | `measure.py ballistics` | Fast 0.44 / 87.9 ms, Natural 1.08 / 416 ms (second stage), Smooth 4.40 / 332 ms | pass |
| the Ess bus is the detection band | `measure.py listen` | follows the filters' own impulse response within 1.5 dB at 2-14 kHz; 1 kHz rejected 50 dB | pass |
| Stereo modes | `measure.py stereo` | centred ess -8.8 dB in all three; Dual leaves the quiet channel at 0.00 dB; Mid leaves a pure side signal exactly | pass |
| every rate 44.1-192 kHz | `measure.py rates` | s reduced -7.2 to -7.4 dB at every rate, all finite | pass |
| block-size independence (D.5.1) | `measure.py blocks` | blocks 1, 13, 32, 64, 4096 all exact against 512 | pass |
| two seeded runs from reset are identical (rule 8) | `measure.py reset` | identical | pass |
| silence: no tail, no DC, no NaN | `measure.py silence` | tail exact, DC -120 dBFS, finite | pass |
| CPU at 48 k/64 (rule 20) | `suite_fast` | p99.9 10.1 %, max 100.7 %, over_deadline 1 | **not Björn's machine** |

## Listening debt
- 2026-11-01: **everything.** The design is measured and nulled but has never been heard.
  Run `python3 "sound design/proto/render_references.py"` and A/B, level-matched, in this
  order: `00-dry` against `10-split`; then `11-wide` against `10-split` (Wide should audibly
  duck the whole voice); `20-delta-split` must contain esses and nothing else;
  `30-over-range` is the lisp the red ticks warn about; `40/41-relative-*` must sound
  equally de-essed 20 dB apart. The material is synthetic - a real voice is the checkpoint.
- 2026-11-01: Spectral's window is 5.33 ms where the sketch said 10.7 ms. Measured as
  equivalent, not heard. The A/B is `12-spectral` against `10-split` on a /t/-heavy phrase.

## Open exceptions
- **EX-1 2026-11-01: rule 5, "wet/dry mixes equal-power".** Mix is a **linear** blend of the
  delay-compensated dry and the wet. Measured by `measure.py level`: level change over Mix
  0-100 % at Range 0 is **0.00 dB**; an equal-power crossfade would add up to **+3 dB** at
  Mix 50 %, because dry and wet here are the same voice minus a little band and are almost
  perfectly correlated - the rule's wording and the rule's stated purpose (F.2 Law 5: "so the
  level stays constant") disagree for a correlated wet path, and this keeps the purpose.
  Shipping is acceptable because the measurement is the rule's own criterion.
  **Unacceptable if** the level moves more than 0.1 dB across Mix travel, as test
  `measure.py level`. Friends: none - Mix at 50 % sounds like half the de-essing, which is
  what it says.
- **EX-2 2026-11-01: `quality_targets.response_error_db`, the /f/ in Wide mode.** The /f/ at
  4 kHz changes by **-1.63 dB** against the target of < 0.5 dB. Measured by
  `measure.py selectivity`. Shipping is acceptable because Wide applies the reduction to the
  whole signal by definition ("Wide ducks all"), so anything audible during a detection is
  ducked with it; Split - the default and the brief's defining feature - measures -0.44 dB
  and Spectral -0.51 dB. **Unacceptable if** Split or Spectral exceeds 0.6 dB, as test
  `DefiningFeatures.test_split_reduces_the_band_and_leaves_the_rest`. Friends: on a bright
  consonant, Wide dulls a little more than Split - which is the reason Split is the default.
  Re-checked when the detector's band changes.
- **EX-3 2026-11-01: `presetlint` cannot check this bank.** `presetlint bank --harness` and
  `presetlint render` report 2 and 20 errors that are not defects: `check_init` compares a
  normalised echo against a plain choice index (Mode 1 of 3, Speed 1 of 3), and
  `presetlint render` drives an effect with the harness's default impulse, so its true-peak
  (-0.0 dBTP) and click (0.0 dB) figures are the impulse's. The CMake test therefore runs
  `presetlint bank` **without** `--harness`, and the two properties it would have checked are
  verified in the suite against the plugin's own normalisation:
  `Properties.test_init_preset_equals_the_table_defaults` and
  `Properties.test_preset_listing_matches_the_csv`. **Unacceptable if** the bank's
  per-preset health and loudness spread are still unverified at the release gate: the
  remaining work is `PresetBank` in `tools/tests/test_plugin.py` (render every preset through
  the phrase: NaN, clipping, true peak, click, integrated LUFS within +/-1 LU of the median,
  state round trip). Not written yet - the next task in the handoff. `docs/presets.md` is
  generated by `presetlint render --md` and is therefore **not committed yet**: the one run
  that produced it reported a worst block of 148 % and a level of +0.0 LU for every preset,
  which are the impulse's figures, not the bank's. It belongs to G7, after this is fixed.
  Re-checked when the kit is fixed in bob-skills.

## Handoff
Task: build Less S from G1 to the release gate at Tier P.
Plan: 1. [x] G1 algorithm decision 2. [x] G2 numpy prototype 3. [x] G3 measure (82 checks)
4. [x] G4 port to C++ 5. [x] G5 null + preset bank 6. [ ] **G6 validate - needs Björn's
machines** (next) 7. [ ] G7 product (README, manual, notices, golden renders).
Working tree: clean at the commit this line ships in. Build: green (`cmake --build --preset
release`). Tests: `ctest --preset all` 5 pass / 0 fail (`suite_fast` 29 s, `suite_render` 39 s,
`harness_contract`, `parameter_table`, `preset_bank`).
Open questions for the owner: the Waiting-for-Björn list above; the two that touch the sketch
are Split's filter structure and the Spectral window.
Next command: `docs/handoff.md` - the prompt for the Visual Studio session.

## Decisions
- 2026-11-01: **G1 family.** De-esser, `dsp-selection.md` S.2 row: split-band, ~5-10 kHz with
  peak tracking, relative threshold, ~1 ms attack with look-ahead, limited range. Less S is
  **one detector, three appliers**.
  *Detector* - a 4th-order Butterworth band-pass (high-pass at the lower edge, low-pass at
  the upper one) from Frequency and Width, normalised to unity at the centre so Threshold
  means the same level at every Width; TPT SVF sections, because the band moves with the
  knobs (rule 6). This is the sketch's "24 dB/oct skirts" read literally: two resonant
  band-passes in cascade give only 12 dB/oct and leak the vowels - measured at 2 kHz with the
  default band, the Butterworth pair rejects 29 dB where the cascade rejected 16, and
  "leave 1-4 kHz untouched" is in the brief. Then peak and mean-square followers blended by
  Speed, converted to dB, the gain computer in the log domain *after* the detector (E.1's
  feed-forward recommendation, Giannoulis-Massberg-Reiss), soft knee 6 dB, ratio 4:1,
  hard-limited to Range, ballistics on the control signal in dB, dB to linear once per sample
  (rule 2).
  *Appliers* - Wide: the signal times the gain. Split: the parallel bell
  `y = x + (G-1)*BP(x)`. Spectral: STFT bins times the bell's magnitude at that gain.
  Look-ahead delays the audio only and is reported latency (rule 7).
  *Trade-off*: the parallel bell costs one band-pass per channel and buys an exact null at
  Range 0, no coefficient movement and no crossover phase modulation; it pays with a bell
  skirt instead of a brick wall, so an 8 dB cut at 7 kHz also takes 1.6 dB at 4 kHz. A
  24 dB/oct band split would be more surgical but cannot null at all (see Waiting for Björn).
- 2026-11-01: **Spectral weights bins with the bell's magnitude, not the band-pass's.**
  Weighting with `|BP|` - the obvious reading of "the gain per bin weighted by the band's
  shape" - gives a wider cut than Split has, because the bell is minimum-phase and the phase
  narrows its skirts: at 4 kHz with an 8 dB cut, `|BP|` weighting took 3.8 dB where Split
  takes 1.6. Switching Mode then changed how much a nearby /f/ was touched. The peaking-EQ
  magnitude `sqrt((1-W^2)^2 + (gW/q)^2) / sqrt((1-W^2)^2 + (W/q)^2)` makes the two modes
  agree to 0.07 dB and is still exactly 1 at g = 1, so the null holds.
- 2026-11-01: **Departure 1 - absolute threshold is the default.** S.2 marks "an absolute
  threshold" as *Not* for a de-esser and E.2 says relative by default for corrective work.
  The brief chooses `relative: 0` because a new user expects a compressor's threshold.
  Measured: with Relative on, 20 dB of input level changes the reduction by 0.00 dB; with it
  off, by 11.87 dB. The switch is worth flipping, so the default is a preference, not a
  defect. Rejected if a friend cannot reach the same result with it off.
- 2026-11-01: **Departure 2 - no peak tracking.** S.2's row says "with peak tracking"; the
  brief's `out_of_scope` says "continuous frequency tracking". Less S tracks the band once
  (Learn), because a drifting centre cannot be heard as a cause. Rejected if one Learn result
  cannot serve a whole take - Frequency must land 6.5-8.5 kHz on the female phrase (measured
  7460 Hz in the port) and the ess map must keep 13 of 13.
- 2026-11-01: **Departure 3 - the STFT window is a time, not 512 samples.** Rule 12 plus the
  brief's 256-sample budget; see Waiting for Björn. Rejected if the measured latency is not
  what the plugin reports (9 of 9 exact) or if 5.33 ms smears a /t/ audibly against 10.7 ms
  in the A/B.
- 2026-11-01: **The control block is 8 samples, not 32.** `parameters.csv` says
  `control_rate = block` and rule 2 allows up to 32, but 32 is measurable: sweeping Frequency
  over the whole range at 10 Hz puts a sideband at the update rate itself
  (7000 - 48000/32 = 5500 Hz) at -50 dB against the tone. Measured: 32 -> -50 dB, 8 -> -65 dB,
  1 -> -91 dB. 8 costs about 42k `tan()` per second for the seven filters, under 0.1 % CPU,
  and is the knee of that curve.
- 2026-11-01: **Learn runs off the audio thread.** `processBlock` only copies the sidechain
  into a buffer sized in `prepare` (rule 1); the analysis runs on the message thread (a 50 ms
  timer polls one atomic) and writes Frequency and Width through begin/perform/end edit, so
  the host records one undo step. The harness drives the same analysis after the render and
  reports it as `product.learn`, so the Auto presence test needs no host.
- 2026-11-01: **The filters are double, the buffers float.** The detector, the bell and the
  followers carry recursive state and the G5 null is measured in dBFS; float state would cost
  about 20 dB of residual for no measurable saving on two filters per channel.
- 2026-11-01: **Accent is sage #33B679**, the category accent for mix tools (was iris
  #A796F0). Owner's call, relayed with the `main` update; the registry entry in bob-skills is
  still to follow. Nothing is released, so no build carried iris.
- 2026-11-01: **Lookahead's taper warning is kept.** `paramgen.py check` warns that
  Lookahead's default sits at 0 % of travel instead of F.14.2's 40-60 %. Deliberate: the
  brief's `must_do` is zero latency at Lookahead 0, so the default must be the minimum. No
  exception line - the check warns, it does not fail.
