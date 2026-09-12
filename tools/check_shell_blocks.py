#!/usr/bin/env python3
"""Run shellcheck over every fenced bash block, and catch one thing shellcheck cannot.

WHY THIS EXISTS: the gate suite checks Markdown structure, flags, citations and prose, and
nothing checked whether the shell in a Verify block is shell. Two defects this corpus
produced went past every other gate. `head -c 11m` used a lowercase suffix GNU coreutils
rejects, so curl posted an empty body and a size-limit check passed untested. And
`CURL="curl -q --noproxy * -sS"` stored an asterisk that every unquoted expansion then
globbed against the reader's working directory, silently not disabling the proxy the line
existed to disable.

WHAT IT CATCHES, honestly: NEITHER of those two. That is worth stating plainly, because the
first draft of this docstring claimed shellcheck caught the second through SC2086 and a test
of the claim showed it does not, even with every optional check enabled. `head -c 11m` is
valid syntax carrying an invalid argument, which no linter can see. `$CURL` expanded without
quotes is deliberate word splitting, which is the normal way to use a variable holding a
command, so shellcheck is right not to flag it.

What it does catch is a different and larger set, and the corpus proved it on the first run:
five real defects across two guides, plus three more found by the second check below. Two
competing redirections, an unquoted `${HOME}` that breaks on a path with a space, an
unquoted command substitution. The value is real; the motivating examples simply were not
the evidence for it, and pretending otherwise would make this file the third gate in this
suite to promise more than it delivers.

THE SECOND CHECK is here because shellcheck has a specific blind spot this corpus walks
into. An angle-bracket placeholder inside a bash block is not a placeholder to the shell,
it is a redirection: `chown <service-user> server.key` reads from a file called
`service-user`. shellcheck catches one only when two redirections compete for one stream,
so `https://<a>.<b>/` is caught with four errors while `http://<c>:8080/x` produces none at
all. This check therefore reports an angle-bracket placeholder anywhere in a bash block,
quoted or not. Quoting made no difference to whether a placeholder belongs in this corpus,
and tracking quotes to exempt the quoted ones cost three demonstrated defects. Heredoc
bodies are skipped, because they are data rather than shell; that is the only shell
construct this gate tracks, and it is tracked because a configuration block inside a
heredoc is exactly the text a fronting-layer guide carries. The corpus now carries none of
these placeholders, the five that existed having been replaced with house placeholders.

WHEN SHELLCHECK IS NOT INSTALLED this prints a SKIP and the suite stays green. That is a
GAP, not a pass, and the message says so. The angle-bracket check does not depend on it and
always runs.

WHAT THIS DOES NOT PROVE: that a Verify step is correct, that its commands do what their
comments claim, or that a valid command carries valid arguments. It proves the shell parses
and that shellcheck's default rules find nothing, on fragments that are deliberately
incomplete: they reference undefined variables and placeholder hosts by design, which is
why each block is linted on its own with a shebang supplied rather than as one script.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk

SKIP_DIRS = {".git", "node_modules", "__pycache__", "site", "tools", "scripts", ".github", ".aiqt"}
BASH_BLOCK = re.compile(r"^```bash\n(.*?)^```", re.S | re.M)
# Any angle-bracket placeholder, anywhere in a bash block. The class is deliberately wide:
# an earlier version excluded `:`, `@` and space, so `<IP:PORT>` and `<user@host>` passed
# while silently truncating a pasted command.
ANGLE = re.compile(r"<[A-Za-z][^<>\n]*>")
# A heredoc body is data, not shell. `<<EOF`, `<<-EOF` and `<<'EOF'` open one; a line equal
# to the marker closes it, allowing leading tabs for the dash form. This is the only shell
# construct this gate tracks, because an Apache or XML configuration block inside a heredoc
# is exactly the text a fronting-layer guide carries, and reading it as shell rejected it.
HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def blocks_of(path):
    """Yield (first_line_number, block_text) for every fenced bash block in a file."""
    text = path.read_text(encoding="utf-8")
    for m in BASH_BLOCK.finditer(text):
        yield text[:m.start()].count("\n") + 2, m.group(1)


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
                # The angle-bracket check, which does not need shellcheck.
                marker = None
                for offset, line in enumerate(body.splitlines()):
                    if marker is not None:
                        if line.strip() == marker:
                            marker = None
                        continue
                    opened = HEREDOC.search(line)
                    # The opener supplies a `<` of its own, so `cat <<EOF > /tmp/x` would
                    # otherwise report `<EOF >` as a placeholder. Blank the openers first.
                    hit = ANGLE.search(HEREDOC.sub(" ", line))
                    if hit:
                        findings.append(
                            f"{path.name}:{first + offset}: {hit.group(0)} is a redirection to the "
                            f"shell, not a placeholder; use a house placeholder such as "
                            f"203.0.113.10, or REPLACE_WITH_A_NAME for a value the reader supplies")
                    if opened:
                        marker = opened.group(2)
                if have_shellcheck:
                    name = tmp / f"{n_blocks:04d}.sh"
                    name.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
                    index[name.name] = (path.name, first)

        if have_shellcheck and index:
            try:
                done = subprocess.run(
                    ["shellcheck", "-f", "gcc", "-s", "bash",
                     *sorted(str(tmp / n) for n in index)],
                    capture_output=True, text=True, timeout=180)
            except (OSError, subprocess.SubprocessError) as exc:
                print(f"  FAIL  shellcheck could not be run: {exc}")
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
              f"guides went unlinted; the angle-bracket check ran and found nothing")
        return 0
    print(f"  ok    {n_blocks} bash blocks in {n_files} guides parse and pass shellcheck")
    return 0


if __name__ == "__main__":
    sys.exit(main())
