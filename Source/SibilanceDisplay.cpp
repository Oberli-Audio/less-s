#include "SibilanceDisplay.h"
#include "Params.h"
#include "dsp/Constants.h"

#include <cmath>

namespace
{
using namespace oberli::ui;
namespace k = lesss::dsp::k;

constexpr double kLowHz = 20.0, kHighHz = 20000.0;
constexpr float kSpecLowDb = -60.0f, kSpecHighDb = 0.0f;
constexpr double kHistogramTau = SibilanceDisplay::kWindowSeconds / 3.0;   // a bin falls to 5 % in 8 s
constexpr int kGap = 6;   // well, map and legend

float plainOf (juce::AudioProcessorValueTreeState& apvts, const char* id)
{
    return apvts.getRawParameterValue (id)->load();
}

juce::String hzText (double hz)
{
    return hz >= 1000.0 ? juce::String (hz / 1000.0, hz >= 10000.0 ? 1 : 1) + " kHz" : juce::String (juce::roundToInt (hz)) + " Hz";
}
} // namespace

SibilanceDisplay::SibilanceDisplay (LessSAudioProcessor& p)
    : audio (p),
      apvts (p.parameters()),
      thresholdAttachment (*p.parameters().getParameter (Params::threshold),
                           [this] (float v) { threshold = v; repaint(); }, nullptr)
{
    thresholdAttachment.sendInitialUpdate();
    setOpaque (false);
    setTitle ("Sibilance");
    setDescription ("Spectrum, band-level histogram and ess map");
    setTooltip ("Two humps in the strip: put Threshold in the valley between them. Drag the line to set it.");
    audio.setDisplayActive (true);
}

SibilanceDisplay::~SibilanceDisplay()
{
    audio.setDisplayActive (false);
}

void SibilanceDisplay::setHistogramVisible (bool shouldShow)
{
    showHistogram = shouldShow;
    repaint();
}

//==============================================================================
// geometry

juce::Rectangle<float> SibilanceDisplay::legendArea() const
{
    return getLocalBounds().toFloat().removeFromBottom ((float) kLegendHeight);
}

juce::Rectangle<float> SibilanceDisplay::mapArea() const
{
    auto r = getLocalBounds().toFloat();
    r.removeFromBottom ((float) (kLegendHeight + kGap));
    return r.removeFromBottom ((float) kMapHeight);
}

juce::Rectangle<float> SibilanceDisplay::wellArea() const
{
    auto r = getLocalBounds().toFloat();
    r.removeFromBottom ((float) (kLegendHeight + kGap + kMapHeight + kGap));
    return r;
}

juce::Rectangle<float> SibilanceDisplay::stripArea() const
{
    return showHistogram ? wellArea().removeFromLeft ((float) kStripWidth) : juce::Rectangle<float>();
}

juce::Rectangle<float> SibilanceDisplay::spectrumArea() const
{
    auto r = wellArea();
    if (showHistogram)
        r.removeFromLeft ((float) kStripWidth);
    return r;
}

float SibilanceDisplay::xForHz (double hz, juce::Rectangle<float> a) const noexcept
{
    const auto t = std::log (juce::jlimit (kLowHz, kHighHz, hz) / kLowHz) / std::log (kHighHz / kLowHz);
    return a.getX() + (float) t * a.getWidth();
}

float SibilanceDisplay::yForDb (float db, juce::Rectangle<float> a) const noexcept
{
    // below the floor the curve drops out of the well (clipped) instead of crawling along its edge
    const auto t = (juce::jlimit (kSpecLowDb - 6.0f, kSpecHighDb, db) - kSpecLowDb) / (kSpecHighDb - kSpecLowDb);
    return a.getBottom() - t * a.getHeight();
}

float SibilanceDisplay::yForStripDb (float db, juce::Rectangle<float> a) const noexcept
{
    const auto t = (juce::jlimit (stripLow(), stripHigh(), db) - stripLow()) / (stripHigh() - stripLow());
    return a.getBottom() - t * a.getHeight();
}

float SibilanceDisplay::stripDbForY (float y) const noexcept
{
    const auto a = stripArea();
    const auto t = juce::jlimit (0.0f, 1.0f, (a.getBottom() - y) / juce::jmax (1.0f, a.getHeight()));
    return stripLow() + t * (stripHigh() - stripLow());
}

/** The detector's -3 dB edges, found on k::detectorMagnitude itself (rule 9). */
std::pair<double, double> SibilanceDisplay::bandEdges() const
{
    const double f0 = plainOf (apvts, Params::frequency), bw = plainOf (apvts, Params::width);
    const double half = std::sqrt (0.5);
    auto edge = [&] (double lo, double hi)   // bisection in log frequency between a passing and a rejecting point
    {
        for (int i = 0; i < 40; ++i)
        {
            const double mid = std::sqrt (lo * hi);
            const bool inside = k::detectorMagnitude (mid, f0, bw) >= half;
            const bool loInside = k::detectorMagnitude (lo, f0, bw) >= half;
            (inside == loInside ? lo : hi) = mid;
        }
        return std::sqrt (lo * hi);
    };
    return { edge (kLowHz, f0), edge (f0, kHighHz) };
}

//==============================================================================
// frame

void SibilanceDisplay::advance (double now, float dt)
{
    juce::ignoreUnused (now);
    relative = plainOf (apvts, Params::relative) >= 0.5f;

    // the band-level histogram: this frame's share of time into the band level's bin, all bins decaying
    const auto decay = std::exp (-(double) dt / kHistogramTau);
    for (auto& b : binsAbsolute) b *= decay;
    for (auto& b : binsRelative) b *= decay;
    const auto level = audio.bandLevelDb();
    if (std::isfinite (level))
    {
        double* bins = relative ? binsRelative.data() : binsAbsolute.data();
        const int n = relative ? (int) binsRelative.size() : (int) binsAbsolute.size();
        const int i = (int) std::floor (level - stripLow());
        if (i >= 0 && i < n)
            bins[i] += dt;
    }

    // the ess map: drain the ring, keep the last 8 s on the engine's clock
    clock = audio.audioSeconds();
    lesss::dsp::EssEvent e;
    while (audio.popEssEvent (e))
        events.push_back ({ e.startSeconds, e.durationSeconds, e.depthDb, e.hitRange });
    while (! events.empty() && events.front().start + events.front().duration < clock - kWindowSeconds)
        events.pop_front();

    sinceRepaint += dt;
    if (sinceRepaint >= 1.0f / 30.0f)
    {
        sinceRepaint = 0.0f;
        repaint();
    }
}

//==============================================================================
// paint

void SibilanceDisplay::paint (juce::Graphics& g)
{
    const auto& t = front();
    const auto well = wellArea();

    g.setColour (t.surfaceSunken);
    g.fillRoundedRectangle (well, Tokens::radiusSm);

    {
        juce::Graphics::ScopedSaveState clip (g);
        juce::Path rounded;
        rounded.addRoundedRectangle (well, Tokens::radiusSm);
        g.reduceClipRegion (rounded);
        paintSpectrum (g, spectrumArea());
        if (showHistogram)
            paintStrip (g, stripArea());
    }

    paintMap (g, mapArea());
    paintLegend (g, legendArea());
}

void SibilanceDisplay::paintSpectrum (juce::Graphics& g, juce::Rectangle<float> a)
{
    const auto& t = front();
    const auto listen = (int) std::lround (plainOf (apvts, Params::listen));

    // grid: decades and the level lines the strip shares
    g.setColour (t.line);
    for (double hz : { 100.0, 1000.0, 10000.0 })
        g.drawVerticalLine (juce::roundToInt (xForHz (hz, a)), a.getY(), a.getBottom());
    for (float db : { -30.0f })
        g.drawHorizontalLine (juce::roundToInt (yForDb (db, a)), a.getX(), a.getRight());

    // the detection band: opacity follows the detector's own magnitude (rule 9)
    const double f0 = plainOf (apvts, Params::frequency), bw = plainOf (apvts, Params::width);
    const auto accent = Tokens::accent();
    for (float x = a.getX(); x < a.getRight(); x += 1.0f)
    {
        const auto hz = kLowHz * std::pow (kHighHz / kLowHz, (double) ((x - a.getX()) / a.getWidth()));
        const auto m = (float) k::detectorMagnitude (hz, f0, bw);
        if (m > 0.01f)
        {
            g.setColour (accent.withAlpha (0.24f * m * m));
            g.fillRect (x, a.getY(), 1.0f, a.getHeight());
        }
    }
    g.setColour (accent);
    g.fillRect (xForHz (f0, a) - 1.0f, a.getY(), 2.0f, a.getHeight());

    // the two curves from the analysers: input dashed, output solid
    auto curve = [&] (oberli::Analyser& an)
    {
        juce::Path p;
        const int n = an.numBands();
        bool started = false;
        for (int i = 0; i < n; ++i)
        {
            const auto hz = (double) an.bandCentre (i);
            if (hz < kLowHz || hz > kHighHz)
                continue;
            const juce::Point<float> pt (xForHz (hz, a), yForDb (an.fastDb (i), a));
            if (! started) { p.startNewSubPath (pt); started = true; }
            else p.lineTo (pt);
        }
        return p;
    };
    const auto in = curve (audio.inputSpectrum());
    const auto out = curve (audio.outputSpectrum());
    if (! in.isEmpty())
    {
        juce::Path dashed;
        const float dashes[] = { 4.0f, 3.0f };
        juce::PathStrokeType (1.25f).createDashedStroke (dashed, in, dashes, 2);
        g.setColour (t.inkMuted);
        g.fillPath (dashed);
    }
    if (! out.isEmpty())
    {
        g.setColour (t.ink);
        g.strokePath (out, juce::PathStrokeType (1.75f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
    }

    // frequency labels along the bottom
    for (double hz : { 100.0, 1000.0, 2000.0, 5000.0, 10000.0, 20000.0 })
    {
        const auto x = xForHz (hz, a);
        const auto text = hz >= 1000.0 ? juce::String ((int) (hz / 1000.0)) + "k" : juce::String ((int) hz);
        const juce::Rectangle<float> box (x - 30.0f, a.getBottom() - 16.0f, 26.0f, 14.0f);
        if (box.getX() > a.getX() + 4.0f)
        {
            // knocked out of the band, the centre line and the curves, so it reads at any Frequency
            const auto w = std::ceil (type::width (type::meta(), text));
            g.setColour (t.surfaceSunken);
            g.fillRoundedRectangle (box.withLeft (box.getRight() - w).expanded (4.0f, 1.0f), Tokens::radiusXs);
            type::draw (g, text, box, type::meta(), t.inkSubtle, juce::Justification::centredRight);
        }
    }

    if (listen > 0)
        type::draw (g, listen == 1 ? "Listening: Ess" : "Listening: Delta", a.reduced (10.0f, 8.0f).removeFromTop (14.0f),
                    type::meta(), t.inkSubtle, juce::Justification::centredRight);
}

void SibilanceDisplay::paintStrip (juce::Graphics& g, juce::Rectangle<float> a)
{
    const auto& t = front();
    const auto accent = Tokens::accent();
    const auto thr = yForStripDb (threshold, a);

    // above the threshold: what gets caught
    g.setColour (accent.withAlpha (0.14f));
    g.fillRect (a.withBottom (thr));

    // the histogram: a silhouette growing from the left edge, normalised to its own peak
    const double* bins = relative ? binsRelative.data() : binsAbsolute.data();
    const int n = relative ? (int) binsRelative.size() : (int) binsAbsolute.size();
    double peak = 0.0;
    for (int i = 0; i < n; ++i) peak = std::max (peak, bins[i]);
    if (peak > 1.0e-6)
    {
        juce::Path p;
        p.startNewSubPath (a.getX(), a.getBottom());
        for (int i = 0; i < n; ++i)
        {
            const auto y = yForStripDb (stripLow() + (float) i + 0.5f, a);
            p.lineTo (a.getX() + (float) (bins[i] / peak) * (a.getWidth() - 6.0f), y);
        }
        p.lineTo (a.getX(), a.getY());
        p.closeSubPath();
        g.setColour (t.ink.withAlpha (0.82f));
        g.fillPath (p);
    }

    // the threshold line, across the strip only (a band level is not a per-bin level)
    g.setColour (accent);
    g.fillRect (a.getX(), thr - 1.0f, a.getWidth(), 2.0f);

    // the strip's own axis on its right edge, and the hairline to the spectrum
    g.setColour (t.lineStrong);
    g.fillRect (a.getRight() - 1.0f, a.getY(), 1.0f, a.getHeight());
    const float marks[] = { stripHigh(), (stripHigh() + stripLow()) * 0.5f, stripLow() };
    for (auto db : marks)
    {
        auto y = juce::jlimit (a.getY() + 7.0f, a.getBottom() - 7.0f, yForStripDb (db, a));
        type::draw (g, (db > 0 ? "+" : "") + juce::String (juce::roundToInt (db)),
                    { a.getRight() - 34.0f, y - 7.0f, 28.0f, 14.0f }, type::meta(), t.inkSubtle, juce::Justification::centredRight);
    }
}

void SibilanceDisplay::paintMap (juce::Graphics& g, juce::Rectangle<float> a)
{
    const auto& t = front();
    g.setColour (t.surfaceSunken);
    g.fillRoundedRectangle (a, Tokens::radiusXs);
    g.setColour (t.lineStrong);
    g.fillRect (a.getX() + 6.0f, a.getBottom() - 6.0f, a.getWidth() - 12.0f, 1.0f);

    const auto range = juce::jmax (1.0f, plainOf (apvts, Params::range));
    const auto inner = a.reduced (6.0f, 6.0f);
    for (const auto& e : events)
    {
        const auto x0 = inner.getX() + (float) ((e.start - (clock - kWindowSeconds)) / kWindowSeconds) * inner.getWidth();
        const auto w = juce::jmax (3.0f, e.duration / (float) kWindowSeconds * inner.getWidth() - 1.0f);   // 1 px apart
        const auto h = juce::jlimit (2.0f, inner.getHeight() - 4.0f, e.depth / range * (inner.getHeight() - 4.0f));
        const juce::Rectangle<float> bar (x0, inner.getBottom() - h, w, h);
        if (bar.getRight() < inner.getX())
            continue;
        // a tinted body and a solid cap at the depth: the accent marks the action, the saturated
        // area stays inside the render budget (plugin-visual-craft rule 6, <= 2 %)
        const auto shown = bar.getIntersection (inner);
        g.setColour (Tokens::accent().withAlpha (0.45f));
        g.fillRect (shown);
        g.setColour (Tokens::accent());
        g.fillRect (shown.withHeight (juce::jmin (2.0f, shown.getHeight())));
        if (e.hitRange)
        {
            g.setColour (t.clip);
            g.fillRect (bar.getX() - 1.0f, bar.getY() - 4.0f, bar.getWidth() + 2.0f, 2.0f);
        }
    }
}

void SibilanceDisplay::paintLegend (juce::Graphics& g, juce::Rectangle<float> a)
{
    const auto& t = front();
    auto r = a;
    auto key = [&] (juce::Colour c, bool dashed, const juce::String& text)
    {
        auto box = r.removeFromLeft (20.0f + std::ceil (type::width (type::meta(), text)));
        const auto y = box.getCentreY();
        g.setColour (c);
        if (dashed)
            for (float x = box.getX(); x < box.getX() + 14.0f; x += 5.0f)
                g.fillRect (x, y - 0.75f, 3.0f, 1.5f);
        else
            g.fillRect (box.getX(), y - 1.0f, 14.0f, 2.0f);
        type::draw (g, text, box.withTrimmedLeft (20.0f), type::meta(), t.inkMuted);
        r.removeFromLeft (14.0f);
    };
    const auto [lo, hi] = bandEdges();
    key (t.ink, false, "Output");
    key (t.inkMuted, true, "Input");
    key (Tokens::accent().withAlpha (0.6f), false, "Band " + hzText (lo).upToFirstOccurrenceOf (" kHz", false, false)
                                                         + " to " + hzText (hi));

    // the count of the last 8 s
    int count = 0, over = 0;
    float deepest = 0.0f;
    for (const auto& e : events)
        if (e.start + e.duration >= clock - kWindowSeconds)
        {
            ++count;
            over += e.hitRange ? 1 : 0;
            deepest = std::max (deepest, e.depth);
        }
    juce::String summary = count == 0 ? juce::String ("No esses caught")
                         : juce::String (count) + (count == 1 ? " ess" : " esses") + "  \xc2\xb7  deepest -" + juce::String (deepest, 1) + " dB";
    if (over > 0)
        summary << "  \xc2\xb7  " << over << " over range";
    type::draw (g, juce::String::fromUTF8 (summary.toRawUTF8()), r, type::meta(), over > 0 ? t.ink : t.inkMuted,
                juce::Justification::centredRight);
}

//==============================================================================
// the threshold line drags

bool SibilanceDisplay::onThresholdLine (juce::Point<float> p) const
{
    const auto a = stripArea();
    return showHistogram && a.contains (p) && std::abs (p.y - yForStripDb (threshold, a)) <= 6.0f;
}

void SibilanceDisplay::mouseMove (const juce::MouseEvent& e)
{
    setMouseCursor (onThresholdLine (e.position) ? juce::MouseCursor::UpDownResizeCursor : juce::MouseCursor::NormalCursor);
}

void SibilanceDisplay::mouseDown (const juce::MouseEvent& e)
{
    if (! showHistogram || ! stripArea().contains (e.position))
        return;
    draggingThreshold = true;
    thresholdAttachment.beginGesture();
    thresholdAttachment.setValueAsPartOfGesture (juce::jlimit (-60.0f, 0.0f, stripDbForY (e.position.y)));
}

void SibilanceDisplay::mouseDrag (const juce::MouseEvent& e)
{
    if (draggingThreshold)
        thresholdAttachment.setValueAsPartOfGesture (juce::jlimit (-60.0f, 0.0f, stripDbForY (e.position.y)));
}

void SibilanceDisplay::mouseUp (const juce::MouseEvent&)
{
    if (draggingThreshold)
        thresholdAttachment.endGesture();
    draggingThreshold = false;
}
