#!/usr/bin/env python3
"""Cases for check_gensrc.py, against what it does now rather than what it used to.

This file was rewritten when the gate stopped trying to work out what a build script lists
and started asking it. Most of its previous cases tested a parser that no longer exists: a
comment inside a word, a quoted filename with a space, a glob, mismatched quotes. Bash
resolves all of those now, because bash runs the script, so those cases had nothing left to
assert and keeping them would have meant asserting things about deleted code.

Three survive in a different form: a variable referenced inside the array, a quoted filename
containing a space, and the `typeset -a files+=` append, which now sits among the placement
cases because placement is what decides whether the listing reports it. They are inputs that
beat both earlier implementations, and they are here to show the current one handles them by
construction rather than by another special case.

One case here records a KNOWN LIMIT rather than a closed finding, and it lives outside the
table in `disclosed_limit()` because asserting an exit status was not enough to record it. It
used to be a table row asserting that the gate passes, which it does whether or not the bug is
present; a reviewer removed the bug and the suite stayed green. The replacement runs the build
as well as the listing and fails unless the disagreement it discloses is really there. The
success line still counts it separately, because reporting an open limit as a closed finding is
the kind of quiet overclaim this file exists to prevent.

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
REGENERATE = "bash scripts/build-llms-full.sh"

# Shaped like the real build script: it states its inputs LAST, immediately before the work, so
# anything changing `files` has to sit above the listing to be reported. `middle` is that
# above-the-listing slot; `tail` is below it, where a change cannot reach the listing.
SCRIPT = """#!/usr/bin/env bash
set -euo pipefail
{preamble}files=(
{body}
)
{middle}if [ "${{1:-}}" = "--list-inputs" ]; then
  printf '%s\\n' "${{files[@]}}"
  exit 0
fi
{tail}cat "${{files[@]}}" > site/llms-full.txt
"""


def script(body, preamble="", middle="", tail=""):
    return SCRIPT.format(body=body, preamble=preamble, middle=middle, tail=tail)


def fixture(script_body, sources, extra_files=(), write_script=True, regenerate=REGENERATE):
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
            (d / f).write_text(f"content of {f}\n", encoding="utf-8")
        (d / ".aiqt" / "gensrc.json").write_text(json.dumps({"generated": [{
            "kind": "file", "target": "site/llms-full.txt",
            "regenerate": regenerate, "sources": sources}]}),
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
# An optional eighth field replaces the manifest's regenerate command.
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
    # The regenerate value is a shell command line, so `str.split` kept the quotes and the
    # suffix match rejected a script path that was plainly named.
    ("a quoted script path in the regenerate command",
     script("  README.md"), BASE, False, (), None, True,
     'bash "scripts/build-llms-full.sh"'),
    ("an unbalanced quote in the regenerate command is reported, not raised",
     script("  README.md"), BASE, True, (), "regenerate command", True,
     'bash "scripts/build-llms-full.sh'),

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
    ("a quoted filename containing a space",
     script('  "guide name.md"'), ["scripts/build-llms-full.sh", "guide name.md"], False,
     ("guide name.md",), None, True),

    # WHERE THE LISTING SITS. The gate believes what the script reports, so the listing has to
    # be the last thing before the work: an append above it is reported, an append below it is
    # not. A second assignment spelled `typeset -a files+=` beat both earlier implementations,
    # and it is the append used here.
    ("an append before the listing is reported",
     script("  README.md", middle="typeset -a files+=(nginx.md)\n"),
     BASE + ["nginx.md"], False, (), None, True),
    ("an append above the listing is included in what it reports",
     script("  README.md", middle="typeset -a files+=(nginx.md)\n"), BASE, True, (),
     "nginx.md is built in but not recorded here", True),
)


def disclosed_limit():
    """The one thing this gate cannot see, demonstrated instead of asserted.

    An append placed AFTER the listing exits changes what the script builds from and never
    reaches the listing. The table case that used to record this only asserted that the gate
    passed, which it does with or without the append, so a reviewer removed the append and
    the suite stayed green: the case was vacuous. This runs the build too, so it fails unless
    the disagreement is really present. Returns a list of problems, empty when the limit is
    still open exactly as disclosed.
    """
    d = Path(tempfile.mkdtemp())
    try:
        for sub in ("tools", "scripts", ".aiqt", "site"):
            (d / sub).mkdir()
        shutil.copy(GATE, d / "tools" / GATE.name)
        sh = d / "scripts" / "build-llms-full.sh"
        sh.write_text(script("  README.md", tail="typeset -a files+=(nginx.md)\n"),
                      encoding="utf-8")
        sh.chmod(0o755)
        (d / "site" / "llms-full.txt").write_text("x", encoding="utf-8")
        for f in ("README.md", "README.sources.md", "nginx.md"):
            (d / f).write_text(f"content of {f}\n", encoding="utf-8")
        (d / ".aiqt" / "gensrc.json").write_text(json.dumps({"generated": [{
            "kind": "file", "target": "site/llms-full.txt",
            "regenerate": REGENERATE, "sources": BASE}]}), encoding="utf-8")

        listed = subprocess.run(["bash", "scripts/build-llms-full.sh", "--list-inputs"],
                                cwd=d, capture_output=True, text=True)
        subprocess.run(["bash", "scripts/build-llms-full.sh"], cwd=d,
                       capture_output=True, text=True, check=True)
        built = (d / "site" / "llms-full.txt").read_text(encoding="utf-8")
        gate = subprocess.run([sys.executable, f"tools/{GATE.name}"], cwd=d,
                              capture_output=True, text=True)

        problems = []
        if "nginx.md" in listed.stdout:
            problems.append("the listing named nginx.md, so there is no disagreement here "
                            "to disclose and this case is testing nothing")
        if "content of nginx.md" not in built:
            problems.append("the build did not consume nginx.md, so the append had no "
                            "effect and this case would pass with its own bug removed")
        if gate.returncode:
            problems.append(f"the gate FAILED, so this limit is closed: delete this case "
                            f"rather than leave it claiming an open gap ({gate.stdout.strip()})")
        return problems
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main() -> int:
    failures = []
    for case in CASES:
        desc, body, sources, must_fail, extra, expected, write = case[:7]
        regenerate = case[7] if len(case) > 7 else REGENERATE
        rc, out = fixture(body, sources, extra, write, regenerate)
        if bool(rc) != must_fail:
            want = "fail" if must_fail else "pass"
            failures.append(f"{desc}: expected the gate to {want}, it did not ({out})")
        elif expected is not None and expected not in out:
            failures.append(
                f"{desc}: the gate's exit status was right but its message was not. "
                f"Expected it to contain {expected!r}. It said: {out!r}")

    for problem in disclosed_limit():
        failures.append(f"known limit: an append AFTER the listing: {problem}")

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    total = len(CASES) + 1
    print(f"  ok    {total} recorded cases for the generated-file record gate: "
          f"{total - 1} findings closed, 1 disclosed limit still open and demonstrated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
