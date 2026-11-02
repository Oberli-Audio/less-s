#!/usr/bin/env python3
"""The release preset's bundles, as one CTest (macOS, PRODUCT_RELEASE_SYMBOLS).

    python3 tools/tests/check_bundle.py build/LessS_artefacts/Release/VST3/Less\\ S.vst3 [...]

For every bundle given:
  1. `codesign --verify --strict` passes. The symbols step strips the binary after JUCE has
     signed it; without the ad-hoc signature after `strip`, arm64 macOS kills every process
     that loads the bundle (pluginval and the Steinberg validator exited with signal 9).
  2. Its dSYM carries DWARF for every slice of the binary, with the binary's UUID. With LTO the
     debug map points at ld's temporary object; without -object_path_lto per slice the dSYM
     held no compile unit at all, so a friend's crash report could not be symbolicated.
docs/failures.md has both rows.
"""
import re
import subprocess
import sys
from pathlib import Path


def run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def uuids(path):
    _, out = run("dwarfdump", "--uuid", str(path))
    return dict((a, u) for u, a in re.findall(r"UUID: (\S+) \((\w+)\)", out))


def check(bundle):
    bundle = Path(bundle)
    fails = []
    if not bundle.exists():
        return ["%s: not built" % bundle]
    code, out = run("codesign", "--verify", "--strict", str(bundle))
    if code != 0:
        fails.append("%s: signature invalid (%s)" % (bundle.name, out.strip().splitlines()[-1] if out.strip() else code))
    binary = bundle / "Contents" / "MacOS" / bundle.stem
    dsym = Path(str(bundle) + ".dSYM")
    if not dsym.exists():
        return fails + ["%s: no dSYM beside the bundle" % bundle.name]
    want, have = uuids(binary), uuids(dsym)
    if not want:
        fails.append("%s: no slice found in %s" % (bundle.name, binary))
    for arch, uuid in want.items():
        if have.get(arch) != uuid:
            fails.append("%s %s: dSYM UUID %s, binary %s" % (bundle.name, arch, have.get(arch), uuid))
            continue
        _, info = run("dwarfdump", "--arch", arch, "--debug-info", str(dsym))
        units = info.count("DW_TAG_compile_unit")
        if units == 0:
            fails.append("%s %s: the dSYM holds no DWARF (LTO object lost?)" % (bundle.name, arch))
        else:
            print("%-28s %-7s signed, dSYM %s, %d compile units" % (bundle.name, arch, uuid, units))
    return fails


def main(argv):
    if not argv:
        sys.exit(__doc__)
    fails = [f for b in argv for f in check(b)]
    for f in fails:
        print("FAILED: " + f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
