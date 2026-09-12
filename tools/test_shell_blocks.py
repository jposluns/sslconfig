#!/usr/bin/env python3
"""Cases for check_shell_blocks.py, including the ones it cannot catch.

The rule these test changed once: an angle-bracket placeholder is now reported anywhere in a\nbash block, quoted or not, because tracking quotes to exempt the quoted ones cost three\ndemonstrated defects and the corpus had no quoted ones left to exempt.\n\nTwo of these matter more than the rest, and neither is a pass. The gate was written because
this corpus produced two shell defects that every other gate missed, and it catches neither
of them. Both are recorded here as known limits, asserting that the gate stays green, so
that the file cannot quietly start claiming coverage it does not have.

That is not a confession of uselessness. The gate found five real defects across two guides
on its first run over the corpus, and its own angle-bracket check found a third instance
that shellcheck structurally cannot see. The point of recording the two misses is that the
motivating examples were not the evidence, and an earlier draft of the gate's docstring said
they were, until the claim was tested.

Each case builds a throwaway repository with one guide and runs the real gate in it. A case
earns its place by failing when its bug is restored, except the ones marked "known limit:",
which assert the gate's current answer and are counted separately.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def run_against(block):
    """Build a throwaway repository holding one guide and run the real gate. (exit, output)."""
    d = Path(tempfile.mkdtemp())
    try:
        (d / "tools").mkdir()
        for f in ("check_shell_blocks.py", "_walk.py"):
            shutil.copy(TOOLS / f, d / "tools" / f)
        (d / "guide.md").write_text(
            "# T\n\n## Verify\n\n```bash\n" + block + "\n```\n", encoding="utf-8")
        r = subprocess.run([sys.executable, "tools/check_shell_blocks.py"], cwd=d,
                           capture_output=True, text=True)
        return r.returncode, r.stdout.strip()
    finally:
        shutil.rmtree(d, ignore_errors=True)


# (description, block, must_fail, expected substring or None)
CASES = (
    # CAUGHT, and each of these was a real defect in the corpus.
    ("two competing redirections from an angle-bracket host",
     "curl -sI https://<machine>.<tailnet>.ts.net/", True, "is a redirection"),
    ("a single redirection shellcheck does not flag",
     "curl -s http://<public-ip>:11434/api/tags", True, "is a redirection"),
    ("an angle-bracket placeholder as a command argument",
     "chown <service-user> server.key", True, "is a redirection"),
    ("a placeholder containing a colon, which the old class excluded",
     "curl -s http://<IP:PORT>/api/tags", True, "is a redirection"),
    ("a placeholder containing an at sign, which the old class excluded",
     "ssh <user@host> 'ss -tlnp'", True, "is a redirection"),
    ("an unquoted expansion that breaks on a path with a space",
     "cp a.pem ${HOME}/certs/b.pem", True, "SC2086"),
    ("an unquoted command substitution",
     "kafka-storage.sh format -t $(kafka-storage.sh random-uuid)", True, "SC2046"),
    ("a variable referenced and never assigned, which expands to nothing",
     'if [ "$n" -lt 5 ]; then echo low; fi', True, "SC2154"),

    # NOT CAUGHT, and correctly so.
    ("a placeholder inside double quotes, which the rule no longer exempts",
     'curl -s https://x.example.com/ -H "Authorization: Bearer <key>"', True, "is a redirection"),
    ("a house placeholder address",
     "curl -s http://203.0.113.10:11434/api/tags", False, None),
    ("a quoted expansion",
     'cp a.pem "${HOME}/certs/b.pem"', False, None),
    ("a heredoc carrying plain text",
     "cat > /tmp/x <<'EOF'\nplain text\nEOF", False, None),
    ("a heredoc body holding configuration that looks like shell",
     "cat > /etc/apache2/auth.conf <<'EOF'\n<Location />\n  Require valid-user\n</Location>\nEOF",
     False, None),
    ("a heredoc opener carrying its own redirect",
     "cat <<EOF > /tmp/x\nplain text\nEOF", False, None),
    ("an ordinary correct Verify block",
     "ss -tlnp | grep 8080\ncurl -sS -o /dev/null -w '%{http_code}\\n' https://app.example.com/",
     False, None),

    # KNOWN LIMITS. Both are the defects that motivated this gate, and it catches neither.
    # They assert the gate's CURRENT answer so that a future change closing one fails loudly.
    ("known limit: a valid command carrying an invalid argument",
     "head -c 11m /dev/zero | curl -X POST --data-binary @- https://example.com/", False, None),
    ("known limit: a glob stored in a variable and expanded unquoted",
     'CURL="curl -q --noproxy * -sS"\n$CURL -o /dev/null https://example.com/', False, None),
)


def main() -> int:
    failures = []
    for desc, block, must_fail, expected in CASES:
        rc, out = run_against(block)
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
    limits = sum(1 for c in CASES if c[0].startswith("known limit:"))
    print(f"  ok    {len(CASES)} recorded cases for the shell-block gate: "
          f"{len(CASES) - limits} behaviours checked, {limits} disclosed limits still open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
