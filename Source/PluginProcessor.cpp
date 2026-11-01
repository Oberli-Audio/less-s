#include "PluginProcessor.h"
#include "PluginEditor.h"
#include "State.h"

#include <cmath>

namespace
{
std::atomic<float>* param (juce::AudioProcessorValueTreeState& apvts, const char* id)
{
    auto* p = apvts.getRawParameterValue (id);
    jassert (p != nullptr);   // the table and the code disagree: parameters.csv is the source
    return p;
}
} // namespace

LessSAudioProcessor::LessSAudioProcessor()
    : AudioProcessor (BusesProperties()
                          .withInput ("Input", juce::AudioChannelSet::stereo(), true)
                          .withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      apvts (*this, nullptr, "PARAMETERS", Params::createParameterLayout())
{
    frequencyParam = param (apvts, Params::frequency);
    widthParam = param (apvts, Params::width);
    thresholdParam = param (apvts, Params::threshold);
    rangeParam = param (apvts, Params::range);
    modeParam = param (apvts, Params::mode);
    autoLearnParam = param (apvts, Params::autoLearn);
    relativeParam = param (apvts, Params::relative);
    speedParam = param (apvts, Params::speed);
    lookaheadParam = param (apvts, Params::lookahead);
    listenParam = param (apvts, Params::listen);
    stereoParam = param (apvts, Params::stereo);
    mixParam = param (apvts, Params::mix);
    bypassParam = param (apvts, Params::bypassParameterId);

    // 20 Hz is often enough for Learn: the analysis needs two seconds of audio first, so
    // the poll costs one atomic read per 50 ms (D.1: never triggerAsyncUpdate from audio).
    if (juce::MessageManager::getInstanceWithoutCreating() != nullptr)
        startTimer (50);
}

LessSAudioProcessor::~LessSAudioProcessor()
{
    stopTimer();
}

lesss::dsp::Parameters LessSAudioProcessor::readParameters() const noexcept
{
    lesss::dsp::Parameters p;
    p.frequency = frequencyParam->load();
    p.width = widthParam->load();
    p.threshold = thresholdParam->load();
    p.range = rangeParam->load();
    p.mode = (int) std::lround (modeParam->load());
    p.autoLearn = autoLearnParam->load() >= 0.5f;
    p.relative = relativeParam->load() >= 0.5f;
    p.speed = (int) std::lround (speedParam->load());
    p.lookaheadMs = lookaheadParam->load();
    p.listen = (int) std::lround (listenParam->load());
    p.stereo = (int) std::lround (stereoParam->load());
    p.mix = mixParam->load();
    p.bypass = bypassParam->load() >= 0.5f;
    return p;
}

void LessSAudioProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    currentSampleRate = sampleRate;
    engine.prepare (sampleRate, juce::jmax (1, samplesPerBlock));

    juce::dsp::ProcessSpec spec { sampleRate, (juce::uint32) juce::jmax (1, samplesPerBlock), 1 };
    for (auto* f : { &rmsFilterL, &rmsFilterR })
    {
        f->prepare (spec);
        f->setLevelCalculationType (juce::dsp::BallisticsFilterLevelCalculationType::RMS);
        f->setAttackTime (20.0f);
        f->setReleaseTime (20.0f);
    }
    rmsL.store (0.0f);
    rmsR.store (0.0f);

    const auto p = readParameters();
    reportedLatency = engine.latencyFor (p);
    setLatencySamples (reportedLatency);
}

void LessSAudioProcessor::releaseResources() {}

bool LessSAudioProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    if (layouts.getMainOutputChannelSet() != juce::AudioChannelSet::stereo())
        return false;
    return layouts.getMainInputChannelSet() == juce::AudioChannelSet::stereo()
        || layouts.getMainInputChannelSet() == juce::AudioChannelSet::mono();
}

double LessSAudioProcessor::getTailLengthSeconds() const
{
    // A de-esser has no tail of its own; what it does have is reported latency, which the
    // host compensates separately. Lookahead and the STFT frame are not a tail (D.2.5).
    return 0.0;
}

juce::AudioProcessorParameter* LessSAudioProcessor::getBypassParameter() const
{
    return apvts.getParameter (Params::bypassParameterId);
}

void LessSAudioProcessor::updateLatency (const lesss::dsp::Parameters& p)
{
    const int wanted = engine.latencyFor (p);
    if (wanted != reportedLatency)
    {
        reportedLatency = wanted;
        // Changing Mode or Lookahead changes the latency; the host re-measures. The sketch
        // (4.7) accepts that a change while the transport runs may click once.
        setLatencySamples (wanted);
    }
}

void LessSAudioProcessor::processBlockBypassed (juce::AudioBuffer<float>& buffer, juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    for (int ch = getTotalNumInputChannels(); ch < getTotalNumOutputChannels(); ++ch)
        buffer.clear (ch, 0, buffer.getNumSamples());
    if (buffer.getNumSamples() == 0)
        return;
    // rule 7: the bypassed path is delayed by the reported latency, so it nulls against the
    // input and switching bypass does not shift the signal in time.
    auto p = readParameters();
    p.bypass = true;
    engine.process (buffer, p);
}

void LessSAudioProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;
    juce::ignoreUnused (midi);
    const int numSamples = buffer.getNumSamples();
    for (int ch = getTotalNumInputChannels(); ch < getTotalNumOutputChannels(); ++ch)
        buffer.clear (ch, 0, numSamples);
    if (numSamples == 0)   // a zero-length block is legal (harness contract, D.5.1)
        return;

    const auto p = readParameters();
    updateLatency (p);
    engine.process (buffer, p);

    // the level the editor shows (20 ms RMS per channel, D.6.2)
    auto* l = buffer.getWritePointer (0);
    auto* r = buffer.getNumChannels() > 1 ? buffer.getWritePointer (1) : nullptr;
    float lastL = 0.0f, lastR = 0.0f;
    for (int i = 0; i < numSamples; ++i)
    {
        lastL = rmsFilterL.processSample (0, l[i]);
        if (r != nullptr)
            lastR = rmsFilterR.processSample (0, r[i]);
    }
    rmsL.store (lastL, std::memory_order_relaxed);
    rmsR.store (r != nullptr ? lastR : lastL, std::memory_order_relaxed);
}

//==============================================================================
void LessSAudioProcessor::requestLearn()
{
    engine.requestLearn();
}

lesss::dsp::LearnResult LessSAudioProcessor::runLearnNow()
{
    const auto result = engine.runLearn();
    lastLearn = result;
    if (! result.found)
        return result;
    // Written as a user edit so the host records one undo step and the preset shows
    // modified (sketch 4.2). Nothing else is touched: Learn is not a tracker.
    struct Write { const char* id; float value; };
    const Write writes[] = { { Params::frequency, (float) result.frequency },
                             { Params::width, (float) result.width } };
    for (const auto& w : writes)
        if (auto* p = apvts.getParameter (w.id))
        {
            p->beginChangeGesture();
            p->setValueNotifyingHost (p->convertTo0to1 (w.value));
            p->endChangeGesture();
        }
    return result;
}

void LessSAudioProcessor::timerCallback()
{
    if (engine.learnReady())
        runLearnNow();
}

//==============================================================================
juce::AudioProcessorEditor* LessSAudioProcessor::createEditor()
{
    return new LessSAudioProcessorEditor (*this);
}

void LessSAudioProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    copyXmlToBinary (*lesss::State::toXml (apvts), destData);
}

void LessSAudioProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    loadState (data, sizeInBytes);
}

bool LessSAudioProcessor::loadState (const void* data, int sizeInBytes)
{
    // arbitrary bytes are refused, never crashed on (D.5.3): a foreign or newer blob leaves the state as it is
    if (data == nullptr || sizeInBytes <= 0)
        return false;
    auto xml = getXmlFromBinary (data, sizeInBytes);
    if (xml == nullptr)
        return false;
    auto* state = lesss::State::stateOf (*xml);
    return state != nullptr && lesss::State::fromXml (*state, apvts);
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new LessSAudioProcessor();
}
