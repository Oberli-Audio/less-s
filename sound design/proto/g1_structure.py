#!/usr/bin/env python3
"""G1 evidence: which structure applies the band gain in Split mode?

sound-design-bob G1 asks for the departures from the selection table to name the
measurement that would reject them. This script is that measurement for the one
structural departure from docs/sketch.md: the sketch's Linkwitz-Riley three-way split
against the parallel bell form of dsp-reference-bob E.2.

    python3 "sound design/proto/g1_structure.py"

Two questions, both answered on an impulse at 48 kHz:

1. Does the structure null against its input at band gain 1 (brief must_do
   "Null at Range 0 dB in every mode", sketch acceptance test 1)?
2. Does a band gain of -8 dB deliver -8 dB at the centre, and what does it cost
   outside the band (brief quality_targets.response_error_db, mix_context
   "must leave 1-4 kHz untouched")?

Pure numpy/scipy; no harness, no build. Numbers quoted in docs/status.md.
"""
import numpy as np
from scipy import signal as sg

FS = 48000.0
F0 = 7000.0          # the table's default Frequency
WIDTH_OCT = 1.2      # the table's default Width
DEPTH_DB = 8.0       # the table's default Range
PROBES = (1000, 2000, 3000, 4000, 5000, 7000, 10000, 14000, 18000)


def butter2(fc, kind):
    return sg.butter(2, fc / (FS / 2), kind)


def cascade2(ba, x):
    b, a = ba
    return sg.lfilter(b, a, sg.lfilter(b, a, x))


def allpass2(fc, x, q=1.0 / np.sqrt(2.0)):
    """The LR4 correction filter: one 2nd-order allpass at the crossover, Q = 0.7071."""
    w0 = 2 * np.pi * fc / FS
    al = np.sin(w0) / (2 * q)
    b = np.array([1 - al, -2 * np.cos(w0), 1 + al]) / (1 + al)
    a = np.array([1.0, -2 * np.cos(w0) / (1 + al), (1 - al) / (1 + al)])
    return sg.lfilter(b, a, x)


def bandpass_biquad(f0, bw_oct):
    """RBJ constant-skirt band-pass, peak gain 1 at f0; 1 + (G-1)*BP is an exact bell."""
    w0 = 2 * np.pi * f0 / FS
    al = np.sin(w0) * np.sinh(np.log(2) / 2 * bw_oct * w0 / np.sin(w0))
    b = np.array([al, 0.0, -al])
    a = np.array([1 + al, -2 * np.cos(w0), 1 - al])
    return b / a[0], a / a[0]


def band_edges(f0, bw_oct):
    return f0 * 2 ** (-bw_oct / 2), f0 * 2 ** (bw_oct / 2)


def lr4_split(x, flo, fhi, gain):
    """Low | band | high through two LR4 splitters, allpass-corrected, band scaled."""
    low = cascade2(butter2(flo, "low"), x)
    upper = cascade2(butter2(flo, "high"), x)
    band = cascade2(butter2(fhi, "low"), upper)
    high = cascade2(butter2(fhi, "high"), upper)
    return allpass2(fhi, low) + gain * band + high


def parallel_bell(x, f0, bw_oct, gain):
    b, a = bandpass_biquad(f0, bw_oct)
    return x + (gain - 1.0) * sg.lfilter(b, a, x)


def residual_db(y, x):
    r = y - x
    peak = 20 * np.log10(np.max(np.abs(r)) + 1e-300)
    rms = 20 * np.log10(np.sqrt(np.mean(r ** 2)) + 1e-300)
    return peak, rms


def magnitude_at(y, probes=PROBES):
    f, h = sg.freqz(y, worN=1 << 15, fs=FS)
    mag = 20 * np.log10(np.abs(h) + 1e-300)
    return [(p, mag[np.argmin(np.abs(f - p))]) for p in probes]


def main():
    n = 1 << 15
    x = np.zeros(n)
    x[0] = 1.0
    flo, fhi = band_edges(F0, WIDTH_OCT)
    g = 10 ** (-DEPTH_DB / 20)

    print("Less S G1 - Split mode structure, %g Hz / %g oct / %g dB at %g Hz\n"
          % (F0, WIDTH_OCT, DEPTH_DB, FS))
    print("1. Null at Range 0 (band gain 1): residual against the input")
    for name, y in (("LR4 three-way split", lr4_split(x, flo, fhi, 1.0)),
                    ("parallel bell", parallel_bell(x, F0, WIDTH_OCT, 1.0))):
        peak, rms = residual_db(y, x)
        verdict = "PASS" if peak < -120.0 else "FAIL"
        print("   %-22s peak %8.1f dBFS   rms %8.1f dBFS   %s" % (name, peak, rms, verdict))

    print("\n2. Band gain -%g dB: magnitude at the probes" % DEPTH_DB)
    rows = {"LR4 three-way split": magnitude_at(lr4_split(x, flo, fhi, g)),
            "parallel bell": magnitude_at(parallel_bell(x, F0, WIDTH_OCT, g))}
    print("   %-22s %s" % ("", " ".join("%7d" % p for p, _ in rows["parallel bell"])))
    for name, row in rows.items():
        print("   %-22s %s" % (name, " ".join("%+7.2f" % v for _, v in row)))
    centre = dict(rows["parallel bell"])[int(F0)]
    print("\n   parallel bell at the centre: %+.2f dB (target -%g +/-1 dB) -> %s"
          % (centre, DEPTH_DB, "PASS" if abs(centre + DEPTH_DB) <= 1.0 else "FAIL"))


if __name__ == "__main__":
    main()
