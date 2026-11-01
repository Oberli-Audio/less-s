#!/usr/bin/env python3
"""G2 reference renders: the files Björn listens to, and the dry file to A/B against.

    python3 "sound design/proto/render_references.py"            # 48 kHz, the phrase
    python3 "sound design/proto/render_references.py" --rate 96000

Writes into `sound design/renders/`, which `.gitignore` keeps out of git (the family
puts audio in OneDrive). The reproducible artefact is this script: the prototype is
deterministic and seeded, so the same command gives byte-identical files anywhere.

What to listen for, in order:
  00-dry             the phrase untouched - the reference level for every A/B
  10-split           the default: only the band moves. The esses should lose their
                     edge and the vowels should be untouched. If the voice gets dull,
                     Width is too wide or Range too deep.
  11-wide            the same reduction applied to everything: it should sound like
                     the whole voice ducks on every ess. This is what Split is not.
  12-spectral        only the hissing bins: the most transparent, 5.3 ms of latency.
  20-delta-split     what Split removed. It should contain esses and nothing else -
                     no vowels, no breath, no /f/.
  30-over-range      Range at 24 dB with a low Threshold: the lisp. This is the
                     failure the ess map's red ticks are there to warn about.
  40-relative-quiet  the same phrase 20 dB quieter with Relative on; the reduction
  41-relative-loud   should be the same in both, which is the whole point of Relative.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from less_s import LISTEN_DELTA, MODE_SPECTRAL, MODE_SPLIT, MODE_WIDE, render  # noqa: E402
import material as M  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "renders")


def write(path, x, fs):
    from scipy.io import wavfile
    x = np.asarray(x, dtype=np.float64)
    peak = float(np.max(np.abs(x)))
    if peak > 1.0:
        print("  ! %s peaks at %+.2f dBFS: written as float32, not clipped"
              % (os.path.basename(path), 20 * np.log10(peak)))
    wavfile.write(path, int(fs), x.astype(np.float32))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rate", type=float, default=48000.0)
    ap.add_argument("--voice", default="female", choices=("female", "male"))
    args = ap.parse_args(argv)
    fs = args.rate
    os.makedirs(OUT, exist_ok=True)
    x, labels = M.phrase(fs, voice=args.voice)
    tag = "" if args.voice == "female" else "-male"

    jobs = [
        ("00-dry", dict(range_db=0.0)),
        ("10-split", dict(mode=MODE_SPLIT, range_db=8.0, threshold=-30.0)),
        ("11-wide", dict(mode=MODE_WIDE, range_db=8.0, threshold=-30.0)),
        ("12-spectral", dict(mode=MODE_SPECTRAL, range_db=8.0, threshold=-30.0)),
        ("20-delta-split", dict(mode=MODE_SPLIT, range_db=8.0, threshold=-30.0, listen=LISTEN_DELTA)),
        ("30-over-range", dict(mode=MODE_SPLIT, range_db=24.0, threshold=-48.0)),
    ]
    print("Less S reference renders at %g Hz, %s voice -> %s" % (fs, args.voice, OUT))
    print("  the phrase has %d labelled esses, %d breaths, %d /f/ bursts"
          % (len(labels["ess"]), len(labels["breath"]), len(labels["f"])))
    for name, params in jobs:
        y, info = render(x, fs, auto_learn=False, **params)
        write(os.path.join(OUT, "%s%s.wav" % (name, tag)), y, fs)
        print("  %-16s latency %4d  events %2d  deepest %5.1f dB"
              % (name, info.latency, len(info.events),
                 float(np.max(info.gain_db)) if info.gain_db.size else 0.0))

    for name, level in (("40-relative-quiet", -30.0), ("41-relative-loud", -10.0)):
        g = 10 ** ((level - (-14.0)) / 20)
        y, info = render(x * g, fs, auto_learn=False, relative=True, threshold=-6.0,
                         range_db=12.0, mode=MODE_SPLIT)
        write(os.path.join(OUT, "%s%s.wav" % (name, tag)), y, fs)
        print("  %-16s esses near %.0f dBFS, deepest reduction %5.1f dB"
              % (name, level, float(np.max(info.gain_db)) if info.gain_db.size else 0.0))
    print("\nListen Split against dry first, level-matched; then Wide against Split.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
