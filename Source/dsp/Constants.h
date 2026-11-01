#pragma once

#include <cmath>

/*  Less S - every DSP constant, with the reason it has that value.

    G4 asks for the ported constants to be documented beside the code and hand-matched to
    the prototype. They are all in one header so a diff against
    `sound design/proto/less_s.py` (its "constants" block) is one screen; the names are
    the same in both files on purpose. Changing a number here changes the sound, so it
    needs a `Sounds different:` changelog line (ship-bob) and a new G5 null. */
namespace lesss::dsp::k
{
// samples between parameter smoothing and coefficient updates. parameters.csv says
// control_rate = block and rule 2 allows up to 32, but 32 is measurable: sweeping
// Frequency over the whole range at 10 Hz puts a sideband at the update rate itself
// (7000 - 48000/32 = 5500 Hz) at -50 dB against the tone. Measured on the prototype:
// 32 -> -50 dB, 8 -> -65 dB, 1 -> -91 dB. 8 costs about 42k tan() per second for the
// seven filters, under 0.1 % CPU, and is the knee of that curve.
inline constexpr int controlBlock = 8;

inline constexpr double kneeDb = 6.0;             // soft knee of the gain computer (sketch 4.1)
inline constexpr double ratio = 4.0;              // fixed ratio up to the Range ceiling (sketch 4.1)
inline constexpr double peakReleaseSeconds = 0.002;   // decoupled peak detector: level estimation, not ballistics (E.1)
inline constexpr double fullTauSeconds = 0.050;   // full-band mean-square window for Relative mode
inline constexpr double fullFloorDbfs = -50.0;    // below this full-band level Relative does nothing (sketch 4.1)
inline constexpr double programHoldSeconds = 0.030;   // after this long in release the release slows (E.1, two-stage opto)
inline constexpr double configFadeSeconds = 0.015;    // Mode / Listen / Stereo crossfade (rule 2: 10-20 ms)
inline constexpr double lookaheadMaxSeconds = 0.005;  // the table's Lookahead maximum; the ring is sized for it
inline constexpr double paramTauSeconds = 0.020;  // parameters.csv smoothing = 20 ms for every smoothed row

// The STFT window is a *time*, not 512 samples (rule 12). A WOLA's algorithmic delay is
// the window once the partial hop a host's block sizes force you to carry is included,
// so a 512-sample window reports 512 samples of latency and the brief's budget for
// Spectral is 256. 5.333 ms is 256 samples at 48 kHz - the budget exactly - 512 at
// 96 kHz and 1024 at 192 kHz, so the behaviour in time is identical at every rate.
// 5.33 ms also resolves a /t/ better than 10.7 ms, which is what a de-esser is for.
inline constexpr double stftWindowSeconds = 256.0 / 48000.0;
inline constexpr int stftOverlap = 4;             // Hann^2 is COLA at hop = N/4, so Range 0 reconstructs exactly

inline constexpr double eventOpenDb = 1.0;        // an ess-map event opens above this much reduction (sketch 4.4)
inline constexpr double eventCloseDb = 0.5;       // and closes below this
inline constexpr double eventRangeMarginDb = 0.25;    // "it hit the Range ceiling" tolerance for the red tick

inline constexpr double learnSeconds = 2.0;       // the Learn window (sketch 4.2)
inline constexpr double learnGateDbfs = -40.0;    // only audio above this is captured
inline constexpr double learnSplitHz = 3000.0;    // "energy above 3 kHz exceeds energy below by 6 dB"
inline constexpr double learnSibilantDb = 6.0;
inline constexpr int learnMinFrames = 5;          // fewer than this: leave the knobs alone
inline constexpr double learnWidthEnergy = 0.80;  // the octave span that holds 80 % of the sibilant energy
inline constexpr double learnWidthMin = 0.6;
inline constexpr double learnWidthMax = 2.0;
inline constexpr double learnFrameSeconds = 1024.0 / 48000.0;   // 21.3 ms, a power of two per rate

// Speed: the three ballistics sets of sketch 4.1 with the detector blend each implies.
// attack/release are the control-signal time constants; rmsTau is the level estimator's
// window; peakBlend is how much of the level estimate is the peak path; releaseSlow is
// the second release stage's multiplier (1 = no second stage).
struct Speed
{
    const char* name;
    double attackSeconds, releaseSeconds, rmsTauSeconds, peakBlend, releaseSlow;
};
inline constexpr Speed speeds[] = {
    { "Fast",    0.0002, 0.040, 0.001, 1.00, 1.0 },
    { "Natural", 0.0005, 0.080, 0.005, 0.60, 2.5 },
    { "Smooth",  0.0020, 0.150, 0.015, 0.25, 1.0 },
};

// The two Butterworth section Qs of a 4th-order response: 1 / (2 cos(pi/8)) and
// 1 / (2 cos(3 pi/8)). The detector's band is a 4th-order Butterworth band-pass - a
// high-pass at the lower edge and a low-pass at the upper one - which is the sketch's
// "24 dB/oct skirts". Two resonant band-passes in cascade would give only 12 dB/oct and
// leak the vowels: measured at 2 kHz with the default band the Butterworth pair rejects
// 29 dB where the cascade rejected 16, and "leave 1-4 kHz untouched" is in the brief.
inline const double butter4Q[2] = { 1.0 / (2.0 * std::cos (3.14159265358979323846 / 8.0)),
                                    1.0 / (2.0 * std::cos (3.0 * 3.14159265358979323846 / 8.0)) };

/** Q of the applier's bell from a bandwidth in octaves: |H|^2 = 1/(1 + u^2) with
    u = Q (f/f0 - f0/f), the -3 dB edges at u = 1, and f_hi/f0 - f0/f_hi =
    2 sinh(ln2 * bw / 2). The resulting bell's half-depth width is about 0.64 * bw. */
inline double qForBandwidth (double bwOct) noexcept
{
    bwOct = std::max (1.0e-3, bwOct);
    return 1.0 / (2.0 * std::sinh (0.34657359027997264 * bwOct));   // ln(2)/2
}

inline double butter4HighpassMag (double f, double fc) noexcept
{
    const double r = f / fc, r4 = r * r * r * r;
    return r4 / std::sqrt (1.0 + r4 * r4);
}

inline double butter4LowpassMag (double f, double fc) noexcept
{
    const double r = f / fc, r4 = r * r * r * r;
    return 1.0 / std::sqrt (1.0 + r4 * r4);
}

/** |H| of the detector's band-pass at `f`, normalised to unity at `f0` - so Threshold
    means the same level however wide the band is (un-normalised, the pair is 3.1 dB down
    at its own centre at Width 0.3). The editor's band drawing uses this same function,
    so the picture cannot drift from the audio (rule 9). */
inline double detectorMagnitude (double f, double f0, double bwOct) noexcept
{
    const double lo = f0 * std::pow (2.0, -bwOct * 0.5);
    const double hi = f0 * std::pow (2.0, bwOct * 0.5);
    const double atF0 = butter4HighpassMag (f0, lo) * butter4LowpassMag (f0, hi);
    return butter4HighpassMag (f, lo) * butter4LowpassMag (f, hi) / std::max (atF0, 1.0e-12);
}

/** |H| of the applier's unity-peak band-pass (analog prototype). */
inline double bandMagnitude (double f, double f0, double q) noexcept
{
    f = std::max (f, 1.0e-9);
    const double u = q * (f / f0 - f0 / f);
    return 1.0 / std::sqrt (1.0 + u * u);
}

/** |H| of the parallel-form bell `1 + (g-1) * BP` at gain `g`: the magnitude response
    Split actually has, which is the classic peaking-EQ magnitude

        |H| = sqrt((1-W^2)^2 + (g W / q)^2) / sqrt((1-W^2)^2 + (W / q)^2),  W = f / f0.

    Spectral weights every bin with *this*, not with |BP|. Weighting with |BP| - the
    obvious reading of "the gain per bin weighted by the band's shape" - gives a wider
    cut than Split has, because the bell is minimum-phase and the phase narrows its
    skirts: measured at 4 kHz with the default band and an 8 dB cut, |BP| weighting took
    3.8 dB where Split takes 1.6 dB, so switching Mode changed how much a nearby /f/ was
    touched. At g = 1 this is exactly 1, so the Range 0 null still holds. The editor's
    curve calls the same function (rule 9). */
inline double bellMagnitude (double f, double f0, double q, double g) noexcept
{
    const double w = std::max (f, 1.0e-9) / f0;
    const double a = 1.0 - w * w;
    const double num = a * a + (g * w / q) * (g * w / q);
    const double den = a * a + (w / q) * (w / q);
    return std::sqrt (num / std::max (den, 1.0e-300));
}
} // namespace lesss::dsp::k
