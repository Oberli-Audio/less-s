#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_basics/juce_gui_basics.h>

#include "PluginProcessor.h"
#include "SibilanceDisplay.h"
#include "oberli/Buttons.h"
#include "oberli/Knob.h"
#include "oberli/Meters.h"
#include "oberli/StripEditor.h"

/*  Less S - the editor (plugin-ui-bob, Tier P), built from docs/sketch.md and the brand sheet:
    the family's Strip frame (Source/oberli/StripEditor.h) around one body, Bone, accent sage.

      DETECT    Frequency and Width (knob-lg); Learn under Frequency (owner decision, brief
                amendment 2026-11-01), the Auto and Relative switches; Listen
      REDUCE    Threshold (knob-lg), Range and Lookahead (knob-md; Lookahead disabled in
                Spectral, where the frame is the look-ahead); Mode; Speed and Stereo
      SIBILANCE the hero (SibilanceDisplay): spectrum, band-level histogram with the Threshold
                line, ess map; the Histogram switch is machine-local, not a parameter
      OUTPUT    last on the right after a hairline: Mix (knob-lg), the GR and level meters

    Window 880 x 612 at 100 %. Parameter names, value strings and tooltips come from
    parameters.csv (Params.h); this file never types a parameter's text. */
class LessSAudioProcessorEditor final : public oberli::ui::StripEditor
{
public:
    explicit LessSAudioProcessorEditor (LessSAudioProcessor&);
    ~LessSAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;

    /** Shows a knob's drag readout without a mouse (the snapshot tool). False for an unknown ID. */
    bool previewDrag (const juce::String& parameterId) override;

private:
    void layoutBody (juce::Rectangle<int> area) override;
    void advanceBody (double now, float dt) override;
    void presetRecalled (double now) override;

    oberli::ui::ParameterKnob& addKnob (const char* id, int size);
    oberli::ui::SegmentedControl& addSegments (const char* id);
    oberli::ui::PillToggle& addToggle (const char* id);

    LessSAudioProcessor& audioProcessor;   // not `processor`: AudioProcessorEditor has one (-Wshadow)

    std::vector<std::unique_ptr<oberli::ui::ParameterKnob>> knobs;   // in wave order, left to right
    oberli::ui::ParameterKnob *frequency = nullptr, *width = nullptr, *threshold = nullptr,
                              *range = nullptr, *lookahead = nullptr, *mix = nullptr;
    std::vector<std::unique_ptr<oberli::ui::SegmentedControl>> segments;
    oberli::ui::SegmentedControl *listen = nullptr, *mode = nullptr, *speed = nullptr, *stereo = nullptr;
    std::vector<std::unique_ptr<oberli::ui::PillToggle>> toggles;
    std::vector<std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment>> toggleAttachments;
    oberli::ui::PillToggle *autoLearn = nullptr, *relative = nullptr;

    oberli::ui::ActionButton learn;
    oberli::ui::PillToggle histogram;
    SibilanceDisplay display;
    oberli::ui::GainReductionMeter grMeter;
    oberli::ui::LevelMeter outMeter;

    // captions and rules painted by the editor (editor coordinates)
    struct Caption { juce::String text; juce::Rectangle<int> box; };
    std::vector<Caption> captions;
    juce::Rectangle<int> outputRule, learnHairline;
    float learnProgress = -1.0f;
    int seenLearnCount = 0;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (LessSAudioProcessorEditor)
};
