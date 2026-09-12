#!/usr/bin/env python3
r"""Run shellcheck over every fenced bash block.

WHY THIS EXISTS: the gate suite checks Markdown structure, flags, citations and prose, and
nothing checked whether the shell in a Verify block is shell. On its first run over this
corpus shellcheck found five real defects across two guides: competing redirections, an
unquoted `${HOME}` that breaks on a path with a space, and an unquoted command substitution.
Those are the evidence for keeping it.

WHAT IT DOES NOT CATCH, and this was established by running it rather than by assuming. The
two defects that originally motivated this gate were `head -c 11m`, a lowercase suffix GNU
coreutils rejects so that curl posted an empty body and a size check passed untested, and
`chown <service-user> server.key`, which reads from a file called `service-user`. shellcheck
catches the second through SC2217, with no competing redirection needed. It catches neither
`head -c 11m`, which is valid syntax carrying an invalid argument, nor an angle-bracket
placeholder written into a URL, which is valid syntax too.

THERE IS NO PLACEHOLDER CHECK HERE ANY MORE, and that is a deliberate removal rather than an
oversight. Five rules were written for it and all five were beaten:

  1. Report any angle-bracket text. Lost to `'<Location />'` in quoted Apache configuration.
  2. Skip quoted text. Lost to a placeholder inside a quoted header value.
  3. Require the bracket glued to a word. Lost to `chown <service-user>`.
  4. Require one word between brackets, not preceded by a slash. Lost to nine inputs at once,
     among them `cat <request.txt>response.txt`, `cat <<EOF>response.txt`, a PCRE named group
     `(?<scheme>https)`, a sed word boundary `\<http\>`, a self-closing `<deny/>` in a heredoc,
     and an email address in angle brackets.
  5. Require a URL scheme, then a word in brackets inside the same token. Lost to
     `sed -E 's#https://([^/]+)#<\1>#'`, `sed 's|http://old|<https://new>|'` and
     `grep -oP 'https://(?<host>[^/]+)'`, all of which are ordinary things to write in a guide.

Every one of those false alarms is legal shell that a guide could plausibly carry, and a gate
that rejects a sed substitution teaches a reader to stop reading it. The distinction between a
placeholder and a redirection is semantic, not syntactic, and four rounds of review plus one
self-inflicted round say it is not encodable at a cost worth paying. So it is a review
obligation now, named in CONTRIBUTING, and NOTHING in this suite catches an angle-bracket
placeholder in a bash block. That gap is stated here so nobody rediscovers it as a surprise.

THE CANARY, which is the most important thing left in this file. Every batch is linted with one
extra block KNOWN to produce SC2086, and its finding must come back. If it does not, shellcheck
did not lint and the gate fails, whatever exit code it gave. A reviewer set `GHCRTS=-M1m` in the
environment: the real shellcheck then exits 1, writes to stderr and prints NOTHING on stdout,
and this gate read that as a clean run over all 156 blocks. Blacklisting that one variable would
have fixed that one input; the canary fixes the class, because a lint that cannot find a defect
it was handed did not happen, whatever went wrong. `SHELLCHECK_OPTS` and `GHCRTS` are stripped
and `--norc` is passed as well, but those are hygiene and the canary is the guarantee.

NO RULES ARE EXCLUDED. An earlier version excluded SC2154 and SC1091 on the theory that these
blocks are deliberately incomplete fragments. A reviewer showed the cost: SC2154 is what catches
a misspelled variable, so excluding it hid `"$cret"` where `$cert` was meant. The corpus was then
run against the full default rule set and came back clean, so the exclusions were buying nothing.
A block that genuinely needs a rule off should carry a `# shellcheck disable=` comment where a
reader of the guide can see it.

THE FENCE is `_markdown.Fences`, this repository's one definition of a fenced code block. The
expression it replaces was `^```bash\n`, which silently skipped a fence with a trailing space
after the info string, a four-backtick fence, and a `~~~bash` fence; reusing the shared tracker
found two more blocks and one more guide. An indented fence has its own indentation removed from
each body line, per CommonMark, because leaving it on handed shellcheck an indented script and
produced a parse error against a block that renders and runs fine.

WHEN SHELLCHECK IS NOT INSTALLED this prints a SKIP and returns 0. That is a GAP, not a pass, and
the message says so. The recorded cases skip alongside it so the suite really does stay green.

THE VERSION IS REPORTED, NOT PINNED. `ubuntu-latest` floats the shellcheck it ships and default
rule sets do change between releases. Pinning by download would put a network fetch inside the
required status check, and CLAUDE.md is explicit that every gate is offline so nothing outside
this repository can turn the build red. Vendoring a binary with a checked digest would be
offline, and is declined because a multi-megabyte executable does not belong in a documentation
repository. So the version is printed: a corpus that reddens without changing is then one log
line from its explanation.

WHAT THIS DOES NOT PROVE: that a Verify step is correct, that its commands do what their comments
claim, or that a valid command carries valid arguments.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk
from _markdown import FENCE_RE, Fences  # noqa: E402  one definition of a fenced block

SKIP_DIRS = {".git", "node_modules", "__pycache__", "site", "tools", "scripts", ".github", ".aiqt"}
# Ambient channels that can change or disable the lint. Stripped as hygiene; the canary is what
# actually guarantees the lint happened.
AMBIENT = ("SHELLCHECK_OPTS", "GHCRTS")
# A block shellcheck must find a defect in. If this finding does not come back, it did not lint.
CANARY = "cp $HOME/a /tmp/b\n"
CANARY_CODE = "SC2086"


def blocks_of(path):
    """Yield (first_line_number, block_text) for every fenced bash block in a file."""
    # split("\n"), not splitlines(): splitlines() treats U+2028 and U+0085 as line breaks while
    # the line numbers a reader sees do not, so a guide containing one reported the wrong line
    # for every finding after it.
    lines = path.read_text(encoding="utf-8").split("\n")
    fences, start, body, indent = Fences(), None, [], 0
    for n, line in enumerate(lines, 1):
        if fences.feed(line):
            if fences.inside:
                info = FENCE_RE.match(line).group(2).strip()
                if info == "bash":
                    start, body = n + 1, []
                    indent = len(line) - len(line.lstrip(" "))
                else:
                    start, body = None, []
            else:
                if start is not None:
                    yield start, "\n".join(body)
                start, body = None, []
            continue
        if start is not None:
            # CommonMark removes up to the opening fence's own indentation from each line.
            body.append(line[indent:] if not line[:indent].strip() else line.lstrip(" "))
    if start is not None:
        # A block the file ended without closing. Its content is still shell a reader copies.
        yield start, "\n".join(body)


def shellcheck_version():
    """The version string, for the pass line. See THE VERSION IS REPORTED in the docstring."""
    try:
        done = subprocess.run(["shellcheck", "--version"], capture_output=True, text=True,
                              timeout=30,
                              env={k: v for k, v in os.environ.items() if k not in AMBIENT})
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    for row in done.stdout.splitlines():
        if row.lower().startswith("version:"):
            return row.split(":", 1)[1].strip()
    return "unknown"


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
                if have_shellcheck:
                    name = tmp / f"{n_blocks:04d}.sh"
                    name.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
                    index[name.name] = (path.name, first)

        if have_shellcheck and index:
            canary = tmp / "canary.sh"
            canary.write_text("#!/usr/bin/env bash\n" + CANARY, encoding="utf-8")
            env = {k: v for k, v in os.environ.items() if k not in AMBIENT}
            try:
                done = subprocess.run(
                    ["shellcheck", "--norc", "-f", "gcc", "-s", "bash",
                     *sorted(str(tmp / n) for n in index), str(canary)],
                    capture_output=True, text=True, timeout=180, env=env)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"  FAIL  shellcheck could not be run: {exc}")
                return 1
            rows = done.stdout.splitlines()
            if not any(r.startswith(str(canary)) and CANARY_CODE in r for r in rows):
                # See THE CANARY. Whatever the exit code says, a lint that did not report a
                # defect it was handed did not happen.
                print(f"  FAIL  shellcheck did not report {CANARY_CODE} against the canary "
                      f"block, so it did not lint: {n_blocks} blocks are unchecked "
                      f"(exit {done.returncode}) {done.stderr.strip()[:160]}")
                return 1
            if done.returncode not in (0, 1):
                print(f"  FAIL  shellcheck exited {done.returncode}, so its run over "
                      f"{n_blocks} blocks was incomplete and any findings it printed are not "
                      f"the whole answer: {done.stderr.strip()[:160]}")
                return 1
            for row in rows:
                parts = row.split(":", 4)
                if len(parts) < 5 or Path(parts[0]).name == canary.name:
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
              f"guides went unlinted")
        return 0
    print(f"  ok    {n_blocks} bash blocks in {n_files} guides parse and pass "
          f"shellcheck {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
