#!/usr/bin/env python3
"""Check that .aiqt/gensrc.json still describes how the generated files are built.

WHAT THIS CATCHES: a generated file whose recorded inputs have drifted from its real
ones. `CLAUDE.md` names `.aiqt/gensrc.json` as the record of which sources produce
`site/llms-full.txt`, and adding a guide means touching five wiring surfaces. Four of them
were already gated: the bundle's own freshness, the site menu, the README index, and
`site/llms.txt`. This one was not, so a guide added to the build script and forgotten here
left the record wrong and nothing said so. That happened, and a reviewer found it rather
than a gate.

WHAT IT CHECKS, per entry under "generated":

  - the target exists;
  - the regenerate command names a script that exists;
  - the declared sources are EXACTLY that script plus the files the script itself lists,
    with no extras and nothing missing.

The third is the one with teeth. The other two only catch a rename.

HOW IT READS THE SCRIPT, and the limit that comes with it: by matching a single
`files=(...)` array assignment, not by running the script. Running it would be the
accurate way and it is not worth executing a build to check a manifest. So this understands
one array in one shape, and a script that built its list some other way would fail the
match rather than be checked incorrectly, which is the direction to fail in. The failure
message says so, rather than leaving a maintainer to guess why a valid script will not
parse.

WHAT THIS DOES NOT PROVE: that the regenerate command produces the target, that the target
is current, or that the sources are the right sources. The bundle-freshness gate covers
currency. This one covers the record of how it is made.
"""
import json
import re
import sys
from pathlib import Path

MANIFEST = Path(".aiqt") / "gensrc.json"
# One array assignment, opened on its own line and closed on its own line. Anything else is
# reported as unreadable rather than silently half-matched.
FILES_ARRAY = re.compile(r"^files=\(\n(.*?)^\)", re.S | re.M)


def script_inputs(script: Path):
    """The files a build script lists, or None if its list is not in the shape we read."""
    m = FILES_ARRAY.search(script.read_text(encoding="utf-8"))
    if not m:
        return None
    return [w for w in m.group(1).split() if w and not w.startswith("#")]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest = root / MANIFEST
    findings = []

    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"  FAIL  {MANIFEST} is missing; CLAUDE.md names it as the generated-file record")
        return 1
    except Exception as exc:
        print(f"  FAIL  {MANIFEST} is not valid JSON: {exc}")
        return 1

    entries = data.get("generated")
    if not isinstance(entries, list) or not entries:
        print(f"  FAIL  {MANIFEST} has no 'generated' list")
        return 1

    for entry in entries:
        target = entry.get("target", "<no target>")
        if not (root / target).exists():
            findings.append(f"{MANIFEST}: target {target} does not exist")

        command = entry.get("regenerate", "")
        named = [w for w in command.split() if w.endswith(".sh") or w.endswith(".py")]
        if not named:
            findings.append(f"{MANIFEST}: {target}: regenerate command names no script: {command!r}")
            continue
        script = root / named[0]
        if not script.exists():
            findings.append(f"{MANIFEST}: {target}: regenerate names {named[0]}, which does not exist")
            continue

        listed = script_inputs(script)
        if listed is None:
            findings.append(
                f"{MANIFEST}: {target}: cannot read a files=(...) array out of {named[0]}. "
                f"This gate reads one array in one shape; if the script changed how it "
                f"builds its list, teach this gate the new shape rather than deleting it")
            continue

        expected = set(listed) | {named[0]}
        declared = set(entry.get("sources", []))
        for missing in sorted(expected - declared):
            findings.append(f"{MANIFEST}: {target}: {missing} is built in but not recorded here")
        for extra in sorted(declared - expected):
            findings.append(f"{MANIFEST}: {target}: {extra} is recorded here but not built in")

    if findings:
        for f in findings:
            print(f"  FAIL  {f}")
        return 1
    n = len(entries)
    print(f"  ok    {MANIFEST} records the real inputs of {n} generated "
          f"file{'' if n == 1 else 's'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
