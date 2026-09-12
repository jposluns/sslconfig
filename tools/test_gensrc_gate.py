#!/usr/bin/env python3
"""Cases for check_gensrc.py, one per input a reviewer demonstrated against it.

The early versions of that gate were naive in both directions, and the two directions were
not equally bad. Missing a real source is a silent false pass. Inventing one produces a
fabricated drift finding against a correct repository, which is worse than having no gate
at all, because a maintainer who is told their manifest is wrong when it is right learns to
distrust the suite.

The gate no longer hand-parses bash. It hands the `files=(...)` block to `bash -c` and reads
back what bash itself produced. It refuses outright when the block carries a command
substitution, a redirection or a control operator. The cases below are what made that
necessary: two hand-written splitters lost to them a round at a time, each fix growing the
parser and each round turning up another word bash already knew how to read. Reading the
array with bash extends no trust that was not extended already, because
`tools/run_all_checks.sh` runs this same build script two checks earlier to prove the
bundle is current.

Every case below is a fixture a reviewer actually ran. Each builds a throwaway repository
in a temporary directory and runs the real gate against it, so what is under test is the
shipped entry point rather than a reimplementation of its logic.

A case earns its place by failing when its bug is restored. That is the standard the
convention gates settled on after three cases were found asserting the right answer for the
wrong reason, and it applies here from the start rather than after the same lesson.

Some cases assert on the gate's MESSAGE as well as its exit status, because an exit code
alone cannot tell a diagnosis from a crash. That was found by removing a guard to check a
case discriminates: the case passed its exit-code assertion while the gate was in fact
raising an AttributeError with an empty stdout, which is a crash wearing the exit code of a
finding. This file briefly lost the only message-level assertion it had when a separate
check was folded into the case table, and the loss is recorded here because a test file
that cannot tell why it went red is the same defect it exists to catch.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent / "check_gensrc.py"
BASE = ["scripts/build-llms-full.sh", "README.md"]


def run_against(script_body, sources, extra_files=()):
    """Build a throwaway repository and run the real gate in it. Returns (exit, output).

    `extra_files` names files to create alongside the three every fixture gets, for the
    cases whose filenames carry a space, a hash or a literal asterisk.
    """
    d = Path(tempfile.mkdtemp())
    try:
        for sub in ("tools", "scripts", ".aiqt", "site"):
            (d / sub).mkdir()
        shutil.copy(GATE, d / "tools" / GATE.name)
        (d / "scripts" / "build-llms-full.sh").write_text(script_body, encoding="utf-8")
        (d / "site" / "llms-full.txt").write_text("x", encoding="utf-8")
        for f in ("README.md", "README.sources.md", "nginx.md", *extra_files):
            (d / f).write_text("x", encoding="utf-8")
        (d / ".aiqt" / "gensrc.json").write_text(json.dumps({"generated": [{
            "kind": "file", "target": "site/llms-full.txt",
            "regenerate": "bash scripts/build-llms-full.sh", "sources": sources}]}),
            encoding="utf-8")
        r = subprocess.run([sys.executable, f"tools/{GATE.name}"], cwd=d,
                           capture_output=True, text=True)
        return r.returncode, r.stdout.strip()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# (description, script body, declared sources, must_fail, extra files to create,
#  expected substring)
# The sixth field is a fragment the gate's own message must contain. It is None where the
# exit status is the whole claim, and a string where the exit status alone would not tell a
# diagnosis from a crash.
CASES = (
    # MISSES. Each of these passed some earlier version of the gate.
    ("an indented files+= after the array",
     "files=(\n  README.md\n)\n  files+=(nginx.md)\n", BASE, True, (), None),
    ("an index assignment after the array",
     "files=(\n  README.md\n)\nfiles[1]=nginx.md\n", BASE, True, (), None),
    ("a command after the array's closing parenthesis",
     "files=(\n  README.md\n); files+=(nginx.md)\n", BASE, True, (), None),
    ("a declare -a respelling of the same assignment",
     "files=(\n  README.md\n)\ndeclare -a files+=(nginx.md)\n", BASE, True, (), None),
    ("a hash inside a filename, which does not start a comment",
     "files=(\n  README.md#notes\n)\n", BASE, True, ("README.md#notes",), None),
    ("an empty array element, which is not a filename",
     'files=(\n  README.md ""\n)\n', BASE, True, (), None),
    ("mismatched quotes, which bash itself rejects",
     'files=(\n  "README.md\'\n)\n', BASE, True, (), None),
    ("a comment after a filename",
     "files=(\n  README.md # nginx.md\n)\n", BASE + ["nginx.md"], True, (), None),
    ("a source built in and not recorded",
     "files=(\n  README.md\n  nginx.md\n)\n", BASE, True, (), None),
    ("sources given as a JSON object, whose keys a set conversion took",
     "files=(\n  README.md\n)\n",
     {"scripts/build-llms-full.sh": 0, "README.md": 0}, True, (),
     "sources must be a list of non-empty strings"),
    ("the same source recorded twice",
     "files=(\n  README.md\n)\n", BASE + ["README.md"], True, (), None),
    ("a command substitution, which this gate reads but will not run",
     "files=(\n  $(ls *.md)\n)\n", BASE, True, (), "reads but will not run"),

    # FALSE ALARMS. Every one of these is ordinary Bash an earlier version invented drift
    # from.
    ("a quoted filename containing a space",
     'files=(\n  "guide name.md"\n)\n',
     ["scripts/build-llms-full.sh", "guide name.md"], False, ("guide name.md",), None),
    ("a filename split across two quoted halves",
     'files=(\n  "README".md\n)\n', BASE, False, (), None),
    ("a quoted hash inside a filename",
     'files=(\n  "guide#name.md"\n)\n',
     ["scripts/build-llms-full.sh", "guide#name.md"], False, ("guide#name.md",), None),
    ("a quoted glob, which is a literal filename",
     "files=(\n  'guide*.md'\n)\n",
     ["scripts/build-llms-full.sh", "guide*.md"], False, ("guide*.md",), None),
    ("a comment on its own line",
     "files=(\n  # core guides\n  README.md\n)\n", BASE, False, (), None),
    ("a line continuation",
     "files=(\n  README.md \\\n)\n", BASE, False, (), None),
    ("an unquoted glob, compared against what it really expands to",
     "files=(\n  README*.md\n)\n", BASE + ["README.sources.md"], False, (), None),
    ("a correct repository",
     "files=(\n  README.md\n)\n", BASE, False, (), None),
)


def main() -> int:
    failures = []
    for desc, body, sources, must_fail, extra, expected in CASES:
        rc, out = run_against(body, sources, extra)
        if bool(rc) != must_fail:
            want = "fail" if must_fail else "pass"
            failures.append(f"{desc}: expected the gate to {want}, it did not ({out})")
        if expected is not None and expected not in out:
            failures.append(
                f"{desc}: the gate's exit status was right but its message was not. "
                f"Expected it to contain {expected!r}, which a crash or an unrelated "
                f"finding would not produce. It said: {out!r}")

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {len(CASES)} recorded cases for the generated-file record gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
