# Status - Less S 0.1.0 (2026-11-03)
Tier P, track E (effect), at gate G6. Recipe D.8.1.

G1 to G5 are closed with evidence and hold on Björn's Mac (M3 Pro, arm64 and the x86_64 slice
under Rosetta). G6's unattended sound side is green here: validators, RTSan, ASan + UBSan, the
CPU row, the bank (EX-3 closed). What is left of G6 needs Björn: the two hosts, a decision on
Plugalyzer, the CPU row once more on the power adapter, and the editor in a host (built
2026-11-03, measured offscreen; `docs/ui/`).

## Waiting for Björn
One line each, newest first. Nothing here blocks the rest of the work.

- 2026-11-02: **The two host checks** (release gate, "the 15-minute list per host"): Ableton
  Live 10.1 under Rosetta on this Mac and Ableton Live on a Windows machine (`tools.toml` has
  no Windows host: a friend). Install: copy `build/LessS_artefacts/Release/VST3/Less S.vst3` to
  `~/Library/Audio/Plug-Ins/VST3/`, rescan. The arm64 smoke ("the Init preset sounds") is a
  listen too: VST3 only ships, so there is no `auval`; the Standalone beside the VST3 is the
  native arm64 path.
- 2026-11-02: **Re-run the CPU row on the power adapter.** It was measured on battery (47 %,
  discharging), which D.2.1 rules out for the figure of record. It passes with room to spare -
  heaviest preset p99.9 1.5 % of the deadline - so this is a formality:
  `python3 scripts/dsp-kit/perf.py run --harness build/LessSHarness_artefacts/Release/LessSHarness --arch x86_64 --presets all --runs 3`
- 2026-11-02: **Plugalyzer is not on this Mac and not in the kit.** `tiers.md` puts the bundle
  null test with Plugalyzer at Tier P, and the brief's latency line names it, but there is no
  `tools.toml` key, no kit step and no install (nor in any sibling repo). What stands in for now:
  `bounce_null` (harness, bit-exact), `MustDo.test_reported_latency_equals_measured` (9 of 9 in
  the harness) and pluginval L10 on the shipped bundle. Decide: build Plugalyzer from source
  beside pluginval-asan and add the step to the kit (a skills-bob item), or accept the stand-ins
  for 0.1.0 as an exception line.
- 2026-11-02: **Template items found on the Mac** (skills-bob, the template; none patched in a
  byte copy):
  1. CMake's FindPython takes Homebrew's framework Python 3.12, which has no numpy or scipy, so
     the whole Python suite is silently not registered (`ctest` reports 4 of 4). a-b-see's build
     on this Mac has the same. Here: `cmake --preset release -DPython3_EXECUTABLE=/usr/bin/python3`
     (machine-local, in the build cache). Suggested fix: fail the configure loudly, or prefer
     the `python3` on PATH.
  2. The release-symbols block (Less S's own, modelled on Horizon Pad's) stripped after
     signing - arm64 kills every process that loads the bundle - and its dSYMs held no DWARF
     under LTO. Fixed here (docs/failures.md); **Horizon Pad has the same block**.
  4. Shared code: `PillToggle::getPreferredWidth` (and `type::width`) measure caps without the
     label font's 0.10 tracking, so a long word is clipped ("RELATI"). Worked around in
     `PluginEditor.cpp` (`pillWidth`); the fix belongs in `Source/oberli/Buttons.cpp`.
  5. The snapshot tool feeds noise only, so an effect whose display needs real material (the
     ess map stays empty on continuous noise) cannot be rendered as it is used. An `--in=<wav>`
     flag was added for this pass, rendered, and reverted (the tool is a template companion).
  3. `presetlint render` and `max_click_db` cannot judge an effect (EX-3, now replaced by
     `PresetBank`); the kit wants an `--in` passthrough and a click measure for effects
     (the time-domain peak above the band, `PresetBank.test_no_preset_clicks_when_it_works`).
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
- 2026-11-03: **The editor is built; look at it in a host.** `Source/PluginEditor.*` and
  `Source/SibilanceDisplay.*` on the Strip frame, from the sketch: DETECT, REDUCE, SIBILANCE
  (spectrum, band-level histogram with a draggable Threshold line, ess map), OUTPUT. Renders in
  `docs/ui/` (100, 150, 200 %). Three departures from the sketch, for you to accept or reject:
  the window is **880 x 612** (sketch 584: Learn and Auto share a row, Relative gets its own,
  because the three do not fit 232 px at real widths); the legend drops the Threshold key (the
  strip's accent line and its tooltip carry it); the ess bars are a tinted body with a solid
  accent cap instead of solid accent (rule 6: solid bars took the render to 3.0 % saturated, the
  limit is 2 %).

## Gates
| Gate | State | Evidence (command -> number, test name, log) |
|---|---|---|
| G0 | closed 2026-11-01 | `docs/brief.md` owner-confirmed, from `docs/sketch.md` |
| G1 | closed 2026-11-01 | see Decisions; `python3 "sound design/proto/g1_structure.py"` -> LR4 null residual -0.7 dBFS FAIL, parallel bell exact PASS, -8.00 dB at the centre |
| G2 | closed 2026-11-01 | `sound design/proto/less_s.py` renders real audio; `python3 "sound design/proto/render_references.py"` -> 8 files (gitignored, OneDrive) |
| G3 | closed 2026-11-01 | `python3 -W error::RuntimeWarning "sound design/proto/measure.py"` -> **82 checks, 0 failed**; the metric table below |
| G4 | closed 2026-11-01 | `cmake --preset release && cmake --build --preset release` clean (VST3, Standalone, harness); the port is `Source/dsp/`. Mac 2026-11-02: clean, universal |
| G5 | closed 2026-11-01 | `ctest --preset all` -> 5/5. `NullAgainstPrototype`, peak / RMS of the residual, no alignment, lag 0 in all four: Split **-148.9 / -173.0**, Wide **-162.4 / -180.4**, Spectral **-144.5 / -165.5**, Relative+Mix **-150.2 / -175.6** dBFS. F.8 asks for < -100 (float with recursive state); the port is two orders of magnitude inside it because the filters are double and only the buffers are float, so the residual sits at the float output's own quantisation. Two goldens in `tools/tests/golden/`. Mac 2026-11-02 (arm64, cross-slice tolerance for the x86_64 goldens): `ctest --preset all` -> 11/11. Bank: `PresetBank` (EX-3 closed) |
| G6 | open | Mac, 2026-11-02, all green: `validate_plugin.py full --plugin "build/LessS_artefacts/Release/VST3/Less S.vst3" --build-cmd "cmake --build --preset release" --test-cmd "ctest --preset all"` -> build PASS, ctest **11/11**, Steinberg validator **47/47** (SDK 3.8.1), pluginval **L10 PASS** (seed 0x48505631, all six rates). `validate_plugin.py full --sanitizer asan` on the asan build with pluginval-asan -> validator 47/47, pluginval L10 PASS. Real-time: rtsan build, `PRODUCT_RTSAN_SELFTEST=1` aborts (exit 134, "unsafe-library-call malloc"), suite under RTSan fast 16 OK (1 skip), render 13 OK. ASan + UBSan (`halt_on_error=1`): fast 16 OK, render 13 OK. `paramgen.py check parameters.csv --manual docs/parameters.md` -> OK, 13 parameters, 1 warning (Lookahead, see Decisions); `--frozen` n/a before the first release. CPU: the row below (on battery). `bundle_signature_and_symbols` green. **Still open**: the two hosts, Plugalyzer (decision), CPU on the adapter. **Interface side (2026-11-03)**: editor built; snapshot pass at 100/150/200 % (`docs/ui/`); `snapshot_contrast.py --metrics --theme bone` -> 0 metrics outside the limits at all three scales (saturated 1.62 / 1.67 / 1.69 %, 9 palette colours, nothing brighter than Bone); text contrast of the display's own labels at 2x -> legend, strip axis, frequency labels all AA (worst 4.95:1); `validate_plugin.py full` with the editor -> ctest 11/11, validator 47/47, pluginval L10 PASS (editor open/close inside); RTSan suite again clean (fast 17, render 13). Still open on the interface side: the host checks (scaling on Windows, keyboard focus, generic editor, automation from the GUI), and the analyser push is not exercised under RTSan (the harness opens no editor) |
| G7 | - | bank exists (9 presets, `presetlint bank` green, `PresetBank` green); README, manual, notices, `docs/presets.md` still to write |

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
| CPU at 48 k/64, x86_64 slice under Rosetta, M3 Pro (rule 20) | `perf.py run --harness <release harness> --arch x86_64 --presets all --runs 3` (60 s each) | heaviest preset Studio Spectral 2 ms: p50 0.9, p99 1.2, **p99.9 1.5 %**, max 6.1 % (scheduling); every preset p99.9 <= 2.3 %, every max reads as scheduling (moves between runs; one 486 % block in Female Lead Natural, over_deadline 1, reported); idle 0.6 %; first block <= 5 % | pass (**on battery**: re-run on the adapter) |

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
- **EX-3 2026-11-01, closed 2026-11-02: `presetlint` cannot check this bank.** Replaced by
  `PresetBank` in `tools/tests/test_plugin.py` (label render): every row of presets.csv renders
  the test phrase - NaN/Inf 0, no clipped sample, true peak under -1 dBTP, integrated LUFS
  within +/-1 LU of the bank median (measured: span -0.17 to +0.30 LU around -22.06 LUFS, Init
  included); no click (a raised-cosine burst train at the preset's Frequency, time-domain peak
  above max(12 kHz, 1.7 x Frequency) under -70 dBFS; bank -79.4 at worst); state round trip
  bytewise and the render after the load bit-identical. Each shown failing first
  (docs/failures.md). `presetlint bank` still runs without `--harness` (the `check_init`
  index bug stays a kit item). `docs/presets.md` (`presetlint render --md`) still carries the
  impulse's figures and belongs to G7 once the kit can feed an effect.

## Handoff
Task: build Less S from G1 to the release gate at Tier P.
Plan: 1. [x] G1 2. [x] G2 3. [x] G3 (82 checks) 4. [x] G4 5. [x] G5 + bank (EX-3 closed)
6. [ ] **G6** - sound side green on the Mac; open: hosts, Plugalyzer, CPU on the adapter, the
editor's half 7. [ ] G7 product (README, manual, notices, golden renders).
Working tree: clean at the commit this line ships in. Build: green (`cmake --preset release
-DPython3_EXECUTABLE=/usr/bin/python3 && cmake --build --preset release`). Tests: `ctest
--preset all` 11 pass / 0 fail (fast label 18 s).
Open questions for the owner: the Waiting-for-Björn list; the two that touch the sketch are
Split's filter structure and the Spectral window.
Next: Björn in a host - the editor, the two host checks, the listening checkpoint; then G7
(README, manual, notices, golden renders, `docs/presets.md` once the kit can feed an effect).

## Decisions
- 2026-11-03: **The editor's display reads the DSP, never a formula of its own** (rule 9): the
  band is drawn and its -3 dB edges found on `k::detectorMagnitude`; the histogram bins
  `bandLevelDb()`; the ess map drains the engine's event ring on the engine's clock
  (`audioSeconds()`); the spectra come from two `oberli::Analyser`s fed only while an editor is
  open and the host plays in real time (`RenderSafety`), so a bounce renders the same audio.
- 2026-11-03: **The Histogram switch is machine-local** (`MachineSettings`, key
  `lessS.histogram`), like the GUI scale: not a parameter, not in presets (sketch 4.3).
- 2026-11-02: **The click check for an effect is a time-domain peak above the band**, not
  `max_click_db` (noise esses read -0.2 dB dry) and not the brief's per-bin sideband figure (a
  click spreads over every bin; a stepped gain read under -90 dBFS per bin). Limit -70 dBFS:
  the bank measures -79.4 at worst, a stepped-gain build -53.0 at best. Rejected if a click
  audible on the phrase passes it.
- 2026-11-02: **`getProgramName` returns "Default"** until the preset drawer is wired; then
  the active preset's name, as Horizon Pad does.
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
