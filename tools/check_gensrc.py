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
`files=(...)` array assignment, not by running the script. Running it would be the accurate
way and it is not worth executing a build to check a manifest.

So this understands one array in one shape, and anything else must fail the MATCH rather
than be checked incorrectly. That direction matters more than it sounds. Missing a real
source is a silent false pass; inventing one is a fabricated drift finding against a
correct repository, which is worse than no gate, because a maintainer told their manifest
is wrong when it is right learns to distrust the whole suite. The first version of this
file did exactly that: a comment line, a line continuation and a quoted filename each
produced invented sources, while a `files+=` later in the script, a trailing comment, and
a glob each produced silent passes. All six were demonstrated by a reviewer and are
recorded in `tools/test_gensrc_gate.py`.

It now refuses, with a reason, when the script assigns to `files` more than once, when a
token carries shell syntax it would have to expand, or when the array is empty. It reads a
comment to end of line rather than as one word, and unwraps a quoted filename. The
manifest side is checked too: `sources` must be a list of non-empty strings, because a
JSON object passed once when converting it to a set silently took its keys.

WHAT THIS DOES NOT PROVE: that the regenerate command produces the target, that the target
is current, or that the sources are the right sources. The bundle-freshness gate covers
currency. This one covers the record of how it is made.
"""
import json
import re
import sys
from pathlib import Path

MANIFEST = Path(".aiqt") / "gensrc.json"
# One array assignment, opened on its own line and closed on its own line.
FILES_ARRAY = re.compile(r"^files=\(\n(.*?)^\)", re.S | re.M)
# Any OTHER assignment to the same name. A `files+=(...)` later in the script, or a second
# `files=(...)`, changes the real list while leaving the first match looking authoritative.
FILES_AGAIN = re.compile(r"^files\+?=", re.M)
# Characters the shell would act on. A token carrying one is not a filename, and certifying
# it literally would bless a manifest that lists a wildcard as though it were a source.
SHELL_ACTIVE = re.compile(r"[*?\[\]${}~!&|;<>()`\\]")


class Unreadable(Exception):
    """The script's list is not in the one shape this gate reads."""


def script_inputs(script: Path):
    """The files a build script lists.

    Raises Unreadable with a reason rather than guessing. Every branch here exists because
    a reviewer demonstrated the previous version getting it wrong, and the two directions
    were not equally bad: missing a real source is a silent false pass, while inventing one
    produces a fabricated drift finding against a correct repository, which is worse than
    no gate because it teaches a maintainer to distrust the suite.
    """
    text = script.read_text(encoding="utf-8")
    m = FILES_ARRAY.search(text)
    if not m:
        raise Unreadable("no files=(...) array opened and closed on their own lines")
    if len(FILES_AGAIN.findall(text)) > 1:
        raise Unreadable("more than one assignment to `files`, so the first is not the whole list")

    out = []
    for line in m.group(1).splitlines():
        line = line.split("#", 1)[0]          # a comment runs to end of line, not one word
        for token in line.split():
            if token.startswith(("'", '"')) and token.endswith(("'", '"')) and len(token) > 1:
                token = token[1:-1]           # a quoted filename is that filename
            if not token:
                continue
            if SHELL_ACTIVE.search(token):
                raise Unreadable(f"{token!r} is shell syntax rather than a plain filename")
            out.append(token)
    if not out:
        raise Unreadable("the files=(...) array is empty")
    return out


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

        try:
            listed = script_inputs(script)
        except Unreadable as why:
            findings.append(
                f"{MANIFEST}: {target}: cannot read the source list out of {named[0]}: {why}. "
                f"This gate reads one array in one shape; if the script changed how it "
                f"builds its list, teach this gate the new shape rather than deleting it")
            continue

        sources = entry.get("sources")
        if not isinstance(sources, list) or not all(
                isinstance(x, str) and x.strip() for x in sources):
            findings.append(
                f"{MANIFEST}: {target}: sources must be a list of non-empty strings. "
                f"A JSON object passed this check once, because converting it to a set "
                f"silently took its keys")
            continue
        duplicates = sorted({x for x in sources if sources.count(x) > 1})
        for d in duplicates:
            findings.append(f"{MANIFEST}: {target}: {d} is recorded more than once")

        expected = set(listed) | {named[0]}
        declared = set(sources)
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
