#pragma once

#include <algorithm>
#include <cmath>

/*  Less S - the dynamics building blocks: one-pole smoother, level follower, gain
    computer, ballistics.

    Ported by structure from `sound design/proto/less_s.py` (OnePole, LevelFollower,
    GainComputer, Ballistics). The topology is E.1's recommendation (Giannoulis, Massberg
    and Reiss, JAES 2012): feed-forward, the gain computer in the log domain, the
    ballistics on the control signal rather than on the level.

    Every constant that is a design decision lives in Constants.h with the comment that
    says where it came from; these classes only hold the structure. */
namespace lesss::dsp
{
/** dB helpers that never produce -inf or NaN: the control path is a number, always. */
inline double toDb (double linear) noexcept
{
    return 20.0 * std::log10 (std::max (linear, 1.0e-30));
}

inline double fromDb (double db) noexcept
{
    return std::pow (10.0, db / 20.0);
}

/** y = x + (y - x) * exp(-dt / tau). tau in seconds, dt in samples (rule 12: never a
    constant in samples). */
class OnePole
{
public:
    void set (double sampleRate, double tauSeconds, double dtSamples = 1.0) noexcept
    {
        coef = tauSeconds <= 0.0 ? 0.0 : std::exp (-dtSamples / (tauSeconds * sampleRate));
    }

    void reset (double value = 0.0) noexcept { y = value; }

    double process (double x) noexcept
    {
        y = x + (y - x) * coef;
        return y;
    }

    double value() const noexcept { return y; }

private:
    double y = 0.0, coef = 0.0;
};

/** One channel's band level: a decoupled peak path and a mean-square path, blended by
    Speed in the linear domain and converted to dB once by the caller (E.1). */
class LevelFollower
{
public:
    void set (double sampleRate, double peakReleaseSeconds, double rmsTauSeconds, double blendPeak) noexcept
    {
        peakCoef = std::exp (-1.0 / (std::max (peakReleaseSeconds, 1.0e-6) * sampleRate));
        msCoef = std::exp (-1.0 / (std::max (rmsTauSeconds, 1.0e-6) * sampleRate));
        blend = blendPeak;
    }

    void reset() noexcept
    {
        peak = 0.0;
        ms = 0.0;
    }

    double process (double x) noexcept
    {
        const double a = std::abs (x);
        peak = a > peak ? a : a + (peak - a) * peakCoef;      // instant attack, one-pole release
        const double xx = x * x;
        ms = xx + (ms - xx) * msCoef;
        return blend * peak + (1.0 - blend) * std::sqrt (std::max (ms, 0.0));
    }

private:
    double peak = 0.0, ms = 0.0, peakCoef = 0.0, msCoef = 0.0, blend = 1.0;
};

/** dB over the threshold in, dB of reduction out: soft knee, fixed ratio, hard Range
    ceiling ("the most it ever takes away, so no ess vanishes"). */
struct GainComputer
{
    static double reductionDb (double overDb, double rangeDb, double kneeDb, double ratio) noexcept
    {
        const double half = kneeDb * 0.5;
        const double slope = 1.0 - 1.0 / ratio;
        double r;
        if (overDb <= -half)
            r = 0.0;
        else if (overDb < half)
            r = slope * (overDb + half) * (overDb + half) / (2.0 * kneeDb);
        else
            r = slope * overDb;
        return std::min (r, std::max (rangeDb, 0.0));
    }
};

/** Attack and release on the control signal in dB. The release is program-dependent:
    after `holdSeconds` of continuous release the time constant is multiplied by
    `releaseSlow` - E.1's two-stage optical release, which is what keeps a long ess from
    dipping back up in its middle. `releaseSlow == 1` switches the second stage off. */
class Ballistics
{
public:
    void set (double sampleRate, double attackSeconds, double releaseSeconds,
              double releaseSlow, double holdSeconds) noexcept
    {
        att = std::exp (-1.0 / (std::max (attackSeconds, 1.0e-6) * sampleRate));
        rel = std::exp (-1.0 / (std::max (releaseSeconds, 1.0e-6) * sampleRate));
        relSlow = std::exp (-1.0 / (std::max (releaseSeconds * releaseSlow, 1.0e-6) * sampleRate));
        holdSamples = (int) std::lround (holdSeconds * sampleRate);
    }

    void reset() noexcept
    {
        value = 0.0;
        releasing = 0;
    }

    double process (double targetDb) noexcept
    {
        double coef;
        if (targetDb > value)
        {
            releasing = 0;
            coef = att;
        }
        else
        {
            ++releasing;
            coef = releasing > holdSamples ? relSlow : rel;
        }
        value = targetDb + (value - targetDb) * coef;
        return value;
    }

    double current() const noexcept { return value; }

private:
    double value = 0.0, att = 0.0, rel = 0.0, relSlow = 0.0;
    int holdSamples = 0, releasing = 0;
};

/** The dry path's delay line: stateful across blocks, so it compensates the reported
    latency (rule 7: "the dry path of every wet/dry mix is delay-compensated"). The
    prototype's first version shifted each block on its own, which zeroed the first
    `latency` samples of every block - docs/failures.md has the row. */
class DelayLine
{
public:
    void prepare (int maxDelaySamples)
    {
        buffer.assign ((size_t) std::max (1, maxDelaySamples + 1) * 2, 0.0f);
        capacity = (int) buffer.size();
        write = 0;
    }

    void reset() noexcept
    {
        std::fill (buffer.begin(), buffer.end(), 0.0f);
        write = 0;
    }

    /** Push one sample, read the one `delay` samples older. */
    float process (float x, int delay) noexcept
    {
        buffer[(size_t) write] = x;
        const int read = (write - std::clamp (delay, 0, capacity - 1) + capacity) % capacity;
        write = (write + 1) % capacity;
        return buffer[(size_t) read];
    }

private:
    std::vector<float> buffer;
    int capacity = 1, write = 0;
};
} // namespace lesss::dsp
