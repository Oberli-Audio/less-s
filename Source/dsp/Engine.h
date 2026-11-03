#pragma once

#include <juce_audio_basics/juce_audio_basics.h>

#include <array>
#include <atomic>
#include <vector>

#include "Constants.h"
#include "Dynamics.h"
#include "Learn.h"
#include "Stft.h"
#include "Svf.h"

/*  Less S - the DSP engine.

    Ported by structure from `sound design/proto/less_s.py` (class LessS), which is the
    G5 null reference. Same classes, same order of operations, same constants
    (Constants.h). The processor owns one Engine and does nothing to the audio itself.

    One detector, three appliers:

      in -+- detector: Butterworth BP4(Frequency, Width) -> peak + mean-square (Speed)
          |            -> dB -> gain computer (Threshold, Range, knee, ratio)
          |            -> ballistics in dB -> gain
          +- Wide:     the signal x gain
          +- Split:    x + (gain - 1) * BP(x)          the parallel bell, nulls at gain 1
          +- Spectral: STFT bins x the bell's magnitude at that gain
          -> Mix -> out; GR and band level for the editor; ess-map events

    Real-time (rule 1): everything is sized in prepare(); process() allocates nothing,
    takes no lock and makes no system call. The editor side is three atomics and one
    lock-free ring of PODs. */
namespace lesss::dsp
{
enum Mode { modeWide = 0, modeSplit = 1, modeSpectral = 2 };
enum Listen { listenOff = 0, listenEss = 1, listenDelta = 2 };
enum Stereo { stereoLink = 0, stereoMid = 1, stereoDual = 2 };

/** The parameters in plain units, read once per block from the cached atomics. */
struct Parameters
{
    float frequency = 7000.0f;      // Hz
    float width = 1.2f;             // octaves
    float threshold = -28.0f;       // dB
    float range = 8.0f;             // dB
    float lookaheadMs = 0.0f;
    float mix = 100.0f;             // %
    int mode = modeSplit;
    int speed = 1;
    int listen = listenOff;
    int stereo = stereoLink;
    bool autoLearn = true;
    bool relative = false;
    bool bypass = false;
};

/** One caught ess, as the ess map draws it (sketch 4.4). POD, so the ring needs no
    allocation and no destructor on either thread. */
struct EssEvent
{
    double startSeconds = 0.0;
    float durationSeconds = 0.0f;
    float depthDb = 0.0f;
    bool hitRange = false;
};

/** A single-producer single-consumer ring of PODs: the audio thread writes, the editor
    reads (D.1). Overrun drops the oldest, which is right for a display. */
template <typename T, int Capacity>
class EventRing
{
public:
    void clear() noexcept
    {
        read.store (0, std::memory_order_relaxed);
        write.store (0, std::memory_order_relaxed);
    }

    void push (const T& v) noexcept
    {
        const int w = write.load (std::memory_order_relaxed);
        slots[(size_t) (w % Capacity)] = v;
        write.store (w + 1, std::memory_order_release);
    }

    bool pop (T& out) noexcept
    {
        int r = read.load (std::memory_order_relaxed);
        const int w = write.load (std::memory_order_acquire);
        if (r >= w)
            return false;
        if (w - r > Capacity)                       // the reader fell behind: skip ahead
            r = w - Capacity;
        out = slots[(size_t) (r % Capacity)];
        read.store (r + 1, std::memory_order_relaxed);
        return true;
    }

private:
    std::array<T, Capacity> slots {};
    std::atomic<int> read { 0 }, write { 0 };
};

class Engine
{
public:
    //==========================================================================
    void prepare (double sampleRateIn, int maxBlock)
    {
        sampleRate = sampleRateIn;
        juce::ignoreUnused (maxBlock);

        for (auto& ch : detector)
            for (auto& section : ch)
                section = Svf {};
        for (auto& b : bell)
            b = Svf {};

        for (auto& s : stft)
            s.prepare (sampleRate);

        const int maxLatency = std::max ((int) std::lround (k::lookaheadMaxSeconds * sampleRate),
                                         stft[0].latency()) + 2;
        for (auto& d : lookahead)
            d.prepare (maxLatency);
        for (auto& d : dryDelay)
            d.prepare (maxLatency);
        for (auto& d : bandDelay)
            d.prepare (maxLatency);

        gainHistoryMask = 1;
        while (gainHistoryMask < 4 * stft[0].size())
            gainHistoryMask <<= 1;
        gainHistory.assign ((size_t) gainHistoryMask, 1.0f);
        --gainHistoryMask;                          // a power of two minus one: index mask

        for (auto& s : smoothed)
            s.set (sampleRate, k::paramTauSeconds, (double) k::controlBlock);

        fadeLength = std::max (1, (int) std::lround (k::configFadeSeconds * sampleRate));
        learn.prepare (sampleRate);
        reset();
    }

    /** rule 8: every piece of state, delay memory included. Two renders from here with
        the same input are bit-identical. */
    void reset() noexcept
    {
        for (auto& ch : detector)
            for (auto& section : ch)
                section.reset();
        for (auto& b : bell)
            b.reset();
        for (auto& s : stft)
            s.reset();
        for (auto& d : lookahead)
            d.reset();
        for (auto& d : dryDelay)
            d.reset();
        for (auto& d : bandDelay)
            d.reset();
        for (auto& f : level)
            f.reset();
        for (auto& f : fullBand)
            f.reset (0.0);
        for (auto& b : ballistics)
            b.reset();
        std::fill (gainHistory.begin(), gainHistory.end(), 1.0f);
        samplePosition = 0;
        events.clear();
        eventOpen = false;
        eventStart = 0.0;
        eventDepth = 0.0f;
        learn.reset();
        learnDone = false;
        sawAudio = false;
        smoothersPrimed = false;
        fade = 1.0f;
        gainReduction.store (0.0f, std::memory_order_relaxed);
        bandLevel.store (-100.0f, std::memory_order_relaxed);
    }

    /** The latency this configuration reports (rule 7); the processor calls
        setLatencySamples with it whenever Mode or Lookahead change. */
    int latencyFor (const Parameters& p) const noexcept
    {
        if (p.mode == modeSpectral)
            return stft[0].latency();   // the Lookahead knob is disabled here: the frame is the look-ahead
        return (int) std::lround (p.lookaheadMs * 1.0e-3 * sampleRate);
    }

    //==========================================================================
    void process (juce::AudioBuffer<float>& buffer, const Parameters& p)
    {
        const int numSamples = buffer.getNumSamples();
        if (numSamples == 0)
            return;
        const int latency = latencyFor (p);

        auto* left = buffer.getWritePointer (0);
        auto* right = buffer.getNumChannels() > 1 ? buffer.getWritePointer (1) : left;

        if (! smoothersPrimed)
        {
            primeSmoothers (p);
            smoothersPrimed = true;
        }
        if (p.mode != lastMode || p.listen != lastListen || p.stereo != lastStereo)
        {
            // rule 2: a switch is crossfaded, never stepped. Changing Mode to or from
            // Spectral also changes the reported latency; the host re-measures and the
            // sketch (4.7) accepts one click there, so the STFT starts from reset.
            prevMode = lastMode;
            prevListen = lastListen;
            prevStereo = lastStereo;
            lastMode = p.mode;
            lastListen = p.listen;
            lastStereo = p.stereo;
            fade = 0.0f;
            if ((p.mode == modeSpectral) != (prevMode == modeSpectral))
            {
                fade = 1.0f;
                for (auto& s : stft)
                    s.reset();
            }
        }

        if (p.bypass)
        {
            // rule 7: bypass is latency-compensated and nulls against the input
            for (int i = 0; i < numSamples; ++i)
            {
                // every delay line is fed, so un-bypassing starts from continuous state
                const float l = dryDelay[0].process (left[i], latency);
                const float r = dryDelay[1].process (right[i], latency);
                lookahead[0].process (left[i], 0);
                lookahead[1].process (right[i], 0);
                bandDelay[0].process (0.0f, latency);
                bandDelay[1].process (0.0f, latency);
                left[i] = l;
                if (right != left)
                    right[i] = r;
            }
            samplePosition += numSamples;
            gainReduction.store (0.0f, std::memory_order_relaxed);
            return;
        }

        // Learn: the audio thread's share is one bounded copy (rule 1)
        if (p.autoLearn && ! learnDone)
        {
            float peak = 0.0f;
            for (int i = 0; i < numSamples; ++i)
                peak = std::max (peak, std::abs (0.5f * (left[i] + right[i])));
            const double peakDb = toDb (peak);
            if (! sawAudio && peakDb > k::learnGateDbfs)
            {
                sawAudio = true;
                learn.arm();
            }
            if (learn.isArmed())
                learn.capture (left, right, numSamples, peakDb);
        }

        const int lookSamples = p.mode == modeSpectral
                                  ? 0 : (int) std::lround (p.lookaheadMs * 1.0e-3 * sampleRate);
        const auto& speed = k::speeds[(size_t) std::clamp (p.speed, 0, 2)];
        const double mixTarget = std::clamp ((double) p.mix, 0.0, 100.0);

        for (int i = 0; i < numSamples; ++i)
        {
            if ((samplePosition % k::controlBlock) == 0)
                updateCoefficients (p, speed, mixTarget);

            const double l = left[i];
            const double r = right[i];

            // ---- detector: a 4th-order Butterworth band-pass per channel, normalised
            // to unity at the centre. The band-pass is linear, so BP(M) = (BP(L)+BP(R))/2
            // and the Mid detector costs no extra filter state.
            const double bl = detector[0][3].low (detector[0][2].low (detector[0][1].high (detector[0][0].high (l)))) * detNorm;
            const double br = detector[1][3].low (detector[1][2].low (detector[1][1].high (detector[1][0].high (r)))) * detNorm;
            const double bm = 0.5 * (bl + br);

            const double lvL = level[0].process (bl);
            const double lvR = level[1].process (br);
            const double lvM = level[2].process (bm);
            const double fL = fullBand[0].process (l * l);
            const double fR = fullBand[1].process (r * r);
            const double fM = fullBand[2].process (0.25 * (l + r) * (l + r));

            double showLink, showL, showR, showM;
            double redLink, redL, redR, redM;
            if (p.relative)
            {
                computeRelative (std::max (lvL, lvR), std::max (fL, fR), showLink, redLink);
                computeRelative (lvL, fL, showL, redL);
                computeRelative (lvR, fR, showR, redR);
                computeRelative (lvM, fM, showM, redM);
            }
            else
            {
                computeAbsolute (std::max (lvL, lvR), showLink, redLink);
                computeAbsolute (lvL, showL, redL);
                computeAbsolute (lvR, showR, redR);
                computeAbsolute (lvM, showM, redM);
            }
            const double gLink = fromDb (-ballistics[0].process (redLink));
            const double gL = fromDb (-ballistics[1].process (redL));
            const double gR = fromDb (-ballistics[2].process (redR));
            const double gM = fromDb (-ballistics[3].process (redM));

            // ---- lookahead: the audio is delayed, the detector is not (E.2)
            const double dl = lookahead[0].process ((float) l, lookSamples);
            const double dr = lookahead[1].process ((float) r, lookSamples);
            const float dryL = dryDelay[0].process ((float) l, latency);
            const float dryR = dryDelay[1].process ((float) r, latency);
            const float bandLatL = bandDelay[0].process ((float) bl, latency);
            const float bandLatR = bandDelay[1].process ((float) br, latency);

            // ---- the time-domain appliers, crossfaded on a Mode / Listen / Stereo change
            double out0 = 0.0, out1 = 0.0;
            for (int pass = 0; pass < 2; ++pass)
            {
                const float w = pass == 0 ? fade : 1.0f - fade;
                if (w <= 0.0f)
                    continue;
                const int mode = pass == 0 ? lastMode : prevMode;
                const int listen = pass == 0 ? lastListen : prevListen;
                const int st = pass == 0 ? lastStereo : prevStereo;
                const double g1 = st == stereoLink ? gLink : (st == stereoDual ? gL : gM);
                const double g2 = st == stereoLink ? gLink : (st == stereoDual ? gR : gM);
                double c0, c1;
                if (listen == listenEss)
                {
                    c0 = st == stereoMid ? bm : bl;
                    c1 = st == stereoMid ? bm : br;
                }
                else if (mode == modeSpectral)
                {
                    c0 = c1 = 0.0;              // the STFT path writes the output below
                }
                else if (st == stereoMid)
                {
                    const double m = 0.5 * (dl + dr), s = 0.5 * (dl - dr);
                    const double m2 = mode == modeWide ? m * g1 : m + (g1 - 1.0) * bell[2].band (m);
                    c0 = m2 + s;
                    c1 = m2 - s;
                }
                else if (mode == modeWide)
                {
                    c0 = dl * g1;
                    c1 = dr * g2;
                }
                else
                {
                    c0 = dl + (g1 - 1.0) * bell[0].band (dl);
                    c1 = dr + (g2 - 1.0) * bell[1].band (dr);
                }
                if (listen == listenDelta && mode != modeSpectral)
                {
                    c0 = dl - c0;
                    c1 = dr - c1;
                }
                out0 += w * c0;
                out1 += w * c1;
            }

            const double gShow = lastStereo == stereoLink ? gLink
                               : (lastStereo == stereoDual ? 0.5 * (gL + gR) : gM);
            const double showNow = lastStereo == stereoLink ? showLink
                                 : (lastStereo == stereoDual ? 0.5 * (showL + showR) : showM);
            gainHistory[(size_t) (samplePosition & gainHistoryMask)] = (float) gShow;
            const double reductionDb = -toDb (gShow);
            trackEvent (reductionDb);

            if (p.mode == modeSpectral)
            {
                const long long t = samplePosition;
                const double f0 = currentF0, q = currentQ;
                auto fill = [this, t, f0, q] (std::vector<float>& gains, const std::vector<double>& freqs)
                {
                    // the gain at the frame's centre, so the reduction lands on the ess;
                    // taken per frame, from the coefficients current at that frame, so a
                    // moving Frequency cannot make this depend on the block size (D.5.1)
                    const long long centre = t - stft[0].size() / 2;
                    const float g = centre >= 0
                                      ? gainHistory[(size_t) (centre & gainHistoryMask)] : 1.0f;
                    for (size_t bin = 0; bin < gains.size(); ++bin)
                        gains[bin] = (float) k::bellMagnitude (freqs[bin], f0, q, g);
                };
                const float s0 = stft[0].process ((float) dl, fill);
                const float s1 = stft[1].process ((float) dr, fill);
                if (lastListen == listenEss)
                {
                    out0 = bandLatL;
                    out1 = bandLatR;
                }
                else if (lastListen == listenDelta)
                {
                    out0 = dryL - s0;
                    out1 = dryR - s1;
                }
                else
                {
                    out0 = s0;
                    out1 = s1;
                }
            }

            // ---- Mix: a linear blend of the delayed dry and the wet. EX-1 in
            // docs/status.md: rule 5 asks for an equal-power crossfade, which is right
            // for an uncorrelated wet path; here dry and wet are the same voice minus a
            // little band, so equal-power would add to +3 dB at Mix 50 %.
            const double mixValue = std::clamp (smoothed[(size_t) smMix].value(), 0.0, 100.0) / 100.0;
            if (mixValue < 1.0 && p.listen == listenOff)
            {
                out0 = dryL * (1.0 - mixValue) + out0 * mixValue;
                out1 = dryR * (1.0 - mixValue) + out1 * mixValue;
            }

            left[i] = (float) out0;
            if (right != left)
                right[i] = (float) out1;

            if (fade < 1.0f)
                fade = std::min (1.0f, fade + 1.0f / (float) fadeLength);
            ++samplePosition;

            if (i == numSamples - 1)
            {
                gainReduction.store ((float) reductionDb, std::memory_order_relaxed);
                bandLevel.store ((float) showNow, std::memory_order_relaxed);
            }
        }
    }

    //==========================================================================
    // What the editor reads (D.6.2): atomics and one ring, never a lock.
    float gainReductionDb() const noexcept { return gainReduction.load (std::memory_order_relaxed); }
    float bandLevelDb() const noexcept { return bandLevel.load (std::memory_order_relaxed); }
    bool popEvent (EssEvent& out) noexcept { return events.pop (out); }

    // Learn, from the message thread (or the harness, after the render)
    bool learnReady() const noexcept { return learn.isReady(); }
    /** Learn's captured share, 0..1, or -1 when not capturing (the editor's hairline). */
    float learnProgress() const noexcept { return learn.progress(); }
    /** Audio thread: the clock the ess map's events are stamped with, in seconds. */
    double positionSeconds() const noexcept { return (double) samplePosition / sampleRate; }
    LearnResult runLearn()
    {
        auto r = learn.analyse();
        learn.markDone();
        learnDone = true;
        return r;
    }
    /** The editor's Learn button and the menu item. */
    void requestLearn() noexcept
    {
        learnDone = false;
        sawAudio = false;
    }

    int stftLatency() const noexcept { return stft[0].latency(); }

private:
    enum { smFrequency = 0, smWidth, smThreshold, smRange, smMix, smCount };

    void primeSmoothers (const Parameters& p) noexcept
    {
        // the log-domain smoothers hold log2(value): seeding them with the linear value
        // made the first block compute 2 ** 7000 (docs/failures.md)
        smoothed[smFrequency].reset (std::log2 (std::max ((double) p.frequency, 1.0)));
        smoothed[smWidth].reset (std::log2 (std::max ((double) p.width, 1.0e-3)));
        smoothed[smThreshold].reset (p.threshold);
        smoothed[smRange].reset (p.range);
        smoothed[smMix].reset (p.mix);
        lastMode = prevMode = p.mode;
        lastListen = prevListen = p.listen;
        lastStereo = prevStereo = p.stereo;
    }

    void updateCoefficients (const Parameters& p, const k::Speed& speed, double mixTarget) noexcept
    {
        const double f0 = std::pow (2.0, smoothed[smFrequency].process (std::log2 (std::max ((double) p.frequency, 1.0))));
        const double width = std::pow (2.0, smoothed[smWidth].process (std::log2 (std::max ((double) p.width, 1.0e-3))));
        threshold = smoothed[smThreshold].process (p.threshold);
        range = smoothed[smRange].process (p.range);
        smoothed[smMix].process (mixTarget);

        const double q = k::qForBandwidth (width);
        const double lo = f0 * std::pow (2.0, -width * 0.5);
        const double hi = f0 * std::pow (2.0, width * 0.5);
        for (auto& ch : detector)
        {
            ch[0].set (sampleRate, lo, k::butter4Q[0]);
            ch[1].set (sampleRate, lo, k::butter4Q[1]);
            ch[2].set (sampleRate, hi, k::butter4Q[0]);
            ch[3].set (sampleRate, hi, k::butter4Q[1]);
        }
        detNorm = 1.0 / std::max (k::butter4HighpassMag (f0, lo) * k::butter4LowpassMag (f0, hi), 1.0e-12);
        for (auto& b : bell)
            b.set (sampleRate, f0, q);
        for (auto& f : level)
            f.set (sampleRate, k::peakReleaseSeconds, speed.rmsTauSeconds, speed.peakBlend);
        for (auto& f : fullBand)
            f.set (sampleRate, k::fullTauSeconds);
        for (auto& b : ballistics)
            b.set (sampleRate, speed.attackSeconds, speed.releaseSeconds, speed.releaseSlow,
                   k::programHoldSeconds);
        currentF0 = f0;
        currentQ = q;
        currentWidth = width;
    }

    void computeAbsolute (double bandLevelLinear, double& show, double& reduction) const noexcept
    {
        show = toDb (bandLevelLinear);
        reduction = GainComputer::reductionDb (show - threshold, range, k::kneeDb, k::ratio);
    }

    void computeRelative (double bandLevelLinear, double fullMeanSquare, double& show,
                          double& reduction) const noexcept
    {
        const double full = toDb (std::sqrt (std::max (fullMeanSquare, 0.0)));
        show = toDb (bandLevelLinear) - full;
        reduction = full < k::fullFloorDbfs
                      ? 0.0 : GainComputer::reductionDb (show - threshold, range, k::kneeDb, k::ratio);
    }

    /** The ess map: an event opens above eventOpenDb of reduction and closes below
        eventCloseDb; the bar is the deepest reduction inside it (sketch 4.4). */
    void trackEvent (double reductionDb) noexcept
    {
        const double now = (double) samplePosition / sampleRate;
        if (! eventOpen)
        {
            if (reductionDb > k::eventOpenDb)
            {
                eventOpen = true;
                eventStart = now;
                eventDepth = (float) reductionDb;
            }
        }
        else
        {
            eventDepth = std::max (eventDepth, (float) reductionDb);
            if (reductionDb < k::eventCloseDb)
            {
                EssEvent e;
                e.startSeconds = eventStart;
                e.durationSeconds = (float) (now - eventStart);
                e.depthDb = eventDepth;
                e.hitRange = eventDepth >= range - k::eventRangeMarginDb;
                events.push (e);
                eventOpen = false;
            }
        }
    }

    double sampleRate = 48000.0;
    std::array<std::array<Svf, 4>, 2> detector {};   // 2 channels x (HP, HP, LP, LP)
    std::array<Svf, 3> bell {};                      // the appliers: L, R, M
    std::array<LevelFollower, 3> level {};           // L, R, M
    std::array<OnePole, 3> fullBand {};              // full-band mean square for Relative
    std::array<Ballistics, 4> ballistics {};         // link, L, R, M
    std::array<Stft, 2> stft {};
    std::array<DelayLine, 2> lookahead {}, dryDelay {}, bandDelay {};
    std::array<OnePole, smCount> smoothed {};
    std::vector<float> gainHistory;
    Learn learn;
    EventRing<EssEvent, 64> events;

    long long samplePosition = 0;
    int gainHistoryMask = 0, fadeLength = 1;
    int lastMode = modeSplit, lastListen = listenOff, lastStereo = stereoLink;
    int prevMode = modeSplit, prevListen = listenOff, prevStereo = stereoLink;
    float fade = 1.0f;
    double threshold = -28.0, range = 8.0, detNorm = 1.0;
    double currentF0 = 7000.0, currentQ = 1.0, currentWidth = 1.2;
    bool eventOpen = false, learnDone = false, sawAudio = false, smoothersPrimed = false;
    double eventStart = 0.0;
    float eventDepth = 0.0f;

    std::atomic<float> gainReduction { 0.0f }, bandLevel { -100.0f };
};
} // namespace lesss::dsp
