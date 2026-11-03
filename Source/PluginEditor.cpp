#include "PluginEditor.h"
#include "BuildInfo.h"
#include "Params.h"
#include "State.h"
#include "oberli/Folders.h"

#include <ProductData.h>

namespace
{
using namespace oberli::ui;

constexpr int kBodyWidth = 824;     // 880 at 100 % with the 28 px padding
constexpr int kBodyHeight = 508;    // 612 with the header and the padding
constexpr int kDetectWidth = 222;
constexpr int kReduceWidth = 370;
constexpr int kGroupGap = Tokens::space6;
constexpr int kTitle = 14;
constexpr int kRow = Tokens::controlHeight;
constexpr const char* kHistogramKey = "lessS.histogram";   // MachineSettings: machine-local, like the GUI scale

/** A document compiled into the plugin (CMakeLists.txt: ProductData), by its file name. */
juce::String embedded (const char* fileName)
{
    int size = 0;
    for (int i = 0; i < ProductData::namedResourceListSize; ++i)
        if (juce::String (ProductData::getNamedResourceOriginalFilename (ProductData::namedResourceList[i])) == fileName)
            if (const auto* data = ProductData::getNamedResource (ProductData::namedResourceList[i], size))
                return juce::String::fromUTF8 (data, size);
    return {};
}

StripEditor::Info infoFor()
{
    StripEditor::Info info;
    info.productName = JucePlugin_Name;
    info.version = PRODUCT_VERSION;
    info.what = "A de-esser by Oberli Audio. It finds the ess band, takes only the esses down, and shows you what it caught.";
    info.licences = embedded ("LICENSE") + "\n\n" + embedded ("THIRD_PARTY_NOTICES.md");
    info.soundVersion = lesss::State::kDspVersion;
    return info;
}

juce::String nameOf (juce::AudioProcessorValueTreeState& apvts, const char* id)
{
    return apvts.getParameter (id)->getName (12);
}

/** PillToggle::getPreferredWidth measures the caps without the label font's 0.10 tracking, so a
    long word is clipped ("RELATI"); this adds the tracking back (a template item, docs/status.md). */
int pillWidth (const PillToggle& t)
{
    return t.getPreferredWidth() + juce::roundToInt (std::ceil (0.10f * 11.0f * (float) t.getButtonText().length()));
}

bool histogramPreference()
{
    auto settings = oberli::MachineSettings::open();
    return settings == nullptr || settings->getBoolValue (kHistogramKey, true);
}
} // namespace

LessSAudioProcessorEditor::LessSAudioProcessorEditor (LessSAudioProcessor& p)
    : StripEditor (p, p.presetHost(), infoFor()),
      audioProcessor (p),
      learn ("Learn", ActionButton::Variant::secondary),
      histogram ("Histogram"),
      display (p),
      grMeter (p.gainReductionTap(), 24.0f),
      outMeter (p.outputPeaks(), LevelMeter::Led::clip)
{
    frequency = &addKnob (Params::frequency, Tokens::knobLg);
    width = &addKnob (Params::width, Tokens::knobLg);
    threshold = &addKnob (Params::threshold, Tokens::knobLg);
    range = &addKnob (Params::range, Tokens::knobMd);
    lookahead = &addKnob (Params::lookahead, Tokens::knobMd);
    mix = &addKnob (Params::mix, Tokens::knobLg);

    autoLearn = &addToggle (Params::autoLearn);
    relative = &addToggle (Params::relative);
    listen = &addSegments (Params::listen);
    mode = &addSegments (Params::mode);
    speed = &addSegments (Params::speed);
    stereo = &addSegments (Params::stereo);

    learn.setTooltip ("Listens to the next two seconds of singing and sets Frequency and Width once.");
    learn.onClick = [this] { audioProcessor.requestLearn(); };
    addAndMakeVisible (learn);

    histogram.setClickingTogglesState (true);
    histogram.setToggleState (histogramPreference(), juce::dontSendNotification);
    histogram.setTooltip ("Shows the band-level histogram with the Threshold line. Kept on this computer, not in the session.");
    display.setHistogramVisible (histogram.getToggleState());
    histogram.onClick = [this]
    {
        display.setHistogramVisible (histogram.getToggleState());
        if (auto settings = oberli::MachineSettings::open())
            settings->setValue (kHistogramKey, histogram.getToggleState());
    };
    addAndMakeVisible (histogram);
    addAndMakeVisible (display);
    addAndMakeVisible (grMeter);
    addAndMakeVisible (outMeter);

    seenLearnCount = audioProcessor.learnCount();
    setBodySize (kBodyWidth, kBodyHeight);
    audioProcessor.presetLibrary().writeFactoryFolder();   // the bank as files, once per version
}

LessSAudioProcessorEditor::~LessSAudioProcessorEditor() = default;

ParameterKnob& LessSAudioProcessorEditor::addKnob (const char* id, int size)
{
    auto& apvts = audioProcessor.parameters();
    auto k = std::make_unique<ParameterKnob> (apvts, id, nameOf (apvts, id), size);
    const juce::String tip (Params::tooltipFor (id));
    k->knob().setTooltip (tip);
    k->knob().setHelpText (tip);
    addAndMakeVisible (*k);
    knobs.push_back (std::move (k));
    return *knobs.back();
}

SegmentedControl& LessSAudioProcessorEditor::addSegments (const char* id)
{
    auto* choice = dynamic_cast<juce::AudioParameterChoice*> (audioProcessor.parameters().getParameter (id));
    jassert (choice != nullptr);
    auto s = std::make_unique<SegmentedControl> (choice->choices);
    s->attach (*choice);
    s->setTooltip (Params::tooltipFor (id));
    s->setTitle (choice->getName (32));
    addAndMakeVisible (*s);
    segments.push_back (std::move (s));
    return *segments.back();
}

PillToggle& LessSAudioProcessorEditor::addToggle (const char* id)
{
    auto& apvts = audioProcessor.parameters();
    auto t = std::make_unique<PillToggle> (nameOf (apvts, id));
    t->setTooltip (Params::tooltipFor (id));
    toggleAttachments.push_back (std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (apvts, id, *t));
    addAndMakeVisible (*t);
    toggles.push_back (std::move (t));
    return *toggles.back();
}

//==============================================================================
void LessSAudioProcessorEditor::layoutBody (juce::Rectangle<int> area)
{
    captions.clear();
    auto caption = [this] (const juce::String& text, juce::Rectangle<int> box) { captions.push_back ({ text, box }); };
    auto place = [] (ParameterKnob& k, int x, int y) { k.setBounds (x, y, k.getPreferredWidth(), k.getPreferredHeight()); };

    // OUTPUT, last on the right after a hairline
    const auto outputWidth = GainReductionMeter::kWidth + Tokens::space2 + outMeter.getPreferredWidth();
    auto output = area.removeFromRight (outputWidth);
    area.removeFromRight (kGroupGap);
    outputRule = area.removeFromRight (1);
    area.removeFromRight (kGroupGap);

    caption ("OUTPUT", output.removeFromTop (kTitle));
    output.removeFromTop (Tokens::space3);
    mix->setBounds (output.removeFromTop (mix->getPreferredHeight()).withSizeKeepingCentre (mix->getPreferredWidth(), mix->getPreferredHeight()));
    output.removeFromTop (Tokens::space5);
    auto meters = output.removeFromTop (GainReductionMeter::kHeight);
    grMeter.setBounds (meters.removeFromLeft (GainReductionMeter::kWidth));
    meters.removeFromLeft (Tokens::space2);
    outMeter.setBounds (meters.removeFromLeft (outMeter.getPreferredWidth()));

    // the top band: DETECT and REDUCE
    auto top = area.removeFromTop (276);
    auto detect = top.removeFromLeft (kDetectWidth);
    top.removeFromLeft (kGroupGap);
    auto reduce = top.removeFromLeft (kReduceWidth);

    // DETECT
    caption ("DETECT", detect.removeFromTop (kTitle));
    detect.removeFromTop (Tokens::space3);
    place (*frequency, detect.getX(), detect.getY());
    place (*width, frequency->getRight() + Tokens::space5, detect.getY());
    detect.removeFromTop (frequency->getPreferredHeight() + Tokens::space3);
    auto row = detect.removeFromTop (kRow);
    learn.setBounds (row.removeFromLeft (learn.getPreferredWidth()));
    learnHairline = juce::Rectangle<int> (learn.getX() + 6, learn.getBottom() + 3, learn.getWidth() - 12, 2);
    row.removeFromLeft (Tokens::space2);
    autoLearn->setBounds (row.removeFromLeft (pillWidth (*autoLearn)));
    detect.removeFromTop (Tokens::space2);
    relative->setBounds (detect.removeFromTop (kRow).withWidth (pillWidth (*relative)));
    detect.removeFromTop (Tokens::space4);
    caption ("LISTEN", detect.removeFromTop (kTitle));
    detect.removeFromTop (Tokens::space2);
    listen->setBounds (detect.removeFromTop (kRow).withWidth (kDetectWidth));

    // REDUCE
    caption ("REDUCE", reduce.removeFromTop (kTitle));
    reduce.removeFromTop (Tokens::space3);
    place (*threshold, reduce.getX(), reduce.getY());
    const auto smallY = reduce.getY() + (Tokens::knobLg - Tokens::knobMd) / 2;
    place (*range, threshold->getRight() + Tokens::space5, smallY);
    place (*lookahead, range->getRight() + Tokens::space5, smallY);
    reduce.removeFromTop (threshold->getPreferredHeight() + Tokens::space3);
    caption ("MODE", reduce.removeFromTop (kTitle));
    reduce.removeFromTop (Tokens::space2);
    mode->setBounds (reduce.removeFromTop (kRow));
    reduce.removeFromTop (Tokens::space4);
    auto labels = reduce.removeFromTop (kTitle);
    reduce.removeFromTop (Tokens::space2);
    auto pair = reduce.removeFromTop (kRow);
    const auto half = juce::jmax ((pair.getWidth() - Tokens::space4) / 2, speed->getPreferredWidth());
    caption ("SPEED", labels.removeFromLeft (half));
    labels.removeFromLeft (Tokens::space4);
    caption ("STEREO", labels);
    speed->setBounds (pair.removeFromLeft (half));
    pair.removeFromLeft (Tokens::space4);
    stereo->setBounds (pair);

    // SIBILANCE, the hero, under both
    area.removeFromTop (Tokens::space4);
    auto head = area.removeFromTop (kRow);
    caption ("SIBILANCE", head.withHeight (kRow).withTrimmedRight (200));
    histogram.setBounds (head.removeFromRight (histogram.getPreferredWidth()));
    area.removeFromTop (Tokens::space2);
    display.setBounds (area);
}

void LessSAudioProcessorEditor::paint (juce::Graphics& g)
{
    StripEditor::paint (g);
    const auto& t = front();
    for (const auto& c : captions)
        type::draw (g, c.text, c.box.toFloat().withHeight ((float) kTitle).withY ((float) c.box.getCentreY() - kTitle * 0.5f),
                    type::section(), t.inkMuted);
    g.setColour (t.line);
    g.fillRect (outputRule);

    // Learn capturing: a 2 s hairline under the button (sketch 2, states)
    if (learnProgress >= 0.0f)
    {
        g.setColour (t.lineStrong);
        g.fillRect (learnHairline);
        g.setColour (Tokens::accent());
        g.fillRect (learnHairline.withWidth (juce::roundToInt ((float) learnHairline.getWidth() * learnProgress)));
    }
}

void LessSAudioProcessorEditor::advanceBody (double now, float dt)
{
    for (auto& k : knobs)
        k->advance (now, dt);
    grMeter.advance (now, dt);
    outMeter.advance (now, dt);
    display.advance (now, dt);

    // Spectral: the STFT frame already looks ahead, so Lookahead has nothing to do (sketch 2)
    const auto spectral = mode->getSelected() == 2;
    if (lookahead->isEnabled() == spectral)
        lookahead->setEnabled (! spectral);

    const auto progress = audioProcessor.learnProgress();
    if (! juce::approximatelyEqual (progress, learnProgress))
    {
        learnProgress = progress;
        repaint (learnHairline.expanded (1));
    }
    if (audioProcessor.learnCount() != seenLearnCount)
    {
        seenLearnCount = audioProcessor.learnCount();
        if (! audioProcessor.lastLearnResult().found)
            showToast ("No esses found yet: sing a phrase with some s in it", learn.getBounds());
    }
}

void LessSAudioProcessorEditor::presetRecalled (double now)
{
    // the knobs glide to the recalled values one after another, left to right
    auto start = now;
    for (auto& k : knobs)
    {
        k->knob().beginWave (start, false);
        start += 0.04;
    }
}

bool LessSAudioProcessorEditor::previewDrag (const juce::String& parameterId)
{
    auto* parameter = audioProcessor.parameters().getParameter (parameterId);
    if (parameter == nullptr)
        return false;
    for (auto& k : knobs)
        if (k->knob().getTitle() == parameter->getName (64))
        {
            k->knob().setDragPreview (true);
            return true;
        }
    return false;
}
