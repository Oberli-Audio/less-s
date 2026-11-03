#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_dsp/juce_dsp.h>

#include <array>
#include <atomic>
#include <cstring>

#include "Params.h"
#include "dsp/Engine.h"
#include "oberli/Analysis.h"
#include "oberli/MeterTaps.h"
#include "oberli/PresetLibrary.h"

/*  Less S - the processor.

    Thread model (sound-design-bob rule 1, D.1): the audio thread reads parameters through
    cached atomics, never by string lookup; nothing on the audio thread allocates, locks or
    logs; every parameter that reaches the audio path is smoothed with the table's tau
    (Params::smoothing), inside the engine. State is State.h's format. The editor reads what
    the processor publishes as atomics and one lock-free ring.

    The DSP itself is `Source/dsp/Engine.h`, ported by structure from
    `sound design/proto/less_s.py` (G4); this class only moves parameters in and meters out,
    reports latency (rule 7) and drives Learn off the audio thread. */
class LessSAudioProcessor final : public juce::AudioProcessor,
                                  private juce::Timer
{
public:
    LessSAudioProcessor();
    ~LessSAudioProcessor() override;

    // AudioProcessor
    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    void processBlockBypassed (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override;
    juce::AudioProcessorParameter* getBypassParameter() const override;

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return "Default"; }   // not empty: the Steinberg validator fails "Scan Programs" (pluginval L10)
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    /** setStateInformation's work, with a verdict: false when the bytes are not a state of this
        plugin (foreign, truncated, newer); the state is then unchanged. The harness reports it. */
    bool loadState (const void* data, int sizeInBytes);

    /** The parameter tree; the editor attaches to it, the harness sets values through it. */
    juce::AudioProcessorValueTreeState& parameters() { return apvts; }

    //==========================================================================
    // What the editor may read from the audio thread (D.6.2).

    /** The 20 ms RMS per channel of the output. */
    float outputLevel (int channel) const noexcept
    {
        return channel == 0 ? rmsL.load (std::memory_order_relaxed) : rmsR.load (std::memory_order_relaxed);
    }

    /** The gain reduction in dB (positive = reducing), for the GR meter. */
    float gainReductionDb() const noexcept { return engine.gainReductionDb(); }

    /** The detector's band level in dB - dB relative when Relative is on - which is what
        the histogram strip bins (sketch 4.3). */
    float bandLevelDb() const noexcept { return engine.bandLevelDb(); }

    /** The next caught ess, or false when the ring is empty (the ess map, sketch 4.4). */
    bool popEssEvent (lesss::dsp::EssEvent& out) noexcept { return engine.popEvent (out); }

    /** The engine's clock in seconds, the time base of the ess events. */
    double audioSeconds() const noexcept { return audioClock.load (std::memory_order_relaxed); }

    /** The output's sample peak and clip flag, and the gain reduction, for the meters
        (Source/oberli/MeterTaps.h). In Ess listen the output is the band, so the level meter
        shows the band's level (sketch 4.5). */
    oberli::PeakTap& outputPeaks() noexcept { return peaks; }
    oberli::GainReductionTap& gainReductionTap() noexcept { return grTap; }

    /** Input and output spectrum for the display, 1/6 octave. Fed only while an editor is
        open and the host plays in real time (Source/oberli/RenderSafety.h): the audio path
        never depends on either. */
    oberli::Analyser& inputSpectrum() noexcept { return inAnalyser; }
    oberli::Analyser& outputSpectrum() noexcept { return outAnalyser; }
    void setDisplayActive (bool active) noexcept { displayActive.store (active, std::memory_order_relaxed); }

    /** The presets (the factory bank compiled in, the User folder, the active one): the Strip
        frame's header, drawer and menu work on it. Message thread. */
    oberli::PresetLibrary& presetLibrary() noexcept { return *presets; }
    oberli::PresetHost& presetHost() noexcept { return *presets; }

    //==========================================================================
    // Learn (sketch 4.2). The analysis never runs on the audio thread.

    /** The editor's Learn button and the host menu item: capture the next two seconds. */
    void requestLearn();

    /** True when two seconds are captured and `runLearnNow` would do the analysis. The
        harness uses this after a render; in a host the timer below does it. */
    bool learnPending() const noexcept { return engine.learnReady(); }

    /** Runs the analysis and writes Frequency and Width through begin/perform/end edit,
        so the host records one undo step. Message thread only. */
    lesss::dsp::LearnResult runLearnNow();

    /** The last Learn result, for the editor's "No esses found yet" line and the harness. */
    lesss::dsp::LearnResult lastLearnResult() const { return lastLearn; }

    /** How many Learn analyses have run (message thread), so the editor sees a new result. */
    int learnCount() const noexcept { return learnRuns; }

    /** Learn's captured share 0..1, or -1 when it is not capturing (the hairline). */
    float learnProgress() const noexcept { return engine.learnProgress(); }

private:
    void timerCallback() override;
    lesss::dsp::Parameters readParameters() const noexcept;
    void updateLatency (const lesss::dsp::Parameters& p);

    juce::AudioProcessorValueTreeState apvts;

    // cached parameter pointers (never string lookups on the audio thread)
    std::atomic<float>* frequencyParam = nullptr;
    std::atomic<float>* widthParam = nullptr;
    std::atomic<float>* thresholdParam = nullptr;
    std::atomic<float>* rangeParam = nullptr;
    std::atomic<float>* modeParam = nullptr;
    std::atomic<float>* autoLearnParam = nullptr;
    std::atomic<float>* relativeParam = nullptr;
    std::atomic<float>* speedParam = nullptr;
    std::atomic<float>* lookaheadParam = nullptr;
    std::atomic<float>* listenParam = nullptr;
    std::atomic<float>* stereoParam = nullptr;
    std::atomic<float>* mixParam = nullptr;
    std::atomic<float>* bypassParam = nullptr;

    lesss::dsp::Engine engine;
    lesss::dsp::LearnResult lastLearn;
    int learnRuns = 0;
    std::atomic<double> audioClock { 0.0 };
    oberli::PeakTap peaks;
    oberli::GainReductionTap grTap;
    oberli::Analyser inAnalyser, outAnalyser;
    std::atomic<bool> displayActive { false };
    std::unique_ptr<oberli::PresetLibrary> presets;
    double currentSampleRate = 48000.0;
    int reportedLatency = 0;
    std::atomic<float> rmsL { 0.0f }, rmsR { 0.0f };
    juce::dsp::BallisticsFilter<float> rmsFilterL, rmsFilterR;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (LessSAudioProcessor)
};
