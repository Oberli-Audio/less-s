#pragma once

#include <juce_dsp/juce_dsp.h>

#include <atomic>
#include <vector>

#include "Constants.h"
#include "Dynamics.h"

/*  Less S - Learn: the one-shot band finder (sketch 4.2).

    Ported by structure from `sound design/proto/less_s.py` (class Learn).

    Rule 1 decides the shape of this class. The analysis is an FFT over two seconds of
    audio with a search in it, which has no place in `processBlock`, so the audio thread
    does one thing only: `capture()` copies the mono sidechain into a buffer sized in
    `prepare()`. When the buffer is full it sets an atomic flag; the message thread (or,
    in the harness, the renderer after the render) calls `analyse()`, which is a pure
    function of that buffer, and writes Frequency and Width to the parameters through
    begin/perform/end edit so the host records one undo step and the preset shows
    modified. Nothing else is touched - Learn is not a tracker. */
namespace lesss::dsp
{
struct LearnResult
{
    bool found = false;
    double frequency = 0.0;     // Hz
    double width = 0.0;         // octaves
    int sibilantFrames = 0;
};

class Learn
{
public:
    void prepare (double sampleRateIn)
    {
        sampleRate = sampleRateIn;
        buffer.assign ((size_t) std::lround (k::learnSeconds * sampleRate), 0.0f);
        const int frame = std::max (64, 1 << (int) std::lround (std::log2 (k::learnFrameSeconds * sampleRate)));
        frameSize = frame;
        fft = std::make_unique<juce::dsp::FFT> ((int) std::lround (std::log2 ((double) frame)));
        window.resize ((size_t) frame);
        for (int i = 0; i < frame; ++i)
            window[(size_t) i] = (float) (0.5 - 0.5 * std::cos (juce::MathConstants<double>::twoPi * i / frame));
        scratch.assign ((size_t) (2 * frame), 0.0f);
        accum.assign ((size_t) (frame / 2 + 1), 0.0);
        reset();
    }

    void reset() noexcept
    {
        captured.store (0, std::memory_order_relaxed);
        armed.store (false, std::memory_order_relaxed);
    }

    /** Ask for a new Learn: the next two seconds above the gate are captured. */
    void arm() noexcept
    {
        captured.store (0, std::memory_order_relaxed);
        armed.store (true, std::memory_order_relaxed);
    }

    bool isArmed() const noexcept { return armed.load (std::memory_order_relaxed); }

    /** For the editor's progress hairline: the captured share of the window, 0..1, or -1
        when no Learn is capturing. Any thread; reads two atomics and the buffer's size,
        which only prepare() changes. */
    float progress() const noexcept
    {
        if (! armed.load (std::memory_order_relaxed) || buffer.empty())
            return -1.0f;
        return std::min (1.0f, (float) captured.load (std::memory_order_relaxed) / (float) buffer.size());
    }

    bool isReady() const noexcept
    {
        return armed.load (std::memory_order_relaxed)
            && captured.load (std::memory_order_relaxed) >= (int) buffer.size();
    }

    /** Audio thread: a bounded copy into a buffer sized in prepare(), no allocation and
        no locks (rule 1). The mono sum is formed here rather than in a scratch buffer,
        because a scratch buffer would have to be resized for a block larger than the one
        the host announced - which is an allocation in processBlock. `blockPeakDb` is the
        caller's own peak measurement, so neither side walks the block twice. */
    void capture (const float* l, const float* r, int numSamples, double blockPeakDb) noexcept
    {
        if (! armed.load (std::memory_order_relaxed) || numSamples <= 0)
            return;
        const int have = captured.load (std::memory_order_relaxed);
        if (have >= (int) buffer.size())
            return;
        if (blockPeakDb < k::learnGateDbfs)
            return;                                   // silence moves nothing
        const int n = std::min (numSamples, (int) buffer.size() - have);
        for (int i = 0; i < n; ++i)
            buffer[(size_t) (have + i)] = 0.5f * (l[i] + r[i]);
        captured.store (have + n, std::memory_order_release);
    }

    /** Message thread: a pure function of the captured buffer. */
    LearnResult analyse()
    {
        LearnResult r;
        const int have = captured.load (std::memory_order_acquire);
        const int n = frameSize;
        const int hop = n / 2;
        std::fill (accum.begin(), accum.end(), 0.0);
        int frames = 0;
        for (int start = 0; start + n <= have; start += hop)
        {
            for (int i = 0; i < n; ++i)
                scratch[(size_t) i] = buffer[(size_t) (start + i)] * window[(size_t) i];
            std::fill (scratch.begin() + n, scratch.end(), 0.0f);
            fft->performFrequencyOnlyForwardTransform (scratch.data(), true);
            double eHi = 0.0, eLo = 0.0;
            for (int bin = 0; bin <= n / 2; ++bin)
            {
                const double f = (double) bin * sampleRate / (double) n;
                const double p = (double) scratch[(size_t) bin] * scratch[(size_t) bin];
                if (f >= k::learnSplitHz)
                    eHi += p;
                else if (f >= 50.0)
                    eLo += p;
            }
            // "energy above 3 kHz exceeds energy below by 6 dB", as a power ratio
            if (eHi > 0.0 && 10.0 * std::log10 (eHi / std::max (eLo, 1.0e-30)) > k::learnSibilantDb)
            {
                for (int bin = 0; bin <= n / 2; ++bin)
                    accum[(size_t) bin] += (double) scratch[(size_t) bin] * scratch[(size_t) bin];
                ++frames;
            }
        }
        r.sibilantFrames = frames;
        if (frames < k::learnMinFrames)
            return r;

        double sum = 0.0, weighted = 0.0;
        const int firstBin = (int) std::ceil (k::learnSplitHz * n / sampleRate);
        for (int bin = firstBin; bin <= n / 2; ++bin)
        {
            const double f = (double) bin * sampleRate / (double) n;
            sum += accum[(size_t) bin];
            weighted += f * accum[(size_t) bin];
        }
        if (sum <= 0.0)
            return r;
        const double centroid = weighted / sum;

        // The octave span centred on the centroid that holds learnWidthEnergy of it:
        // sort the bins by their distance from the centroid in octaves, walk out until
        // enough energy is inside, and take twice that distance. Identical to the
        // prototype's argsort-and-cumsum, so both report the same width. Off the audio
        // thread, so the sort may allocate (rule 1 is about processBlock).
        sorted.clear();
        for (int bin = firstBin; bin <= n / 2; ++bin)
        {
            const double f = (double) bin * sampleRate / (double) n;
            sorted.push_back ({ std::abs (std::log2 (std::max (f, 1.0) / centroid)), accum[(size_t) bin] });
        }
        std::sort (sorted.begin(), sorted.end(), [] (auto& a, auto& b) { return a.first < b.first; });
        double inside = 0.0, span = sorted.empty() ? 0.0 : sorted.back().first;
        for (auto& [distance, energy] : sorted)
        {
            inside += energy;
            if (inside >= k::learnWidthEnergy * sum)
            {
                span = distance;
                break;
            }
        }
        r.found = true;
        r.frequency = std::clamp (centroid, 2000.0, 16000.0);
        r.width = std::clamp (2.0 * span, k::learnWidthMin, k::learnWidthMax);
        return r;
    }

    void markDone() noexcept { armed.store (false, std::memory_order_relaxed); }

private:
    std::unique_ptr<juce::dsp::FFT> fft;
    std::vector<float> buffer, window, scratch;
    std::vector<double> accum;
    std::vector<std::pair<double, double>> sorted;    // (octaves from the centroid, energy)
    double sampleRate = 48000.0;
    int frameSize = 1024;
    std::atomic<int> captured { 0 };
    std::atomic<bool> armed { false };
};
} // namespace lesss::dsp
