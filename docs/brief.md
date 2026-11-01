# Sonic brief (owner-confirmed 2026-11-01 from the decided Tier S sketch, docs/sketch.md; amend below, never edit the YAML)

```yaml
name: Less S
track: effect
stages: [processing, analysis, output]
type: dynamics
musical_role: effect
tier: P
one_sentence: A de-esser that finds the ess band on its own, reduces only that band at zero latency, and shows in a histogram and an ess map exactly what it caught.
references:
  - FabFilter Pro-DS: spectral and wideband modes, auto; Less S is free and adds the band histogram and ess map
  - Weiss DS1: relative threshold; Less S offers it as a switch
  - Techivation T-De-Esser 2: free tier needs an account; Less S needs none
must_do:
  - Reduce esses by up to Range dB without changing "f" and "th"
  - Zero latency in Split and Wide with Lookahead 0
  - Relative threshold follows the singer across a 20 dB level change
  - Auto finds Frequency and Width once (Learn), then leaves the knobs to the user
  - Null at Range 0 dB in every mode
defining_features:
  - Split mode (LR4 band only) as default, phase-coherent
  - Band-level histogram with the Threshold line inside the spectrum well
  - Ess map: every caught ess as a bar of its depth, ticked when it hit Range
out_of_scope: [two-band de-essing, plosive or mouth-noise mode, continuous frequency tracking]
core_controls:
  - Frequency: centre of the ess band
  - Width: how wide the listened band is
  - Threshold: where reduction starts (dB, or dB relative)
  - Range: the most it ever takes away
  - Mode: Wide, Split, Spectral
signal_flow: |
  in -+- detector: bandpass(Freq, Width) -> peak+RMS (Speed) -> threshold (abs|relative) -> range -> gain
      +- Wide: in x gain | Split: LR4 band x gain, recombined | Spectral: STFT 512/4x, band bins x gain
      -> Mix -> out; meters GR, out; ess-map events; band histogram
cpu_budget: { p999_pct: 25, max_pct: 50, idle_pct: 2, at: 48k/64, slice: x86_64-rosetta, preset: Studio Spectral 2 ms }
cpu_reference_machine: Apple M3 Pro (Björn's Mac)
instances_expected: 6-10 per project (lead and backing vocals), 2 in the live-stream rig
latency_budget: 0 in Wide and Split with Lookahead 0; Spectral 256 samples, reported; Lookahead adds its time, reported
sample_rates: [44100, 48000, 88200, 96000, 176400, 192000]
channels: stereo
register: n/a (effect)
register_intent: n/a
presets:
  bank_size: 9
  categories: [Lead, Backing, Speech, Live, Instruments]
  reference_chord: n/a; test material is a sibilant female and male vocal phrase plus synthetic s and f bursts
  loudness_window: n/a
  edge_presets: [Studio Spectral 2 ms, Hi-Hat Tamer, Live Stream Zero Latency]
  naming: English, by singer and use ("Female Lead Natural", "Spoken Word")
mix_context: vocal tracks and buses in worship recordings and the live stream; must leave 1-4 kHz untouched
quality_targets:
  alias_floor_db:     { target: n/a in Split and Spectral; Wide gain modulation below -90 dBFS sidebands, method: 7 kHz burst train, FFT of output }
  thd_n_db:           { target: null at Range 0 (Spectral within -100 dBFS), method: harness null test per mode }
  response_error_db:  { target: "s at 7 kHz reduced by Range +/-1 dB, f at 4 kHz 10 dB quieter by < 0.5 dB", method: synthetic burst pair through the harness }
  loudness:           { target: n/a, method: n/a }
  keyboard_span_lu:   { target: n/a, method: n/a }
  low_register:       { target: n/a, method: n/a }
  other:
    - "relative: same phrase at -30 and -10 dBFS gets the same reduction within 1 dB"
    - "auto: Frequency lands 6.5-8.5 kHz on the female test phrase; silence moves nothing"
    - "ess map: 13 esses in the test phrase give 13 events, none on breaths"
    - "latency: reported equals measured (Plugalyzer) in every mode and lookahead"
open_questions: []
```

## Amendments
- 2026-11-01: Accent is **sage #33B679**, the category accent for mix tools (one accent per
  category; peacock #039BE5 is analysis). It replaces iris #A796F0 from the sketch. Owner's
  call, relayed with the CLAUDE.md and sketch update on `main`; the registry entry in
  bob-skills is still to follow. Nothing is released, so no build carried iris.
- 2026-11-01: Owner decisions confirmed with the brief: default Mode is Split; the Learn button sits on the panel under the Frequency knob (and stays in the menu); the histogram is a strip inside the spectrum well with a machine-local on/off toggle, default on; LookAndFeel and meters come from the shared Source/oberli/ code (bob-skills).
