#!/usr/bin/env python3
r"""Run shellcheck over every fenced bash block, and catch one thing shellcheck cannot.

WHY THIS EXISTS: the gate suite checks Markdown structure, flags, citations and prose, and
nothing checked whether the shell in a Verify block is shell. Two defects this corpus
produced went past every other gate. `head -c 11m` used a lowercase suffix GNU coreutils
rejects, so curl posted an empty body and a size-limit check passed untested. And
`chown <service-user> server.key` reads from a file called `service-user` rather than naming
an owner.

WHAT IT CATCHES, checked rather than assumed. shellcheck catches the second on its own,
through SC2217, with no competing redirection needed; an earlier version of this docstring
said the opposite and a reviewer ran it. `head -c 11m` is valid syntax carrying an invalid
argument, which no linter can see, and this gate does not catch it either. Beyond the
motivating pair, shellcheck found five real defects across two guides on its first run over
this corpus: competing redirections, an unquoted `${HOME}` that breaks on a path with a
space, an unquoted command substitution. That is the evidence for keeping it.

THE SECOND CHECK is one regular expression, and it is one because three larger rules lost.
`<[^\s<>]+>`, not preceded by a slash. An angle-bracket placeholder is a single word between
angle brackets: `<public-ip>`, `<service-user>`, `<user@host>`, `<IP:PORT>`. Every shell
construct that uses an angle bracket puts something else there. A redirection has whitespace
or a file descriptor around it (`<request.txt >response.txt`, `2>&1`, `3<>/dev/tcp/...`). A
heredoc doubles the bracket (`<<EOF`, `<<-EOF`, `<<'END-CONFIG'`, `<<\EOF`, `<<<str`).
Process substitution follows it with a parenthesis (`<(sort a)`). And the configuration this
corpus carries inside heredocs either contains a space (`<Location />`, `<VirtualHost *:443>`,
`<IfModule mod_ssl.c>`) or is a closing tag, which is what the leading-slash exclusion is for
(`</Location>`). One expression separates all of that, which is why this gate no longer
tracks quotes or heredocs at all.

WHAT THE EARLIER RULES COST. The version before this reported any angle-bracket text anywhere
and tracked heredocs to spare their bodies. A reviewer demonstrated eight failures in both
directions: `'<Location />'` in single quotes and the same text in a comment were reported as
redirections; `openssl s_client ... <request.txt >response.txt` was reported although it is
ordinary redirection; `cat <<\EOF`, `cat <<'END-CONFIG'` and a line opening two heredocs at
once were mis-parsed; and a COMMENT that merely contained `cat <<EOF` silenced every check for
the rest of the block. The expression above gets all eight right by construction. It was then
run over the whole corpus: 156 bash blocks, zero findings, which is the state the corpus is
already in.

ITS OWN LIMITS, stated rather than discovered later. A bare `<Directory>` or `<html>` inside a
heredoc, with no attribute and so no space, would be reported. No guide has one; if one ever
does, the honest fix is to widen the exclusion deliberately rather than to reach back for a
quote tracker. And it knows nothing about quoting, which is on purpose: `"Bearer <key>"` is
still a placeholder a reader must replace, and nothing else in this suite would catch it.

THE FENCE is `_markdown.Fences`, this repository's one definition of a fenced code block,
rather than an expression of this gate's own. The expression it replaces was `^```bash\n`,
and a reviewer showed it silently skipped a fence with a trailing space after the info
string, a four-backtick fence, and a `~~~bash` fence. Reusing the shared tracker found two
more blocks in the corpus on the first run, 156 rather than 154.

WHEN SHELLCHECK IS NOT INSTALLED this prints a SKIP and returns 0. That is a GAP, not a pass,
and the message says so. The placeholder check does not depend on it and always runs. The
recorded cases in test_shell_blocks.py skip alongside it, because an earlier version left
this gate skipping while its own tests went red one file later, so the suite did not stay
green the way this paragraph promised.

DETERMINISM. shellcheck reads `SHELLCHECK_OPTS` from the environment and `.shellcheckrc` from
the filesystem, and a reviewer used both to turn this corpus from passing to seven findings
and back without changing a line of it. The variable is stripped from the child's environment
and `--norc` is passed. Two rules are then excluded by policy rather than by accident:
SC2154, a variable referenced but not assigned, and SC1091, a sourced file not followed.
These blocks are deliberately incomplete fragments whose variables come from an earlier block
or from the reader's own environment, and a sourced deployment file does not exist at lint
time. That is a policy, so it is written here rather than left to whatever the runner does.

THE VERSION IS REPORTED, NOT PINNED. `ubuntu-latest` floats the shellcheck it ships, and a
new version can find something in an unchanged corpus. Installing a pinned build would fix
that by putting a release download inside the required status check, which is the one thing
CLAUDE.md says this suite must never do: every gate is offline so that nothing outside this
repository can turn the build red. So the version is printed in the pass line instead. A
corpus that reddens without changing is then one line of log away from its explanation,
which is the part that actually costs time.

A NON-ZERO EXIT THAT IS NOT A FINDING is now a failure. shellcheck answers 0 for clean and 1
for findings; anything else means it did not lint. Given a bad option it exits 3, writes to
stderr and prints no findings on stdout, and this gate used to read that as a pass.

WHAT THIS DOES NOT PROVE: that a Verify step is correct, that its commands do what their
comments claim, or that a valid command carries valid arguments. It proves the shell parses
and that shellcheck's default rules, less the two excluded above, find nothing.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk
from _markdown import FENCE_RE, Fences  # noqa: E402  one definition of a fenced block

SKIP_DIRS = {".git", "node_modules", "__pycache__", "site", "tools", "scripts", ".github", ".aiqt"}
# A placeholder is one word between angle brackets. See THE SECOND CHECK in the docstring for
# why every shell construct and every configuration element in this corpus falls outside it.
ANGLE_WORD = re.compile(r"<(?!/)[^\s<>]+>")
# Excluded by policy, not by accident. See DETERMINISM: these blocks are fragments.
FRAGMENT_RULES = ("SC2154", "SC1091")


def shellcheck_version():
    """The version string, for the pass line. See THE VERSION IS REPORTED in the docstring."""
    try:
        done = subprocess.run(["shellcheck", "--version"], capture_output=True, text=True,
                              timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    for row in done.stdout.splitlines():
        if row.lower().startswith("version:"):
            return row.split(":", 1)[1].strip()
    return "unknown"


def blocks_of(path):
    """Yield (first_line_number, block_text) for every fenced bash block in a file."""
    # split("\n"), not splitlines(): splitlines() treats U+2028 and U+0085 as line breaks
    # while the line numbers a reader sees do not, so a guide containing one reported the
    # wrong line for every finding after it.
    lines = path.read_text(encoding="utf-8").split("\n")
    fences, start, body = Fences(), None, []
    for n, line in enumerate(lines, 1):
        if fences.feed(line):
            if fences.inside:
                info = FENCE_RE.match(line).group(2).strip()
                start, body = ((n + 1, []) if info == "bash" else (None, []))
            else:
                if start is not None:
                    yield start, "\n".join(body)
                start, body = None, []
            continue
        if start is not None:
            body.append(line)
    if start is not None:
        # A block the file ended without closing. Its content is still shell a reader copies.
        yield start, "\n".join(body)


def main() -> int:  # noqa: C901
    root = Path(__file__).resolve().parents[1]
    findings, n_files, n_blocks = [], 0, 0
    try:
        paths = sorted(walk_files(root, SKIP_DIRS, suffixes={".md"}))
    except Exception as exc:
        print(f"  FAIL  could not walk the repository: {exc}")
        return 1
    paths = [p for p in paths if p.parent == root]

    have_shellcheck = shutil.which("shellcheck") is not None
    version = shellcheck_version() if have_shellcheck else ""
    tmp = Path(tempfile.mkdtemp())
    index = {}
    try:
        for path in paths:
            try:
                found = list(blocks_of(path))
            except Exception as exc:
                findings.append(f"{path.name}: unreadable ({exc})")
                continue
            if found:
                n_files += 1
            for first, body in found:
                n_blocks += 1
                for offset, line in enumerate(body.split("\n")):
                    for m in ANGLE_WORD.finditer(line):
                        findings.append(
                            f"{path.name}:{first + offset}:{m.start() + 1}: {m.group(0)} is a "
                            f"redirection to the shell, not a placeholder; use a house "
                            f"placeholder such as 203.0.113.10, or REPLACE_WITH_A_NAME for a "
                            f"value the reader supplies")
                if have_shellcheck:
                    name = tmp / f"{n_blocks:04d}.sh"
                    name.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
                    index[name.name] = (path.name, first)

        if have_shellcheck and index:
            env = {k: v for k, v in os.environ.items() if k != "SHELLCHECK_OPTS"}
            try:
                done = subprocess.run(
                    ["shellcheck", "--norc", "-f", "gcc", "-s", "bash",
                     f"--exclude={','.join(FRAGMENT_RULES)}",
                     *sorted(str(tmp / n) for n in index)],
                    capture_output=True, text=True, timeout=180, env=env)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"  FAIL  shellcheck could not be run: {exc}")
                return 1
            if done.returncode not in (0, 1):
                # 0 is clean, 1 is findings. Anything else means it did not lint at all, and
                # reading that as a pass is how a gate goes quiet without going red.
                print(f"  FAIL  shellcheck exited {done.returncode} instead of linting, so "
                      f"{n_blocks} blocks went unchecked: {done.stderr.strip()[:200]}")
                return 1
            for row in done.stdout.splitlines():
                parts = row.split(":", 4)
                if len(parts) < 5:
                    continue
                fname, lineno, _col, _sev, message = parts
                guide, first = index.get(Path(fname).name, ("?", 0))
                # The block gains a shebang, so extracted line 2 is the block's first line.
                findings.append(f"{guide}:{first + int(lineno) - 2}:{message.strip()}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if findings:
        for f in sorted(findings):
            print(f"  FAIL  {f}")
        return 1
    if not have_shellcheck:
        print(f"  SKIP  shellcheck is not installed, so {n_blocks} bash blocks in {n_files} "
              f"guides went unlinted; the placeholder check ran and found nothing")
        return 0
    print(f"  ok    {n_blocks} bash blocks in {n_files} guides parse and pass "
          f"shellcheck {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
