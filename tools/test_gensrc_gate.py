#!/usr/bin/env python3
"""Cases for check_gensrc.py, one per input a reviewer demonstrated against it.

The first version of that gate was naive in both directions, and the two directions were
not equally bad. Missing a real source is a silent false pass. Inventing one produces a
fabricated drift finding against a correct repository, which is worse than having no gate
at all, because a maintainer who is told their manifest is wrong when it is right learns to
distrust the suite.

Every case below is a fixture a reviewer actually ran. Each builds a throwaway repository
in a temporary directory and runs the real gate against it, so what is under test is the
shipped entry point rather than a reimplementation of its logic.

A case earns its place by failing when its bug is restored. That is the standard the
convention gates settled on after three cases were found asserting the right answer for the
wrong reason, and it applies here from the start rather than after the same lesson.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent / "check_gensrc.py"
BASE = ["scripts/build-llms-full.sh", "README.md"]


def run_against(script_body, sources):
    """Build a throwaway repository and run the real gate in it. Returns (exit, output)."""
    d = Path(tempfile.mkdtemp())
    try:
        for sub in ("tools", "scripts", ".aiqt", "site"):
            (d / sub).mkdir()
        shutil.copy(GATE, d / "tools" / GATE.name)
        (d / "scripts" / "build-llms-full.sh").write_text(script_body, encoding="utf-8")
        (d / "site" / "llms-full.txt").write_text("x", encoding="utf-8")
        for f in ("README.md", "README.sources.md", "nginx.md"):
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


# (description, script body, declared sources, must_fail)
CASES = (
    # MISSES. Each of these passed the first version of the gate.
    ("a later files+= changes the list the first match no longer describes",
     "files=(\n  README.md\n)\nfiles+=(nginx.md)\n", BASE, True),
    ("a comment after a filename, where the comment runs to end of line",
     "files=(\n  README.md # nginx.md\n)\n", BASE + ["nginx.md"], True),
    ("a glob, which the gate must not certify as a literal filename",
     "files=(\n  README*.md\n)\n", ["scripts/build-llms-full.sh", "README*.md"], True),
    ("sources given as a JSON object, whose keys a set conversion silently accepted",
     "files=(\n  README.md\n)\n",
     {"scripts/build-llms-full.sh": 0, "README.md": 0}, True),
    ("the same source recorded twice",
     "files=(\n  README.md\n)\n", BASE + ["README.md"], True),

    # FALSE ALARMS. Each of these is ordinary Bash the first version invented drift from.
    ("a comment on its own line inside the array",
     "files=(\n  # core guides\n  README.md\n)\n", BASE, False),
    ("a quoted filename, which is that filename",
     'files=(\n  "README.md"\n)\n', BASE, False),

    # THE GATE STILL DOES ITS JOB.
    ("a source built in and not recorded is still caught",
     "files=(\n  README.md\n  nginx.md\n)\n", BASE, True),
    ("a correct repository passes",
     "files=(\n  README.md\n)\n", BASE, False),
)

# A line continuation is shell syntax this gate does not read. It fails, and the point of
# the case is WHICH way it fails: with the honest "cannot read the source list" rather than
# by inventing a backslash-shaped source. Checked separately because the assertion is on
# the message, not only the exit status.
CONTINUATION = "files=(\n  README.md \\\n)\n"


def main() -> int:
    failures = []
    for desc, body, sources, must_fail in CASES:
        rc, out = run_against(body, sources)
        if bool(rc) != must_fail:
            want = "fail" if must_fail else "pass"
            failures.append(f"{desc}: expected the gate to {want}, it did not ({out})")

    rc, out = run_against(CONTINUATION, BASE)
    if not rc:
        failures.append("a line continuation: expected the gate to fail, it passed")
    elif "cannot read the source list" not in out:
        failures.append(
            f"a line continuation: expected the honest unreadable message, got: {out}")

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {len(CASES) + 1} recorded cases for the generated-file record gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
