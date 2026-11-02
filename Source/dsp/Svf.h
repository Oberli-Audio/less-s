#pragma once

#include <algorithm>
#include <cmath>

/*  Less S - the TPT / ZDF state-variable filter.

    Ported by structure from `sound design/proto/less_s.py` (class Svf); the prototype is
    the G5 null reference, so the arithmetic order here matches it line for line. Andrew
    Simper's (Cytomic) trapezoidal-integration SVF.

    Why not a biquad (rule 6): Frequency and Width are smoothed parameters, so both the
    detector's band-pass and the applier's bell move while audio runs, and interpolated
    biquad coefficients can be unstable between two stable filters (F.2 Law 5). A TPT SVF
    is safe to re-coefficient at any rate.

    State and arithmetic are double. The audio buffers are float, but these filters carry
    recursive state and the G5 null against the prototype is measured in dBFS: per-operation
    float noise accumulates in the state and would cost about 20 dB of residual for no
    measurable saving (two filters per channel). */
namespace lesss::dsp
{
class Svf
{
public:
    void reset() noexcept
    {
        ic1 = 0.0;
        ic2 = 0.0;
    }

    /** Coefficients from a centre (or corner) frequency in Hz and a Q. */
    void set (double sampleRate, double hz, double q) noexcept
    {
        hz = std::clamp (hz, 10.0, sampleRate * 0.45);
        const double g = std::tan (3.14159265358979323846 * hz / sampleRate);
        k = 1.0 / std::max (q, 1.0e-4);
        a1 = 1.0 / (1.0 + g * (g + k));
        a2 = g * a1;
        a3 = g * a2;
    }

    /** Band-pass, normalised to unity peak gain at the centre, so `1 + (G-1) * band(x)`
        is an exact bell and is exactly the input at G = 1. */
    double band (double x) noexcept
    {
        const double v3 = x - ic2;
        const double v1 = a1 * ic1 + a2 * v3;
        const double v2 = ic2 + a2 * ic1 + a3 * v3;
        ic1 = 2.0 * v1 - ic1;
        ic2 = 2.0 * v2 - ic2;
        return k * v1;
    }

    double low (double x) noexcept
    {
        const double v3 = x - ic2;
        const double v1 = a1 * ic1 + a2 * v3;
        const double v2 = ic2 + a2 * ic1 + a3 * v3;
        ic1 = 2.0 * v1 - ic1;
        ic2 = 2.0 * v2 - ic2;
        return v2;
    }

    double high (double x) noexcept
    {
        const double v3 = x - ic2;
        const double v1 = a1 * ic1 + a2 * v3;
        const double v2 = ic2 + a2 * ic1 + a3 * v3;
        ic1 = 2.0 * v1 - ic1;
        ic2 = 2.0 * v2 - ic2;
        return x - k * v1 - v2;
    }

private:
    double ic1 = 0.0, ic2 = 0.0;
    double a1 = 0.0, a2 = 0.0, a3 = 0.0, k = 1.0;
};
} // namespace lesss::dsp
