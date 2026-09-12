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

HOW IT READS THE SCRIPT: it asks. A build script states its own inputs under
`--list-inputs`, and this gate takes what the script prints rather than working it out.
Two earlier versions tried to determine the list from the script's text, first with a
hand-written parser and then by evaluating the extracted array in bash, and both lost to
ordinary shell a build script is entitled to use: a variable referenced inside the array,
a second assignment spelled `typeset -a files+=`. A reviewer's judgement across three
rounds was that the invariant is worth checking and that this implementation was not worth
its maintenance cost. Requiring a build script to be able to say what it builds from is a
smaller thing to ask than reimplementing bash.

WHAT `--list-inputs` PROVES, AND WHAT IT DOES NOT. It proves what the script SAYS it builds
from, and nothing else. A script can report one list and build from another, and a reviewer
demonstrated two separate ways: an append placed after the listing exits, and an append
placed above it but guarded on the argument count, so that a `--list-inputs` run never
reaches it. Placement narrows the first and does nothing at all about the second, so read it
as a convention that reduces accidents rather than as a mitigation. The only real assurance
is that the listing and the build read the same array, which a reader can check and this gate
cannot. That is the honest cost of asking the script instead of reading it, and the
alternative was reimplementing bash, which lost three rounds running.

HOW IT RUNS THE COMMAND: directly, never through a shell. So the regenerate command has to be
a plain script invocation, optionally preceded by one interpreter, and the gate says so when
it is not. A reviewer demonstrated why that has to be stated rather than assumed: `LC_ALL=C
bash build.sh` tried to execute a program named `LC_ALL=C`, while a trailing `# comment` or
`> /dev/null` arrived as literal arguments, displacing `--list-inputs` from `$1` so the
script performed a full BUILD while the gate was only supposed to be reading it. A check that
rewrites the tree it is checking is worse than the drift it was looking for.

The manifest side is checked too: `sources` must be a list of non-empty strings, because a
JSON object passed once when converting it to a set silently took its keys.

WHAT THIS DOES NOT PROVE: that the regenerate command produces the target, that the target
is current, or that the sources are the right sources. The bundle-freshness gate covers
currency. This one covers the record of how it is made.
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

MANIFEST = Path(".aiqt") / "gensrc.json"


class Unreadable(Exception):
    """The script's list is not in the one shape this gate reads."""


SHELL_ONLY = {"|", "||", "&&", "&", ";", ";;", ">", ">>", "<", "<<", "<<<", "2>", "2>&1"}
SHELL_CHARS = "|&;<>()`$"


def not_a_plain_invocation(words):
    """Why this gate cannot run the command directly, or None when it can.

    The gate executes the regenerate command itself rather than handing it to a shell,
    so anything whose meaning depends on a shell is not something it can run. A reviewer
    demonstrated all three shapes that mattered, and the third is the dangerous one: a
    `VAR=value` prefix became a program name, and a trailing comment or redirection became
    literal arguments, which pushed `--list-inputs` out of `$1` and made the script perform
    a full build while the gate was only reading it.
    """
    if not words:
        return "regenerate command is empty"
    for w in words:
        if w in SHELL_ONLY or w.startswith("#") or any(c in w for c in SHELL_CHARS):
            return (f"regenerate command uses shell syntax ({w!r}), and this gate runs the "
                    f"command directly rather than through a shell")
    scripts = [i for i, w in enumerate(words) if w.endswith(".sh") or w.endswith(".py")]
    if not scripts:
        return "regenerate command names no script"
    i = scripts[0]
    if i > 1 or (i == 1 and "=" in words[0]):
        return ("regenerate command must be a plain script invocation, optionally preceded "
                "by one interpreter. An environment assignment or any other prefix needs a "
                "shell, and this gate runs the command directly")
    if len(words) > i + 1:
        return ("regenerate command has arguments after the script name, and this gate "
                "appends --list-inputs, which those arguments would displace")
    return None


def script_inputs(command, root: Path):
    """The files a build script says it builds from, asked rather than worked out.

    Two earlier versions tried to determine this from the script's text, first with a
    hand-written parser and then by evaluating the extracted array in bash. Both lost to
    ordinary shell that a build script is entitled to use: a variable referenced inside the
    array, `typeset -a files+=` as a second assignment, a command sitting between the array
    and a later one. Every fix grew the code and the next round found another word bash
    already knew how to read.

    So the script states its own inputs under `--list-inputs`, and this asks for them. The
    script is the only thing that can answer without guessing, and a build script that
    cannot say what it builds from is a reasonable thing to require.
    """
    try:
        done = subprocess.run([*command, "--list-inputs"], cwd=root, capture_output=True,
                              timeout=60, env={"PATH": os.environ.get("PATH", "")})
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unreadable(f"could not run it with --list-inputs: {exc}")
    if done.returncode:
        raise Unreadable(
            f"--list-inputs exited {done.returncode}. A build script this manifest names has "
            f"to support it, printing one input per line and doing nothing else: "
            f"{done.stderr.decode('utf-8', 'replace').strip()[:160]}")
    out = [w for w in done.stdout.decode("utf-8").splitlines() if w.strip()]
    if not out:
        raise Unreadable("--list-inputs printed nothing")
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
        target = entry.get("target")
        if not isinstance(target, str) or not target.strip():
            # `root / ""` is the repository directory and `.exists()` said yes, so an entry
            # with no target name passed and the summary counted it as a generated file.
            findings.append(f"{MANIFEST}: an entry has no target file name")
            continue
        if not (root / target).is_file():
            findings.append(f"{MANIFEST}: target {target} is not a file in this repository")

        command = entry.get("regenerate", "")
        try:
            words = shlex.split(command)
        except ValueError as exc:
            findings.append(
                f"{MANIFEST}: {target}: regenerate command does not parse as a shell "
                f"command line ({exc}): {command!r}")
            continue
        why = not_a_plain_invocation(words)
        if why:
            findings.append(f"{MANIFEST}: {target}: {why}: {command!r}")
            continue
        named = [w for w in words if w.endswith(".sh") or w.endswith(".py")]
        script = root / named[0]
        if not script.exists():
            findings.append(f"{MANIFEST}: {target}: regenerate names {named[0]}, which does not exist")
            continue

        try:
            listed = script_inputs(words, root)
        except Unreadable as why:
            findings.append(
                f"{MANIFEST}: {target}: cannot get the source list out of {named[0]}: {why}. "
                f"This gate asks the script rather than reading it, so a script named here "
                f"has to answer `--list-inputs` with one input per line")
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
    print(f"  ok    {MANIFEST} agrees with what {n} generated "
          f"file{'' if n == 1 else 's'} report as their inputs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
