#!/usr/bin/env python3
r"""Cases for check_shell_blocks.py, including the two defects it cannot catch.

The placeholder rule changed twice under review and is now one expression: `<[^\s<>]+>` not
preceded by a slash. The cases below are split accordingly. The FALSE ALARM group is the
reviewer's own inputs, each of which the previous rule reported as a shell redirection and
none of which is one; they are here because a rule that fires on `'<Location />'` inside
single quotes trains a reader to ignore it. The CAUGHT group includes a placeholder inside
double quotes, which this rule reports on purpose: quoting makes it legal shell, and it is
still a value the reader must replace, and no other gate in this suite would say so.

Two cases are KNOWN LIMITS and neither is a pass. This gate was written because the corpus
produced two shell defects every other gate missed, and it catches neither: `head -c 11m` is
valid syntax with an invalid argument, and an asterisk stored in a variable and expanded
unquoted is the normal way to use a variable holding a command. Both assert the gate's
CURRENT answer so that a change closing one fails loudly instead of being quietly dropped.

The cases that need shellcheck SKIP when shellcheck is absent rather than failing. The gate
itself skips in that situation and its docstring promises the suite stays green; before this,
the gate skipped and these cases went red one file later, so the promise was false.

Each case builds a throwaway repository with one guide and runs the real gate in it.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
HAVE_SHELLCHECK = shutil.which("shellcheck") is not None


def run_against(block, fence="```bash", env=None, path_prefix=None):
    """Build a throwaway repository holding one guide and run the real gate. (exit, output)."""
    d = Path(tempfile.mkdtemp())
    try:
        (d / "tools").mkdir()
        for f in ("check_shell_blocks.py", "_walk.py", "_markdown.py"):
            shutil.copy(TOOLS / f, d / "tools" / f)
        marker = fence.split("bash")[0].rstrip()
        (d / "guide.md").write_text(
            "# T\n\n## Verify\n\n" + fence + "\n" + block + "\n" + marker + "\n",
            encoding="utf-8")
        run_env = dict(os.environ)
        if env:
            run_env.update(env)
        if path_prefix:
            run_env["PATH"] = f"{path_prefix}{os.pathsep}{run_env.get('PATH', '')}"
        r = subprocess.run([sys.executable, "tools/check_shell_blocks.py"], cwd=d,
                           capture_output=True, text=True, env=run_env)
        return r.returncode, r.stdout.strip()
    finally:
        shutil.rmtree(d, ignore_errors=True)


APACHE = "<Location />\n  Require valid-user\n</Location>"

# (description, block, must_fail, expected substring or None, needs_shellcheck)
CASES = (
    # CAUGHT BY THE PLACEHOLDER RULE. Each was a real defect in this corpus.
    ("two competing redirections from an angle-bracket host",
     "curl -sI https://<machine>.<tailnet>.ts.net/", True, "is a redirection", False),
    ("a single redirection shellcheck does not flag",
     "curl -s http://<public-ip>:11434/api/tags", True, "is a redirection", False),
    ("a placeholder as a command argument",
     "chown <service-user> server.key", True, "is a redirection", False),
    ("a placeholder containing a colon",
     "curl -s http://<IP:PORT>/api/tags", True, "is a redirection", False),
    ("a placeholder containing an at sign",
     "ssh <user@host> 'ss -tlnp'", True, "is a redirection", False),
    # Deliberate: quoting makes it legal shell and leaves it a value the reader must replace.
    ("a placeholder inside double quotes, which this rule reports on purpose",
     'curl -s https://app.example.com/ -H "Authorization: Bearer <key>"', True,
     "is a redirection", False),

    # FALSE ALARMS UNDER THE PREVIOUS RULE. A reviewer demonstrated every one of these.
    ("Apache syntax inside single quotes",
     "grep -F '<Location />' /etc/apache2/auth.conf", False, None, False),
    ("Apache syntax inside a comment",
     "# Check that <Location /> requires authentication.\n"
     "grep -F 'Require valid-user' /etc/apache2/auth.conf", False, None, False),
    ("ordinary input and output redirection on one command",
     "openssl s_client -connect app.example.com:443 <request.txt >response.txt",
     False, None, False),
    ("a heredoc body holding configuration that looks like shell",
     "cat > /etc/apache2/auth.conf <<'EOF'\n" + APACHE + "\nEOF", False, None, False),
    ("a backslash-quoted heredoc delimiter",
     "cat > /etc/apache2/auth.conf <<\\EOF\n" + APACHE + "\nEOF", False, None, False),
    ("a quoted heredoc delimiter containing punctuation",
     "cat > /etc/apache2/auth.conf <<'END-CONFIG'\n" + APACHE + "\nEND-CONFIG",
     False, None, False),
    ("two heredocs opened on one line",
     "cat /dev/fd/3 3<<'A'\nplain\nA", False, None, False),
    ("a here-string",
     "grep -q ok <<<'ok'", False, None, False),
    ("process substitution",
     "diff <(sort /etc/hosts) <(sort /etc/hosts)", False, None, False),
    ("a closing tag, which the leading-slash exclusion is for",
     "printf '%s\\n' '<Location />' 'Require valid-user' '</Location>'", False, None, False),
    ("a heredoc opener carrying its own redirect",
     "cat <<EOF > /tmp/x\nplain text\nEOF", False, None, False),
    ("a house placeholder address",
     "curl -s http://203.0.113.10:11434/api/tags", False, None, False),
    ("a quoted expansion",
     'cp a.pem "${HOME}/certs/b.pem"', False, None, False),
    ("an ordinary correct Verify block",
     "ss -tlnp | grep 8080\ncurl -sS -o /dev/null -w '%{http_code}\\n' https://app.example.com/",
     False, None, False),

    # CAUGHT BY SHELLCHECK. These are why shellcheck is here at all.
    ("an unquoted expansion that breaks on a path with a space",
     "cp a.pem ${HOME}/certs/b.pem", True, "SC2086", True),
    ("an unquoted command substitution",
     "kafka-storage.sh format -t $(kafka-storage.sh random-uuid)", True, "SC2046", True),

    # FRAGMENT POLICY. Excluded on purpose: see DETERMINISM in the gate's docstring.
    ("a variable from an earlier block, which SC2154 is excluded for",
     'if [ "$n" -lt 5 ]; then echo low; fi', False, None, True),
    ("a sourced deployment file, which SC1091 is excluded for",
     "source ./deployment.env\ncurl -sS https://app.example.com/", False, None, True),

    # KNOWN LIMITS. Both are the defects that motivated this gate, and it catches neither.
    ("known limit: a valid command carrying an invalid argument",
     "head -c 11m /dev/zero | curl -X POST --data-binary @- https://app.example.com/",
     False, None, False),
    ("known limit: a glob stored in a variable and expanded unquoted",
     'CURL="curl -q --noproxy * -sS"\n$CURL -o /dev/null https://app.example.com/',
     False, None, False),
)

# (description, fence, closing marker) for fences the previous expression silently skipped.
FENCES = (
    ("a fence with a trailing space after the info string", "```bash "),
    ("a four-backtick fence", "````bash"),
    ("a tilde fence", "~~~bash"),
)


def main() -> int:
    failures, skipped = [], 0
    for desc, block, must_fail, expected, needs in CASES:
        if needs and not HAVE_SHELLCHECK:
            skipped += 1
            continue
        rc, out = run_against(block)
        if bool(rc) != must_fail:
            want = "fail" if must_fail else "pass"
            failures.append(f"{desc}: expected the gate to {want}, it did not ({out})")
        elif expected is not None and expected not in out:
            failures.append(
                f"{desc}: the gate's exit status was right but its message was not. "
                f"Expected it to contain {expected!r}. It said: {out!r}")

    # Every fence form must actually be read. The previous expression matched none of these,
    # so a block behind one left "every fenced bash block" without anything saying so.
    for desc, fence in FENCES:
        rc, out = run_against("curl -s http://<public-ip>:11434/api/tags", fence=fence)
        if not rc:
            failures.append(f"{desc}: the block was not read at all, so the gate passed ({out})")

    # The line number and column a finding reports have to be the ones a reader sees. Neither
    # was asserted before, and a reviewer mutated both by 100 without a single case noticing.
    rc, out = run_against("echo one\necho two\ncurl -s http://<public-ip>:9090/")
    if "guide.md:8:16:" not in out:
        failures.append(
            f"the finding's line and column are wrong: the block opens on line 5, so the "
            f"third command is line 8 and the placeholder starts at column 16. It said: {out!r}")

    if HAVE_SHELLCHECK:
        # Ambient configuration must not change the answer. A reviewer turned this corpus from
        # passing to seven findings with this variable alone.
        rc, out = run_against('cp a.pem "${HOME}/certs/b.pem"',
                              env={"SHELLCHECK_OPTS": "--enable=all"})
        if rc:
            failures.append(
                f"SHELLCHECK_OPTS reached the child and changed the result: {out!r}")

        # A shellcheck that does not lint must not read as a clean run. Given a bad option the
        # real one exits 3 with nothing on stdout, and this gate used to call that a pass.
        stub = Path(tempfile.mkdtemp())
        try:
            (stub / "shellcheck").write_text(
                "#!/bin/sh\necho 'shellcheck: broken' >&2\nexit 3\n", encoding="utf-8")
            (stub / "shellcheck").chmod(0o755)
            rc, out = run_against("echo ok", path_prefix=str(stub))
            if not rc or "exited 3" not in out:
                failures.append(
                    f"a shellcheck exiting 3 was not treated as a failure to lint: {out!r}")
        finally:
            shutil.rmtree(stub, ignore_errors=True)

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    limits = sum(1 for c in CASES if c[0].startswith("known limit:"))
    ran = len(CASES) - skipped
    note = f", {skipped} skipped because shellcheck is not installed" if skipped else ""
    print(f"  ok    {ran} recorded cases for the shell-block gate: "
          f"{ran - limits} behaviours checked, {limits} disclosed limits still open{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
