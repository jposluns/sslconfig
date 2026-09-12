#!/usr/bin/env python3
r"""Cases for check_shell_blocks.py, including the defects it cannot catch.

Four review rounds are recorded. Three of them were spent on a placeholder check that no longer
exists: five rules were written for it and all five were beaten by legal shell a guide could
plausibly carry, the last of them by an ordinary sed substitution. The gate's docstring tells
that story. What this file keeps from it is the KNOWN LIMITS group, which now records the gap
that removal left, with the shapes that fall into it, so nobody reads the gate's name and
assumes coverage it does not have.

The FALSE ALARMS group is retained for the same reason in the other direction: those are the
reviewers' own inputs, every one legal shell or legal configuration, and they are the cases that
would go red the moment anyone reintroduces a placeholder rule. That is deliberate. A sixth rule
should have to face them before it ships.

What remains is shellcheck, and most of this file is now about making sure it actually ran. The
canary case is the important one: a reviewer used an environment variable to make the real
shellcheck exit 1, write to stderr and print nothing, which the gate read as a clean run over
every block in the corpus.

The cases that need shellcheck SKIP when shellcheck is absent rather than failing, because the
gate skips too and its docstring promises the suite stays green.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
HAVE_SHELLCHECK = shutil.which("shellcheck") is not None


def run_against(block, fence="```bash", env=None, path_prefix=None, raw=None, home=None):
    """Build a throwaway repository holding one guide and run the real gate. (exit, output)."""
    d = Path(tempfile.mkdtemp())
    try:
        (d / "tools").mkdir()
        for f in ("check_shell_blocks.py", "_walk.py", "_markdown.py"):
            shutil.copy(TOOLS / f, d / "tools" / f)
        if raw is not None:
            body = raw
        else:
            marker = re.match(r"[`~]+", fence).group(0)
            body = "# T\n\n## Verify\n\n" + fence + "\n" + block + "\n" + marker + "\n"
        (d / "guide.md").write_text(body, encoding="utf-8")
        run_env = dict(os.environ)
        if env:
            run_env.update(env)
        if home:
            run_env["HOME"] = home
        if path_prefix:
            run_env["PATH"] = f"{path_prefix}{os.pathsep}{run_env.get('PATH', '')}"
        r = subprocess.run([sys.executable, "tools/check_shell_blocks.py"], cwd=d,
                           capture_output=True, text=True, env=run_env)
        return r.returncode, r.stdout.strip()
    finally:
        shutil.rmtree(d, ignore_errors=True)


def run_multi(guides, path_prefix=None):
    """Run the gate over several guides at once. (exit, output).

    Every other case here uses one guide with one block, so nothing noticed a gate that read
    only the first guide, only the first block, or reused one temporary filename for all of
    them. A reviewer found four mutants living in that gap.
    """
    d = Path(tempfile.mkdtemp())
    try:
        (d / "tools").mkdir()
        for f in ("check_shell_blocks.py", "_walk.py", "_markdown.py"):
            shutil.copy(TOOLS / f, d / "tools" / f)
        for name, body in guides.items():
            (d / name).write_text(body, encoding="utf-8")
        env = dict(os.environ)
        if path_prefix:
            env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
        r = subprocess.run([sys.executable, "tools/check_shell_blocks.py"], cwd=d,
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stdout.strip()
    finally:
        shutil.rmtree(d, ignore_errors=True)


APACHE = "<Location />\n  Require valid-user\n</Location>"

# (description, block, must_fail, expected substring or None, needs_shellcheck)
CASES = (
    # CAUGHT BY SHELLCHECK. These are why it is here at all.
    ("a placeholder as a command argument, which SC2217 catches",
     "chown <service-user> server.key", True, "SC2217", True),
    ("two competing redirections",
     "curl -sI https://<machine>.<tailnet>.ts.net/", True, "SC2261", True),
    ("an unquoted expansion that breaks on a path with a space",
     "cp a.pem ${HOME}/certs/b.pem", True, "SC2086", True),
    ("an unquoted command substitution",
     "kafka-storage.sh format -t $(kafka-storage.sh random-uuid)", True, "SC2046", True),
    # No longer excluded: this is what catches a misspelled variable.
    ("a variable referenced and never assigned",
     'cert=/etc/ssl/a.pem\nopenssl x509 -in "$cret" -noout', True, "SC2154", True),
    ("a sourced file that cannot be followed",
     "source ./deployment.env\ncurl -sS https://app.example.com/", True, "SC1091", True),
    ("a variable assigned and never used, which a typo in the reader looks like",
     "cert=/etc/ssl/a.pem\necho done", True, "SC2034", True),
    ("a dynamically sourced path",
     'source "$CONFIG_FILE"\ncurl -sS https://app.example.com/', True, "SC1090", True),
    ("local used outside a function",
     "local cert=/etc/ssl/a.pem\necho \"$cert\"", True, "SC2168", True),
    # The escape a guide should use when a fragment genuinely needs a rule off, in view of the
    # reader rather than buried in a suite-wide exclusion.
    ("a fragment that disables one rule in view of the reader",
     "# shellcheck disable=SC1091\nsource ./deployment.env\ncurl -sS https://app.example.com/",
     False, None, True),

    # FALSE ALARMS UNDER THE FIVE DELETED PLACEHOLDER RULES. Reviewers' own inputs, plus the
    # three that beat the last rule. Any sixth rule has to pass all of these first.
    ("ordinary input and output redirection with no space",
     "cat <request.txt>response.txt", False, None, False),
    ("a heredoc opener followed by a redirect with no space",
     "cat <<EOF>response.txt\nplain text\nEOF", False, None, False),
    ("a here-string followed by a redirect",
     'cat <<<"ok">response.txt', False, None, False),
    ("process substitution followed by a redirect",
     "cat <(hostname)>response.txt", False, None, False),
    ("a PCRE named capture group",
     "grep -P '(?<scheme>https)://' urls.txt", False, None, False),
    ("a PCRE named group after a scheme, which beat the URL-anchored rule",
     "grep -oP 'https://(?<host>[^/]+)' urls.txt", False, None, False),
    ("a sed substitution producing angle brackets, which beat the URL-anchored rule",
     r"sed -E 's#https://([^/]+)#<\1>#' urls.txt", False, None, False),
    ("a sed substitution between two URLs, which beat the URL-anchored rule",
     r"sed 's|http://old|<https://new>|' urls.txt", False, None, False),
    ("a sed word boundary",
     r"sed 's/\<http\>/https/g' urls.txt", False, None, False),
    ("a self-closing element in a heredoc body",
     "cat > /tmp/x <<'EOF'\n<deny/>\nEOF", False, None, False),
    ("an XML comment in a heredoc body",
     "cat > /tmp/x <<'EOF'\n<!--deny-->\nEOF", False, None, False),
    ("an email address in angle brackets",
     "printf '%s\\n' 'To: <ops@example.com>'", False, None, False),
    ("Apache syntax inside single quotes",
     "grep -F '<Location />' /etc/apache2/auth.conf", False, None, False),
    ("Apache syntax inside a comment",
     "# Check that <Location /> requires authentication.\n"
     "grep -F 'Require valid-user' /etc/apache2/auth.conf", False, None, False),
    ("a heredoc body holding configuration that looks like shell",
     "cat > /etc/apache2/auth.conf <<'EOF'\n" + APACHE + "\nEOF", False, None, False),
    ("a backslash-quoted heredoc delimiter",
     "cat > /etc/apache2/auth.conf <<\\EOF\n" + APACHE + "\nEOF", False, None, False),
    ("a quoted heredoc delimiter containing punctuation",
     "cat > /etc/apache2/auth.conf <<'END-CONFIG'\n" + APACHE + "\nEND-CONFIG",
     False, None, False),
    ("two heredocs opened on one line",
     "cat /dev/fd/3 /dev/fd/4 3<<'A' 4<<'B'\n" + APACHE + "\nA\nplain\nB", False, None, False),
    ("a house placeholder address",
     "curl -s http://203.0.113.10:11434/api/tags", False, None, False),
    ("an ordinary correct Verify block",
     "ss -tlnp | grep 8080\ncurl -sS -o /dev/null -w '%{http_code}\\n' https://app.example.com/",
     False, None, False),

    # KNOWN LIMITS. Each asserts the gate's CURRENT answer so a change that closes one is loud.
    # The first three are the gap that deleting the placeholder check left, and nothing else in
    # this suite covers them. The last two are the defects that motivated the gate.
    ("known limit: an angle-bracket placeholder in a URL",
     "curl -s http://<public-ip>:11434/api/tags", False, None, True),
    ("known limit: an angle-bracket placeholder in a quoted header value",
     'curl -s https://app.example.com/ -H "Authorization: Bearer <key>"', False, None, True),
    ("known limit: an angle-bracket placeholder ssh does not redirect over",
     "ssh <user@host> 'uptime'", False, None, True),
    ("known limit: a valid command carrying an invalid argument",
     "head -c 11m /dev/zero | curl -X POST --data-binary @- https://app.example.com/",
     False, None, True),
    ("known limit: a glob stored in a variable and expanded unquoted",
     'CURL="curl -q --noproxy * -sS"\n$CURL -o /dev/null https://app.example.com/',
     False, None, True),
)

# Fences the pre-`Fences` expression silently skipped.
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

    if HAVE_SHELLCHECK:
        # Every guide and every block, not just the first of each. Four mutants lived here.
        rc, out = run_multi({
            "a.md": "# A\n\n## Verify\n\n```bash\necho ok\n```\n\n```bash\n"
                    "cp a.pem ${HOME}/b.pem\n```\n",
            "b.md": "# B\n\n## Verify\n\n```bash\ncp c.pem ${HOME}/d.pem\n```\n"})
        if not rc or "a.md:10:" not in out or "b.md:6:" not in out:
            failures.append(
                f"the gate did not report the second block of the first guide AND the first "
                f"block of the second guide: {out!r}")
        rc, out = run_multi({
            "a.md": "# A\n\n## Verify\n\n```bash\necho ok\n```\n",
            "b.md": "# B\n\n## Verify\n\n```bash\necho ok\n```\n"})
        if rc or "2 bash blocks in 2 guides" not in out:
            failures.append(f"the pass line does not count every block and guide: {out!r}")

        # A line separator splitlines() treats as a break and a reader does not.
        rc, out = run_multi({"a.md": "# A\n\n## Verify\n\n```bash\n"
                                     "printf '%s' 'x\u2028y'\ncp a.pem ${HOME}/b.pem\n```\n"})
        if not rc or "a.md:7:" not in out:
            failures.append(
                f"a U+2028 in a block shifted the reported line number: {out!r}")

        # Every fence form must actually be read. The previous expression matched none of
        # these, so a block behind one left "every fenced bash block" silently.
        for desc, fence in FENCES:
            rc, out = run_against("cp a.pem ${HOME}/b.pem", fence=fence)
            if not rc or "SC2086" not in out:
                failures.append(f"{desc}: the block was not linted ({out})")

        # A non-bash info string must not be linted as bash.
        rc, out = run_against("cp a.pem ${HOME}/b.pem", fence="```text")
        if rc:
            failures.append(f"a ```text fence was linted as bash: {out!r}")

        # The first word of the info string, case-insensitively. Comparing the whole string
        # missed two forms that render as bash and that a reader copies from.
        for fence in ("```Bash", "```bash {.numberLines}"):
            rc, out = run_against("cp a.pem ${HOME}/b.pem", fence=fence)
            if not rc or "SC2086" not in out:
                failures.append(f"a {fence} fence was not linted: {out!r}")

        # An indented fence has its own indentation removed, per CommonMark. Leaving it on
        # handed shellcheck an indented script and produced a parse error against a block that
        # renders and runs correctly.
        rc, out = run_against(None, raw=(
            "# T\n\n## Verify\n\n- step:\n\n  ```bash\n  cat <<'EOF'\n  Require valid-user\n"
            "  EOF\n  ```\n"))
        if rc:
            failures.append(f"an indented fence was linted with its indentation on: {out!r}")

        # A block the file never closed is still shell a reader copies.
        rc, out = run_against(None, raw="# T\n\n## Verify\n\n```bash\ncp a.pem ${HOME}/b.pem\n")
        if not rc or "SC2086" not in out:
            failures.append(f"an unclosed block was not linted: {out!r}")

        # A finding's line number is mapped back through the added shebang, and a mutant
        # shifting that mapping by one survived every case.
        rc, out = run_against("echo one\necho two\ncp a.pem ${HOME}/b.pem")
        if "guide.md:8:" not in out or "SC2086" not in out:
            failures.append(f"the finding is not mapped to the guide's line 8: {out!r}")

        # Ambient configuration must not change the answer. A reviewer turned this corpus from
        # passing to seven findings with SHELLCHECK_OPTS alone.
        rc, out = run_against('cp a.pem "${HOME}/certs/b.pem"',
                              env={"SHELLCHECK_OPTS": "--enable=all"})
        if rc:
            failures.append(f"SHELLCHECK_OPTS reached the child and changed the result: {out!r}")

        # GHCRTS made the real shellcheck exit 1 with an empty stdout, which the gate read as a
        # clean run over every block.
        rc, out = run_against('cp a.pem "${HOME}/certs/b.pem"', env={"GHCRTS": "-M1m"})
        if rc:
            failures.append(f"GHCRTS reached the child and stopped the lint: {out!r}")

        # --norc: a .shellcheckrc in the invoking user's home must not turn a rule off.
        rc_home = Path(tempfile.mkdtemp())
        try:
            (rc_home / ".shellcheckrc").write_text("disable=SC2086\n", encoding="utf-8")
            rc, out = run_against("cp a.pem ${HOME}/b.pem", home=str(rc_home))
            # The finding has to be reported against the GUIDE. Asserting only that the output
            # mentions SC2086 let this pass on the canary's own failure message, which names
            # the same code, so the mutant that drops --norc survived the first version of it.
            if not rc or "guide.md:6:" not in out or "SC2086" not in out:
                failures.append(
                    f"a .shellcheckrc in HOME disabled a rule, so --norc is not in effect: "
                    f"{out!r}")
        finally:
            shutil.rmtree(rc_home, ignore_errors=True)

        # The canary has to be matched on its own path field and a bracketed code. A reviewer
        # got past a prefix test with a forged `<canary>.forged` row and past a substring test
        # with SC20860.
        for label, line in (
                ("a forged path suffix", '%s.forged:2:4: note: x [SC2086]'),
                ("a longer code", '%s:2:4: note: x [SC20860]')):
            stub = Path(tempfile.mkdtemp())
            try:
                (stub / "shellcheck").write_text(
                    '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "version: 9.9.9"; exit 0; fi\n'
                    'for a in "$@"; do case "$a" in */canary.sh) printf "' + line + '\\n" "$a";; esac; done\n'
                    'exit 1\n', encoding="utf-8")
                (stub / "shellcheck").chmod(0o755)
                rc, out = run_against("echo ok", path_prefix=str(stub))
                if not rc or "did not lint" not in out:
                    failures.append(
                        f"the canary accepted {label}, so it does not identify its own "
                        f"diagnostic: {out!r}")
            finally:
                shutil.rmtree(stub, ignore_errors=True)

        # The canary: a shellcheck that answers without linting must not read as a pass,
        # whatever exit code it chooses. This stub is the GHCRTS shape through a channel the
        # gate does not strip.
        stub = Path(tempfile.mkdtemp())
        try:
            (stub / "shellcheck").write_text(
                '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "version: 9.9.9"; exit 0; fi\n'
                'echo "shellcheck: broken" >&2\nexit 1\n', encoding="utf-8")
            (stub / "shellcheck").chmod(0o755)
            rc, out = run_against("echo ok", path_prefix=str(stub))
            if not rc or "did not lint" not in out:
                failures.append(
                    f"a shellcheck that exited 1 without linting was read as a pass: {out!r}")
        finally:
            shutil.rmtree(stub, ignore_errors=True)

        # An exit code that is neither clean nor findings means the run did not finish, so its
        # output is not the whole answer even when the canary came back. This stub lints the
        # canary correctly and then exits 2, which nothing else here covers.
        stub = Path(tempfile.mkdtemp())
        try:
            (stub / "shellcheck").write_text(
                '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "version: 9.9.9"; exit 0; fi\n'
                'for a in "$@"; do case "$a" in */canary.sh) printf "%s:2:4: note: Double quote '
                'to prevent globbing and word splitting. [SC2086]\\n" "$a";; esac; done\n'
                'echo "shellcheck: could not read one file" >&2\nexit 2\n', encoding="utf-8")
            (stub / "shellcheck").chmod(0o755)
            rc, out = run_against("echo ok", path_prefix=str(stub))
            if not rc or "exited 2" not in out:
                failures.append(
                    f"a shellcheck that linted the canary and then exited 2 was read as a "
                    f"pass: {out!r}")
        finally:
            shutil.rmtree(stub, ignore_errors=True)

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    limits = sum(1 for c in CASES
                 if c[0].startswith("known limit:") and (HAVE_SHELLCHECK or not c[4]))
    ran = len(CASES) - skipped
    note = f", {skipped} skipped because shellcheck is not installed" if skipped else ""
    print(f"  ok    {ran} recorded cases for the shell-block gate: "
          f"{ran - limits} behaviours checked, {limits} disclosed limits still open{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
