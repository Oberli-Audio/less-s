# Changelog

All notable changes to Less S, newest first (Keep a Changelog). A **Sounds different:**
line marks a release that changes a factory sound; "(reported by X.)" credits a friend's report.

## [Unreleased]
### Changed
- Accent is sage #33B679, the category accent for mix tools (was iris #A796F0). Nothing is
  released yet, so no shipped build carried the old accent.
- Parameter id `auto` renamed to `autoLearn`; the name stays "Auto". `auto` is a C++ keyword
  and the generated `Source/Params.h` could not compile. No release exists, so no automation
  lane or session is affected (rule 19 freezes IDs at the first release).

### Added
- The de-esser itself: one detector (a 4th-order Butterworth band-pass from Frequency and
  Width, peak and RMS blended by Speed, soft knee, ratio 4:1, hard Range ceiling, ballistics
  in dB) and three ways to apply it - Wide, Split (a parallel bell, exact null at Range 0)
  and Spectral (STFT bins, 256 samples of reported latency at 48 kHz). Relative threshold,
  three Stereo modes, Ess and Delta listening, look-ahead, Learn.
- G1 to G5 with their evidence: the algorithm decision, the numpy design under
  `sound design/proto/` and its 82-check measurement suite, the C++ port in `Source/dsp/`,
  the null test of the port against the design, two goldens, and a 9-preset factory bank.
- The suite now covers the brief's `must_do` list and one presence test per defining feature
  (`tools/tests/test_plugin.py`).
- `docs/handoff.md`: the prompt for the session that takes G6 on.

### Fixed
- The offline harness aborted on a block larger than the one it announced, because its work
  buffer was sized to `--max-block` rather than to the block it actually rendered. The test
  that is for exactly that case could not reach the plugin before this.

## [0.1.0] - 2026-11-01
### Added
- Started from the Oberli Audio plugin template: effect, bone theme, accent iris.
