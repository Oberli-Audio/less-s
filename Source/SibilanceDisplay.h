#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_basics/juce_gui_basics.h>

#include "PluginProcessor.h"
#include "oberli/OberliLookAndFeel.h"

#include <array>
#include <deque>

/*  Less S - the SIBILANCE display, the editor's hero (sketch 2, 4.3, 4.4): what the ear cannot
    judge, in one sunken well.

      - The spectrum: input (dashed, ink-muted) against output (ink), 1/6 octave from the
        processor's two Analysers (Source/oberli/Analysis.h), 20 Hz to 20 kHz, -60 to 0 dB.
      - The detection band, drawn from k::detectorMagnitude - the function the detector's
        filters are designed from - so the picture cannot drift from the audio (rule 9); its
        -3 dB edges are the legend's "Band 5.1 to 9.8 kHz". The centre line carries the accent.
      - The band-level histogram strip on the well's left edge (64 px, sharing the level axis):
        the detector's band level (`bandLevelDb()`), 1 dB bins, decaying over 8 s, with the
        Threshold line across the strip only and the region above it tinted with the accent.
        With Relative on the axis is dB relative, -30 to +10. The line drags (one gesture,
        begin/perform/end through a ParameterAttachment). A machine-local toggle hides the strip.
      - The ess map under the well: every caught ess of the last 8 s as a bar of its depth (the
        Range ceiling at full height), a clip-coloured tick where it hit Range; the legend counts.

    Message thread only. The editor calls advance() every frame; the display drains the ess
    ring, samples the band level and repaints at most 30 times a second. */
class SibilanceDisplay final : public juce::Component,
                               public juce::SettableTooltipClient
{
public:
    explicit SibilanceDisplay (LessSAudioProcessor&);
    ~SibilanceDisplay() override;

    void setHistogramVisible (bool shouldShow);
    bool isHistogramVisible() const noexcept { return showHistogram; }

    void advance (double now, float dt);

    void paint (juce::Graphics&) override;
    void mouseDown (const juce::MouseEvent&) override;
    void mouseDrag (const juce::MouseEvent&) override;
    void mouseUp (const juce::MouseEvent&) override;
    void mouseMove (const juce::MouseEvent&) override;

    static constexpr int kStripWidth = 64;
    static constexpr int kMapHeight = 40;
    static constexpr int kLegendHeight = 16;
    static constexpr double kWindowSeconds = 8.0;

private:
    struct Event { double start; float duration, depth; bool hitRange; };

    juce::Rectangle<float> wellArea() const;
    juce::Rectangle<float> stripArea() const;
    juce::Rectangle<float> spectrumArea() const;
    juce::Rectangle<float> mapArea() const;
    juce::Rectangle<float> legendArea() const;

    float xForHz (double hz, juce::Rectangle<float> area) const noexcept;
    float yForDb (float db, juce::Rectangle<float> area) const noexcept;
    float stripLow() const noexcept  { return relative ? -30.0f : -60.0f; }
    float stripHigh() const noexcept { return relative ? 10.0f : 0.0f; }
    float yForStripDb (float db, juce::Rectangle<float> area) const noexcept;
    float stripDbForY (float y) const noexcept;
    bool onThresholdLine (juce::Point<float>) const;
    std::pair<double, double> bandEdges() const;

    void paintSpectrum (juce::Graphics&, juce::Rectangle<float>);
    void paintStrip (juce::Graphics&, juce::Rectangle<float>);
    void paintMap (juce::Graphics&, juce::Rectangle<float>);
    void paintLegend (juce::Graphics&, juce::Rectangle<float>);

    LessSAudioProcessor& audio;
    juce::AudioProcessorValueTreeState& apvts;
    juce::ParameterAttachment thresholdAttachment;
    float threshold = -28.0f;

    std::array<double, 61> binsAbsolute {};  // -60..0 dB, 1 dB bins
    std::array<double, 41> binsRelative {};  // -30..+10 dB, 1 dB bins
    bool relative = false;
    bool showHistogram = true;
    bool draggingThreshold = false;

    std::deque<Event> events;
    double clock = 0.0;
    float sinceRepaint = 0.0f;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (SibilanceDisplay)
};
