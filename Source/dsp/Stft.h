#pragma once

#include <juce_dsp/juce_dsp.h>

#include <vector>

#include "Constants.h"

/*  Less S - the Spectral mode's short-time Fourier transform.

    Ported by structure from `sound design/proto/less_s.py` (class Stft). Hann WOLA with
    the window given in seconds (rule 12) and 4x overlap: both the analysis and the
    synthesis window are a periodic Hann, and the sum of their product is constant at
    hop = N/4, so with every bin gain at 1 the output is the input. That is what lets the
    brief's "Null at Range 0 dB in every mode" hold in Spectral too.

    Latency is N: the WOLA's own N - hop, plus the one hop of pre-roll that keeps the
    stream one-in one-out whatever block sizes the host uses. Reported, and asserted
    against an impulse measurement by the test suite (rule 7).

    Real-time: `prepare` allocates, `push` does not (rule 1). juce::dsp::FFT's
    performRealOnlyForwardTransform works in place on a preallocated float buffer. */
namespace lesss::dsp
{
class Stft
{
public:
    void prepare (double sampleRate)
    {
        const double target = k::stftWindowSeconds * sampleRate;
        int order = std::max (6, (int) std::lround (std::log2 (target)));
        n = 1 << order;
        hop = std::max (1, n / k::stftOverlap);
        fft = std::make_unique<juce::dsp::FFT> (order);

        window.resize ((size_t) n);
        for (int i = 0; i < n; ++i)   // periodic Hann: COLA at N/4
            window[(size_t) i] = (float) (0.5 - 0.5 * std::cos (juce::MathConstants<double>::twoPi * i / n));

        cola = 0.0f;
        for (int i = 0; i < n; i += hop)
            cola += window[(size_t) i] * window[(size_t) i];

        inbuf.assign ((size_t) n, 0.0f);
        outbuf.assign ((size_t) n, 0.0f);
        fftbuf.assign ((size_t) (2 * n), 0.0f);
        carry.assign ((size_t) hop, 0.0f);
        outQueue.assign ((size_t) (n + hop), 0.0f);
        binGain.assign ((size_t) (n / 2 + 1), 1.0f);
        binFreq.resize ((size_t) (n / 2 + 1));
        for (size_t i = 0; i < binFreq.size(); ++i)
            binFreq[i] = (double) i * sampleRate / (double) n;
        reset();
    }

    void reset() noexcept
    {
        std::fill (inbuf.begin(), inbuf.end(), 0.0f);
        std::fill (outbuf.begin(), outbuf.end(), 0.0f);
        std::fill (outQueue.begin(), outQueue.end(), 0.0f);
        std::fill (carry.begin(), carry.end(), 0.0f);
        carryCount = 0;
        readPos = 0;
        // the hop of pre-roll that turns the WOLA's N - hop into exactly N
        writePos = hop;
    }

    int size() const noexcept { return n; }
    int hopSize() const noexcept { return hop; }
    int latency() const noexcept { return n; }
    const std::vector<double>& frequencies() const noexcept { return binFreq; }

    /** One sample in, one sample out. When the hop fills, `fillBinGain` is called with
        the bin-gain buffer to write; it is called once per frame, from the coefficients
        current at that sample, so a moving Frequency cannot make the result depend on
        the host's block size (D.5.1). */
    template <typename FillBinGain>
    float process (float x, FillBinGain&& fillBinGain) noexcept
    {
        carry[(size_t) carryCount++] = x;
        if (carryCount == hop)
        {
            fillBinGain (binGain, binFreq);
            emit();
            carryCount = 0;
        }
        float out = 0.0f;
        if (readPos < writePos)
        {
            out = outQueue[(size_t) (readPos % (int) outQueue.size())];
            ++readPos;
        }
        return out;
    }

private:
    void emit() noexcept
    {
        // slide the analysis window on by one hop
        std::copy (inbuf.begin() + hop, inbuf.end(), inbuf.begin());
        std::copy (carry.begin(), carry.end(), inbuf.end() - hop);

        for (int i = 0; i < n; ++i)
            fftbuf[(size_t) i] = inbuf[(size_t) i] * window[(size_t) i];
        std::fill (fftbuf.begin() + n, fftbuf.end(), 0.0f);
        // the full spectrum, not only the non-negative half: the inverse transform needs
        // the conjugate bins, and scaling bin j and bin n-j by the same gain keeps the
        // symmetry exact, so the reconstruction stays real
        fft->performRealOnlyForwardTransform (fftbuf.data());
        for (int bin = 0; bin < n; ++bin)
        {
            const float g = binGain[(size_t) (bin <= n / 2 ? bin : n - bin)];
            fftbuf[(size_t) (2 * bin)] *= g;
            fftbuf[(size_t) (2 * bin + 1)] *= g;
        }
        fft->performRealOnlyInverseTransform (fftbuf.data());

        for (int i = 0; i < n; ++i)
            outbuf[(size_t) i] += fftbuf[(size_t) i] * window[(size_t) i];

        for (int i = 0; i < hop; ++i)
        {
            outQueue[(size_t) (writePos % (int) outQueue.size())] = outbuf[(size_t) i] / cola;
            ++writePos;
        }
        std::copy (outbuf.begin() + hop, outbuf.end(), outbuf.begin());
        std::fill (outbuf.end() - hop, outbuf.end(), 0.0f);
    }

    std::unique_ptr<juce::dsp::FFT> fft;
    std::vector<float> window, inbuf, outbuf, fftbuf, carry, outQueue, binGain;
    std::vector<double> binFreq;
    float cola = 1.0f;
    int n = 0, hop = 0, carryCount = 0, readPos = 0, writePos = 0;
};
} // namespace lesss::dsp
