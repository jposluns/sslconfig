#!/usr/bin/env python3
"""Cases for check_gensrc.py, against what it does now rather than what it used to.

This file was rewritten when the gate stopped trying to work out what a build script lists
and started asking it. Most of its previous cases tested a parser that no longer exists: a
comment inside a word, a quoted filename with a space, a glob, mismatched quotes. Bash
resolves all of those now, because bash runs the script, so those cases had nothing left to
assert and keeping them would have meant asserting things about deleted code.

Three survive in a different form, as the last three cases. They are inputs that beat both
earlier implementations, and they are here to show the current one handles them by
construction rather than by another special case.

A case earns its place by failing when its bug is restored, and most assert on the gate's
MESSAGE as well as its exit status, because an exit code cannot tell a diagnosis from a
crash. That was learned twice on this branch, and again when this very file was left
pointing at the old machinery: every case still exited non-zero, and only the message
assertions revealed they were failing for the wrong reason.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent / "check_gensrc.py"
BASE = ["scripts/build-llms-full.sh", "README.md"]

# Shaped like the real build script: it states its inputs, then would do work.
SCRIPT = """#!/usr/bin/env bash
set -euo pipefail
{preamble}files=(
{body}
)
if [ "${{1:-}}" = "--list-inputs" ]; then
  printf '%s\\n' "${{files[@]}}"
  exit 0
fi
{tail}echo built > site/llms-full.txt
"""


def script(body, preamble="", tail=""):
    return SCRIPT.format(body=body, preamble=preamble, tail=tail)


def fixture(script_body, sources, extra_files=(), write_script=True):
    """Build a throwaway repository and run the real gate in it. Returns (exit, output)."""
    d = Path(tempfile.mkdtemp())
    try:
        for sub in ("tools", "scripts", ".aiqt", "site"):
            (d / sub).mkdir()
        shutil.copy(GATE, d / "tools" / GATE.name)
        if write_script:
            sh = d / "scripts" / "build-llms-full.sh"
            sh.write_text(script_body, encoding="utf-8")
            sh.chmod(0o755)
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


NO_LIST = "#!/usr/bin/env bash\nset -euo pipefail\nfiles=(README.md)\necho built > site/llms-full.txt\n"
LIST_FAILS = ("#!/usr/bin/env bash\nif [ \"${1:-}\" = \"--list-inputs\" ]; then\n"
              "  echo 'no list here' >&2\n  exit 3\nfi\n")

# (description, script, sources, must_fail, extra files, expected substring, write_script)
CASES = (
    # THE DRIFT THIS GATE EXISTS FOR.
    ("a source built in and not recorded",
     script("  README.md\n  nginx.md"), BASE, True, (),
     "nginx.md is built in but not recorded", True),
    ("a source recorded and not built in",
     script("  README.md"), BASE + ["nginx.md"], True, (),
     "nginx.md is recorded here but not built in", True),
    ("the same source recorded twice",
     script("  README.md"), BASE + ["README.md"], True, (), "recorded more than once", True),

    # THE SCRIPT HAS TO BE ABLE TO ANSWER.
    ("a script that does not support --list-inputs",
     NO_LIST, BASE, True, (), "--list-inputs", True),
    ("a script whose --list-inputs fails",
     LIST_FAILS, BASE, True, (), "--list-inputs exited 3", True),
    ("a regenerate command naming a script that is not there",
     "", BASE, True, (), "does not exist", False),

    # THE MANIFEST HAS TO BE WELL FORMED.
    ("sources given as a JSON object, whose keys a set conversion took",
     script("  README.md"), {"scripts/build-llms-full.sh": 0, "README.md": 0}, True, (),
     "sources must be a list of non-empty strings", True),
    ("sources holding an empty string",
     script("  README.md"), BASE + [""], True, (),
     "sources must be a list of non-empty strings", True),

    # A CORRECT REPOSITORY.
    ("a correct repository",
     script("  README.md"), BASE, False, (), None, True),

    # THE INPUTS THAT BEAT BOTH EARLIER IMPLEMENTATIONS. These pass now because bash runs
    # the script, not because anything here special-cases them.
    ("a variable referenced inside the array",
     script("  README.md $guide", preamble="guide=nginx.md\n"),
     BASE + ["nginx.md"], False, (), None, True),
    ("a second assignment spelled typeset -a",
     script("  README.md", tail="typeset -a files+=(nginx.md)\n"), BASE, False, (), None, True),
    ("a quoted filename containing a space",
     script('  "guide name.md"'), ["scripts/build-llms-full.sh", "guide name.md"], False,
     ("guide name.md",), None, True),
)


def main() -> int:
    failures = []
    for desc, body, sources, must_fail, extra, expected, write in CASES:
        rc, out = fixture(body, sources, extra, write)
        if bool(rc) != must_fail:
            want = "fail" if must_fail else "pass"
            failures.append(f"{desc}: expected the gate to {want}, it did not ({out})")
        elif expected is not None and expected not in out:
            failures.append(
                f"{desc}: the gate's exit status was right but its message was not. "
                f"Expected it to contain {expected!r}. It said: {out!r}")

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {len(CASES)} recorded cases for the generated-file record gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
