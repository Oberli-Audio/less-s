# Less S - de-esser (Tier S sketch)

Tier S, gate G0-G2 sketch. Oberli Audio effect, Bone theme, accent Sage #33B679 (mix tools, category scheme confirmed 2026-11-01). Static frame: `less-s@1x.png` (880 x 584 at 100 %), `less-s@2x.png` for Retina viewing. Sound side: sound-design-bob is needed for the detector, the split-band crossover and the spectral mode; this sketch states what the DSP must do and the evidence that proves it.

## 1. G0 brief

**Users.** Björn on lead and backing vocals of worship recordings (several singers, male and female, one session), live-stream mixes, and the occasional hi-hat or acoustic guitar. Friends who get the build.

**Why it is a gap.** Every maintained free VST3 de-esser is account-gated or part of a freemium bundle; Ableton Live has no de-esser in any edition (the manual's workaround is Multiband Dynamics or a sidechained Compressor with EQ, five minutes of setup per voice). The paid references are FabFilter Pro-DS (spectral, auto), Weiss DS1 (relative threshold), sonible smart:deess (one knob, adaptive) and Techivation T-De-Esser 2 (free tier, account).

**Core jobs.**
1. Tame esses on one singer in under 30 s: pick the band, set the depth, done.
2. Keep working across a whole take when the singer moves and gets louder or quieter (relative threshold).
3. Hear exactly what is being taken (Ess listen, Delta listen) and see where it happened (the ess map).
4. Not dull the voice: split-band or spectral by default, wideband only on purpose.
5. Zero latency in the live-stream mix; lookahead only in the studio.

**Context.** On the vocal track or the vocal bus, early in the chain (before compression) or late (after a bright EQ), both are common; the Relative mode makes the position matter less. Window open for a minute per singer.

**Success.** A sibilant phrase at 7 kHz is reduced by the set range without the "th" and "f" sounds changing; the ess map shows the esses and nothing else; a 20 dB level change across a take needs no re-setting in Relative mode; the null test with Range at 0 dB is silent; zero latency reported with Lookahead at 0 ms.

**The five core controls.** Frequency, Width, Threshold, Range, Mode. Auto, Relative, Speed and Listen are the second row.

**CPU and latency budget.** Split mode with lookahead 0: zero latency, 0.5 % on an M1 at 48 kHz, 128 samples. Spectral mode: 1 % and a fixed 256-sample latency (reported). Lookahead adds exactly the set time to the reported latency.

**Three structural decisions (sound side).**
1. One detector, three ways to apply it. The detector is a band-limited level follower (bandpass from Frequency and Width, 24 dB/oct skirts) with a fast peak path and a slower RMS path mixed by Speed; Mode decides what the gain reduction acts on: the whole signal (Wide), only the band through a linear-phase-free Linkwitz-Riley split (Split), or the FFT bins inside the band (Spectral).
2. Relative threshold. With Relative on, the threshold is not an absolute level but a ratio of band energy to full-band energy (how sibilant the moment is, Weiss DS1 style), so the de-esser follows the performance and the Threshold knob reads in dB relative.
3. Auto finds the band, the user keeps the knobs. Auto runs a 2 s analysis on the first play (or on "Learn" from the menu): the centroid of the energy above 3 kHz during detected sibilant frames sets Frequency, the spread sets Width; the knobs move to the found values and stay user-editable. Auto is not a continuous tracker, so the sound does not drift.

## 2. G1 design plan (five lines)

1. **Window** 880 x 584 at 100 %, Bone, compact; the sibilance display is the one large sunken well.
2. **Hero** is what the ear cannot judge: one display well. The spectrum, input (dashed) against output (ink), with the detection band; on its left edge, inside the same well and sharing its level axis, the band-level histogram of the last 8 s drawn vertically with the Threshold line across it (a vocal shows two humps, voice body and esses, and the threshold belongs in the valley between them); underneath the ess map showing each caught ess as a bar of its depth over the last 8 s, a red tick where it hit the Range ceiling. The GR meter is secondary.
3. **Accent** Sage on the set and active only: value arcs and pointers, lit LEDs, selected segments, the detection band and the ess bars (they are the plugin's action, so they carry the accent; the GR meter does not).
4. **Sections** in signal-flow order from the table's groups: Detect, Reduce, Sibilance (display, no parameters), Output (Mix 64 px, GR and level meters, output column last).
5. **States**: modified (pill dims), drawer, About (charcoal page), bypass, Ess listen (display shows only the band, output meter shows the band level, header pill shows "Listening: Ess" in `ink-subtle`), Delta listen (same with "Delta"), Auto learning (a 2 s progress hairline under the Frequency knob, knobs animate to the found values), Spectral mode (the Lookahead knob reads "n/a" and is disabled because the FFT already looks ahead).

## 3. Parameter table (sketch, six columns)

| id | type | name | group | unit / choices | min / max / default |
|---|---|---|---|---|---|
| frequency | float | Frequency | Detect | Hz, center 6 kHz | 2000 / 16000 / 7000 |
| width | float | Width | Detect | oct | 0.3 / 3 / 1.2 |
| threshold | float | Threshold | Reduce | dB (dB rel. when Relative) | -60 / 0 / -28 |
| range | float | Range | Reduce | dB | 0 / 24 / 8 |
| mode | choice | Mode | Reduce | Wide \| Split \| Spectral | 0 / 2 / 1 |
| auto | bool | Auto | Detect | - | 0 / 1 / 1 |
| relative | bool | Relative | Detect | - | 0 / 1 / 0 |
| speed | choice | Speed | Reduce | Fast \| Natural \| Smooth | 0 / 2 / 1 |
| lookahead | float | Lookahead | Reduce | ms | 0 / 5 / 0 |
| listen | choice | Listen | Detect | Off \| Ess \| Delta | 0 / 2 / 0 |
| stereo | choice | Stereo | Reduce | Link \| Mid \| Dual | 0 / 2 / 0 |
| mix | float | Mix | Output | % | 0 / 100 / 100 |
| bypass | bool | Bypass | - | - | 0 / 1 / 0 |

Default Lookahead is 0 ms (zero latency for live use); the "Studio" presets set 2 ms. Default Auto is on so the first play already finds the band; Relative is off by default because a new user expects the threshold to behave like a compressor's.

Tooltips (one sentence; the generator appends range and default):
- Frequency: "Center of the sibilance band Less S listens to; esses sit around 5 to 9 kHz."
- Width: "How wide the listened band is; narrower catches only the hiss, wider also the air."
- Threshold: "Where reduction starts; with Relative on it is how sibilant a moment must be, not how loud."
- Range: "The most Less S will ever take away, so a loud ess cannot vanish."
- Mode: "Wide ducks everything, Split only the band, Spectral only the hissing bins."
- Speed: "Fast grabs the first transient, Smooth rides through longer esses without a dip."
- Lookahead: "Sees the ess before it arrives; adds that much latency."
- Listen: "Ess plays what Less S hears, Delta plays only what it removes."
- Stereo: "Link reduces both channels alike, Mid only the center, Dual each channel on its own."

## 4. Approach and best practice

### 4.1 Signal path
```
in ─┬─ detector: bandpass(Frequency, Width) → peak and RMS followers → Speed blend → threshold (abs or relative) → range limit → lookahead delay on the audio path only
    │
    ├─ Wide:     in × gain
    ├─ Split:    LR4 crossover at the band edges; band × gain; recombine (phase-coherent)
    └─ Spectral: STFT 512/4x overlap; bins inside the band × gain (gain per bin weighted by the band's shape); iSTFT
                                    ↓
                                 Mix → out, meters (GR, out level), ess map events
```
- Gain computer: soft knee 6 dB, ratio fixed at 4:1 up to the Range ceiling, then hard limited to Range. Attack and release come from Speed: Fast 0.2/40 ms, Natural 0.5/80 ms with program-dependent release (longer after long esses), Smooth 2/150 ms.
- Split mode keeps the band's phase: Linkwitz-Riley 4th order, the low and high parts delayed to match nothing (LR4 sums flat), so bypass and Range 0 null.
- Spectral mode: the reduction follows the band shape so bin edges do not ring; the analysis frame is also the lookahead, which is why the Lookahead knob is disabled there.
- Relative threshold: ratio = band RMS / full-band RMS in dB, compared against Threshold; a floor at -50 dBFS full-band keeps silence from tripping it.
- Stereo: Link uses the max of both detectors; Mid runs the detector and the gain on M only (S untouched, so width survives); Dual is two independent de-essers.

### 4.2 Auto (Learn)
- Trigger: first play after insertion when Auto is on, or "Learn" in the menu (and a Learn button under the knobs at Tier P).
- Window: 2 s of audio above -40 dBFS. Sibilant frames are those where energy above 3 kHz exceeds energy below by 6 dB. Frequency = energy centroid of those frames above 3 kHz; Width = the octave span that holds 80 % of that energy, clamped to 0.6-2.0 oct.
- Result is written to the two parameters through begin/perform/end edit so the host records it as a user change and the preset shows modified. Nothing else is touched.
- If fewer than 5 sibilant frames are found, Auto leaves the knobs alone and the display says "No esses found yet" in `ink-subtle` for 3 s.

### 4.3 The band-level histogram
- Like a compressor's level histogram, but of the detector's band level (post bandpass, Speed-blended envelope), 1 dB bins from -60 to 0 dBFS, decaying over 8 s so it follows the take.
- It is drawn vertically on the left edge of the spectrum well, sharing the spectrum's level axis, so one well carries both pictures and the eye reads level once. The strip is 64 px wide; the Threshold line crosses the strip only, not the spectrum, because a band level and a per-bin level are not the same number.
- A Histogram toggle (pill, top right of the section) hides the strip and gives the spectrum the full width. It is editor state, machine-local like the GUI scale, not a host parameter and not in presets; default on.
- The Threshold line is draggable in the strip at Tier P (writes the parameter through begin/perform/end edit); the region above the threshold is tinted with the accent.
- With Relative on the x axis becomes dB relative (band minus full band, -30 to +10) and the two humps separate further; this is the picture that explains why Relative works.
- Reading it: two humps with the line in the valley is right; one hump means the band is wrong (open Width or move Frequency); the line inside the right hump means only the loudest esses are caught.

### 4.4 The ess map
- An event starts when gain reduction exceeds 1 dB and ends when it falls below 0.5 dB; the bar height is the deepest reduction in that event, the bar width its duration; events older than 8 s scroll off.
- A bar that reached the Range ceiling gets a `clip`-colored tick on top; the legend counts them ("one over range"), the tooltip says "raise Range or lower Threshold".
- Events cross from the audio thread as a small lock-free ring of (time, depth, duration); the display timer runs at 30 Hz and stops when the transport stands still.
- This is the hero because it answers the question the ear cannot: is it catching esses, or breaths and cymbals too? Breaths show as wide low bars, cymbals as a regular grid; both are visible at a glance.

### 4.5 Metering
- GR: downward, ink, "-4.6" readout as a level; separate from the output level meter (sample peak, `meter-hot` above -6 dBFS). Both labeled.
- In Ess listen, the level meter shows the band's level, so the user can set Threshold by eye while listening.

### 4.6 Presets (G5, product design)
Init first; then by singer and use: Female Lead Natural, Male Lead Natural, Backing Vocals Smooth, Spoken Word, Live Stream Zero Latency, Studio Spectral 2 ms, Hi-Hat Tamer, Acoustic Guitar Squeak. Each sets the band roughly right and Auto refines it.

### 4.7 Hosts and quirks
- 13 parameters, all visible in Live 10.1's panel.
- Latency changes when Mode or Lookahead change: call `setLatencySamples` and let Live re-measure; the manual says that a change while the transport runs may click once.
- Live on Windows auto-scale note (ship-bob).
- Under Rosetta (Live 10.1) test that Learn's parameter writes are recorded as one undo step.

### 4.8 Deliberately not in it
- No multi-band de-essing (two bands at once): a second instance does it.
- No "mouth noise" or plosive mode: different detector, different plugin.
- No continuous frequency tracking: it drifts and the user cannot hear why.

## 5. Manual outline
1. One paragraph and the sentence "Zero latency with Lookahead at 0 ms and Mode Wide or Split."
2. Thirty-second setup: insert, play, let Auto find the band, set Range, check the ess map.
3. The three modes and when each is right.
4. Relative threshold across a take.
5. Listening (Ess, Delta), reading the histogram (threshold in the valley) and the ess map.
6. Stereo modes for the vocal bus.
7. Parameters (generated).
8. Troubleshooting: lisping (Range too high or Width too wide), nothing happens (Threshold above the band level, check Ess listen), latency jump (Mode or Lookahead changed).

## 6. Acceptance tests for promotion to P
1. Null: Range 0 dB, any mode, output nulls to the input (Spectral within -100 dBFS).
2. Selectivity: a synthetic "s" burst at 7 kHz and an "f" at 4 kHz 10 dB quieter; the s is reduced by Range, the f by less than 0.5 dB.
3. Relative: the same phrase at -30 and -10 dBFS gets the same reduction within 1 dB with Relative on.
4. Latency: reported latency equals measured (Plugalyzer) in every Mode and Lookahead setting.
5. Auto: on a 2 s female vocal sample Frequency lands between 6.5 and 8.5 kHz; on silence the knobs do not move.
6. CPU: under 1 % in Spectral mode, under 0.5 % in Split.
7. Ess map: 13 esses in the test phrase yield 13 events, no event on the breath between phrases.

## 7. Open decisions for Björn
- Name: Less S (decided 2026-11-01). Slug `less-s`, plugin ID `LessS`.
- Accent: Sage #33B679, by the category scheme (decided 2026-11-01): one accent per category, mix tools.
- Decided 2026-11-01: default Mode is Split; the Learn button sits on the panel under the Frequency knob (and stays in the menu).

## 8. Report
```
Tier: S, gate: G0-G2 sketch
Hosts: n/a at S
Brand sheet: complies (output column with Mix, GR meter in ink not accent); logo is a CSS stand-in
What works well: the histogram shows where the threshold belongs before you listen, the ess map answers "is it catching only esses"; Relative threshold removes the re-setting across a take; Mode as one segmented control instead of three plugins
Findings: none at S
Open / recommended: none
Evidence: less-s@1x.png at 100 %, less-s@2x.png
```
