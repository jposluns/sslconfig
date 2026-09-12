#!/usr/bin/env python3
"""Flag commands in Verify blocks that skip TLS certificate verification.

WHAT THIS CATCHES: the patterns listed in CHECKS below, in a command inside any fenced
code block in a guide. Indented code blocks are NOT scanned. An earlier version scanned
them and flagged a four-space-indented prose bullet that warned readers against the very
flag it named. That also means a fence nested two list levels deep, which is indented four
spaces or more, is not seen; `tools/_markdown.py` says so too. A fenced block inside a block
quotation IS scanned, because a reader copies
from one just as readily; the quotation markers are stripped before the fence is read.
Nested markers are stripped too, and a quotation that ends closes the fence inside it, since
both were demonstrated to hide a block or to scan a paragraph. It scans every block rather
than only Verify sections, because an insecure flag is a defect wherever a reader copies it
from, and because two rounds of review found bugs in the section-tracking logic itself. It
exists because this corpus forbids disabling TLS verification in three places
(common-mistakes.md item 5, self-signed.md, README.sources.md) and three Verify blocks did
it anyway. A probe that skips verification
is satisfied by a substituted certificate as readily as by the right one, and one of those
three sent credentials over the unverified connection.

WHAT THIS IS NOT: a shell parser, and not a proof that a Verify block verifies anything.
It is a TRIPWIRE for the accidental case, and a determined author walks past it. Successive
rounds of adversarial review demonstrated a long list of bypasses of earlier versions,
several of them in fixes made by the round before. Most are closed. These are known to
remain, and are recorded so nobody mistakes a pass for a guarantee:

  - A line continuation SPLITTING A TOKEN: a backslash-newline inside a flag name. The
    shell rejoins it into a working flag; the scanner inserts a space and sees neither
    half.
  - A trust anchor that trusts the wrong thing, for example `-CAfile` fed a certificate
    fetched from the same server. The flags are present and verification passes against
    an attacker's own certificate.
  - Any tool outside CHECKS, such as gnutls-cli, and any spelling of a listed flag that
    the patterns do not name.
  - Options read from somewhere other than the command line: `echo insecure | curl -K -`
    takes the flag from stdin, and `GIT_SSL_NO_VERIFY=1` or `PYTHONHTTPSVERIFY=0` set it in
    the environment. The tool is named in CHECKS; the mechanism is not a flag.
  - A flag reached through a variable, as in `flags="-k"; curl $flags https://host/`.
  - A PREFIXED spelling of a listed keyword, such as `ssl_verify=False`. This one is left
    open deliberately rather than by omission: `gradio.md` carries exactly that spelling for
    a server-side setting that tells Gradio not to validate its OWN certificate at startup,
    which is not a client skipping verification. Widening the pattern would reject that
    honest line, so the pattern stays anchored on the bare keyword.
  - A quotation spanning a line break. Quote state is tracked per physical line, so
    `curl --data-binary 'first line` followed by `# second line' -k https://host/` reads the
    second line as a comment and loses the flag with it.
  - Anything else that needs a shell parser rather than a scanner. Review here has traded
    new edge cases for new edge cases for round after round, and the line is drawn
    deliberately: this file will not become a shell parser or a Markdown one, because a
    wrong parser that looks authoritative is worse for a reader than a scanner that says
    what it is. What remains open is either disclosed in the list above or recorded in
    `tools/test_convention_gates.py` as a case asserting the current wrong answer, so a
    future change that closes one fails loudly rather than passing quietly. That promise
    has been broken once already, by a quoted flag token that was neither listed nor
    recorded, so read it as an intention held to by review rather than as a guarantee the
    code enforces.

Passing this gate is not evidence that a Verify step is correct, that the certificate it
accepts is the right one, or that the connection is trustworthy.

The openssl check is worth naming, because the first version of this file got it exactly
backwards. `s_client -verify_return_error` takes no argument, so a pattern matching
`-verify_return_error 0` could never fire, and the flag's PRESENCE is the safe state. A
bare `s_client -connect host:port` completes a handshake against any certificate, which
is the defect. It is flagged unless the invocation carries BOTH a flag that makes
verification errors fatal (`-verify_return_error`) and a flag that binds the certificate
to the endpoint (`-verify_hostname` or `-verify_ip`). A trust anchor
alone is not enough, because verification continues after errors. Fatal errors alone are
not enough either, because a chain that verifies still binds no name: it accepts any
unexpired certificate that CA signed, for any host.

PROSE IS NOT SCANNED. A guide that warns against `curl -k` has to name the flag.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk
from _markdown import Fences  # noqa: E402  one shared definition of a fenced block

SKIP_DIRS = {".git", "node_modules", "__pycache__", "site", "tools", "scripts", ".github", ".aiqt"}
NOT_A_GUIDE = {"CONTRIBUTING.md", "CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "README.sources.md"}


# A fenced block can sit inside a block quotation, where a reader copies from it exactly as
# readily. Review showed a `> ```bash` / `> curl -k ...` block was invisible to this gate.
BLOCKQUOTE_RE = re.compile(r"^ {0,3}(?:>[ \t]{0,3})+")


def _substitution_end(code, start):
    """Index just past the `)` that closes the `$(` beginning at `start`, quote aware.

    A blind parenthesis count broke in both directions, each demonstrated. A quoted `(`
    inside the substitution, as in `curl -o "$(printf %s '(')" https://host/ -k`, made the
    scanner swallow the rest of the line and lose the flag. A quoted `)`, as in
    `curl -o "$(printf %s ')'; sort -k 2 paths.txt)"`, ended the substitution early and
    attributed sort's `-k` to curl.
    """
    depth, j, quote = 1, start + 2, None
    while j < len(code) and depth:
        ch = code[j]
        if ch == "\\" and quote != "'" and j + 1 < len(code):
            j += 2
            continue
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif code.startswith("$(", j):
            j = _substitution_end(code, j)
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        j += 1
    return j


def split_segments(code, _depth=0):
    """Split a command line into (segment, preceding_separator) pairs.

    Three properties matter, and each was learned from a demonstrated bypass.

    QUOTE AWARENESS. A quote-blind split let `curl 'https://x?a=1&b=2' -k` sever the flag
    from curl. Backslash escapes are honoured outside quotes and inside double quotes, and
    NOT inside single quotes, where the shell has no escapes: reading the backslash in
    `-H 'X-Path: \\'` as an escape swallowed the closing quote and the separator after it.

    REDIRECTIONS ARE NOT SEPARATORS. `curl https://host/ 2>&1 -k` split at the `&` of
    `2>&1`, which left `-k` in a segment with no curl in it and the command passed.

    A COMMAND SUBSTITUTION IS ITS OWN COMMAND. Blanking `$(...)` hid whatever ran inside
    it, so `status=$(curl -k https://host/)` passed. Keeping it inline attributed the inner
    command's flags to the outer one, so `curl -o "$(sort -k 2)"` was reported as
    `curl -k`. Neither is right. The substitution is lifted out, split recursively, and
    appended as its own segment, which is what it is: a command that runs before the one
    around it and shares no flags with it. Lifting happens inside double quotes too, since
    `"$(...)"` is the more common spelling.
    """
    out, buf, quote, sep = [], [], None, ""
    escaped = -1
    subs = []
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "\\" and quote != "'" and i + 1 < len(code):
            buf.append(code[i:i + 2])
            escaped = i + 1   # `\>` is a filename, not a redirection operator
            i += 2
            continue
        if quote != "'" and code.startswith("$(", i):
            j = _substitution_end(code, i)
            subs.append(code[i + 2:j - 1] if code[j - 1:j] == ")" else code[i + 2:])
            buf.append(" " * (j - i))  # the hole it leaves keeps column intent readable
            i = j
            continue
        if quote != "'" and ch == "`":
            # Backtick substitution is the same thing in older syntax, and leaving it
            # inline attributed the inner command's flags to the outer one: review
            # demonstrated `curl -o "`sort -k 2 paths.txt`" https://host/` reported as
            # `curl -k`.
            j = code.find("`", i + 1)
            subs.append(code[i + 1:j] if j != -1 else code[i + 1:])
            j = len(code) if j == -1 else j + 1
            buf.append(" " * (j - i))
            i = j
            continue
        if quote:
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch == "&" and ((i and code[i - 1] in "<>" and i - 1 != escaped)
                            or (i + 1 < len(code) and code[i + 1] == ">")):
            buf.append(ch)  # `2>&1` and `&>log`: a redirection, not a separator
        elif ch in "|;&":
            run = ch
            while i + 1 < len(code) and code[i + 1] in "|&":
                i += 1
                run += code[i]
            out.append(("".join(buf), sep))
            buf, sep = [], run
        else:
            buf.append(ch)
        i += 1
    out.append(("".join(buf), sep))
    if _depth < 4:  # a bound, not a semantic limit: nesting this deep is not real shell
        for inner in subs:
            for seg, _s in split_segments(inner, _depth + 1):
                out.append((seg, ";"))
    return out

INSECURE_CURL = re.compile(r"(?:^|[\s'\"/=`(])curl\b")
# The trailing class must accept everything that can legally abut a flag, including the
# quote that closes a remote command and a redirect glued straight onto it. Review
# demonstrated `ssh host 'curl https://h/ -k'` and `curl https://h/ -k>/dev/null` both
# passing, because the PREFIX class accepted quotes and this one did not. The same
# asymmetry was fixed for the s_client flags in an earlier round and never mirrored here.
# The combined-flag class takes digits and `#` as well as letters, because curl combines
# short flags and `-4`, `-6` and `-#` are all real ones, so `curl -k4` was passing.
# The LEADING class takes quotes too. Widening only the trailing side left `curl '-k'`
# passing for two rounds, while the prefix class in front of `curl` had accepted quotes
# all along.
CURL_FLAG = re.compile(
    r"""(?:^|[\s'"])(?:-[a-zA-Z0-9#]*k[a-zA-Z0-9#]*|--insecure|--proxy-insecure)"""
    r"""(?:[\s=)`'"<>|;&]|$)""")

CHECKS = (
    ("wget --no-check-certificate (prefix abbreviations included)",
     re.compile(r"(?:^|[\s'\"/=`(])wget\b[^\n]*?--no-check-cert\w*")),
    ("python verify=False or verify=0",
     re.compile(r"\bverify\s*=\s*(?:False|0)\b")),
    ("node rejectUnauthorized false",
     re.compile(r"\brejectUnauthorized\s*:\s*false\b")),
    ("NODE_TLS_REJECT_UNAUTHORIZED zero",
     re.compile(r"\bNODE_TLS_REJECT_UNAUTHORIZED\s*=\s*['\"]?0['\"]?")),
    ("httpie --verify=no",
     re.compile(r"\bhttps?\b[^\n]*?--verify[= ]\s*(?:no|false)\b", re.I)),
    ("git http.sslVerify false",
     re.compile(r"http\.sslVerify[\s=]+false", re.I)),
)

# A search command does not RUN what it searches for. A hardening guide legitimately tells a
# reader to hunt their own tree for these strings, and widening the flag boundaries in rounds
# 7 and 8 turned every such instruction into a finding. Only search tools are exempt, and
# only as the segment's own command: `git -c http.sslVerify=false clone` is still caught,
# because the exemption keys on `git grep` and `git log -S`, not on `git`.
SEARCH_COMMAND = re.compile(
    r"""^\s*['"(`]*(?:grep|egrep|fgrep|rg|ag|ack)\b"""
    r"""|^\s*['"(`]*git\s+(?:grep\b|log\b.*?\s-S\b)""")

# openssl s_client verifies nothing unless one of these appears.
SCLIENT = re.compile(r"(?:^|[\s'\"/=`(])openssl\s+s_client\b")
# OpenSSL: "the verify operation continues after errors" unless -verify_return_error is
# given, so a trust source alone does not make verification fatal. The negative forms
# (-no-CAfile and friends) DISABLE trust, so they must not satisfy this.
SCLIENT_VERIFIES = re.compile(r"""(?:^|\s)-verify_return_error(?:[\s<>|)`'";&]|$)""")
SCLIENT_HELP = re.compile(r"\s-(?:help|h)\b")
# Chain verification without an identity check binds nothing to the endpoint: it accepts
# any unexpired certificate that CA signed, for any hostname. self-signed.md says so.
# `-verify_email` is deliberately NOT here. It matches an email SAN, which says nothing about
# the host you connected to: a certificate for wrong.example.com carrying the right email
# address passes it and fails -verify_hostname, demonstrated against OpenSSL.
SCLIENT_BINDS = re.compile(r"""(?:^|\s)-verify_(?:hostname|ip)(?:[\s<>|)=`'";&]|$)""")


def logical_lines(text):
    """Yield (line_number, joined_command) for every fenced code line in the file.

    Scans ALL fenced code blocks, not only those under a Verify heading. Section tracking
    was removed after it produced two demonstrated bugs of its own: a nested `### Verify
    TLS` cleared its own parent section, and a `---` thematic break after a closing fence
    was read as a setext heading. Markdown heading semantics are not worth reimplementing
    for this, and an insecure flag is a defect wherever a reader copies it from.

    What a fence is comes from `_markdown.Fences`, shared with the prose gate, because the
    two used to disagree about marker length and a four-backtick block was read as closed
    at the first three-backtick line inside it.

    Comments are stripped BEFORE continuations are joined, because a comment ending in a
    backslash does not continue in the shell, and joining first swallowed the next command.
    A line that is ONLY a comment ENDS a buffered continuation rather than being skipped:
    in `curl ... \\` then `# no additional arguments` then `sort -k 2`, the backslash joins
    the comment to the curl line and the comment runs to the end of that logical line, so
    `sort` is a separate command. Skipping the comment line joined `sort -k 2` onto the
    curl and reported `curl -k` on legitimate text.
    """
    fences = Fences()
    bq = False
    buf, buf_line = None, None
    for i, raw in enumerate(text.splitlines(), 1):
        line, marked = raw, False
        m = BLOCKQUOTE_RE.match(raw)
        if m and (not fences.inside or bq):
            line, marked = raw[m.end():], True
        if fences.inside and bq and not marked and raw.strip():
            # The quotation ended, so the fence inside it ended with it. Without this the
            # scanner stayed in that fence and read the rest of the document as code: a
            # later unquoted `curl -k` block was skipped as if it were the close, and an
            # ordinary paragraph warning against the flag was reported as a finding.
            fences.close()
            bq = False
        was_inside = fences.inside
        if fences.feed(line):
            if not was_inside:
                bq = marked           # remember the container the fence opened in
            elif buf is not None:
                yield buf_line, buf
                buf, buf_line = None, None
            continue
        if not fences.inside:
            continue
        code = strip_comment(line).rstrip()
        if not code.strip():
            if buf is not None:
                yield buf_line, buf
                buf, buf_line = None, None
            continue
        if code.endswith("\\") and (len(code) - len(code.rstrip("\\"))) % 2:
            frag = code[:-1]
            buf = frag if buf is None else buf + " " + frag.strip()
            if buf_line is None:
                buf_line = i
            continue
        if buf is not None:
            yield buf_line, buf + " " + code.strip()
            buf, buf_line = None, None
        else:
            yield i, code
    if buf is not None:
        yield buf_line, buf


def strip_comment(line):
    """Drop a trailing shell comment without eating a URL fragment or a quoted `#`.

    A comment `#` begins the line or follows whitespace. A fragment `#` does neither, so
    `https://host/#health` survives while `curl ... # note` loses the note. Backslash
    escapes are honoured outside quotes and inside double quotes, and not inside single
    quotes: reading the escaped quote in `-H "X-Note: \\" #note"` as a CLOSING quote made
    the rest of the line a comment and discarded the URL and the flag that followed it.
    """
    out, quote, idx = [], None, 0
    while idx < len(line):
        ch = line[idx]
        if ch == "\\" and quote != "'" and idx + 1 < len(line):
            out.append(line[idx:idx + 2])
            idx += 2
            continue
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (idx == 0 or line[idx - 1].isspace()):
            break
        out.append(ch)
        idx += 1
    return "".join(out)


def findings_for(code):  # noqa: C901
    """Return a label for every insecure pattern in one command line.

    Each segment is judged on its own. There is no adjacency rule any more. An earlier
    version exempted an `s_client` piped into `openssl x509`, reasoning that printing a
    certificate reads it rather than trusts it. Review showed the exemption was a
    laundering pipe: appending `| openssl x509` to an unverified handshake made it pass
    while the comment beside it still claimed the handshake proved something. The exemption
    is gone, and the two guides that inspect publicly trusted certificates carry real
    verification flags instead.
    """
    hits = []
    for segment, _sep in split_segments(code):
        if SEARCH_COMMAND.search(segment):
            continue
        if INSECURE_CURL.search(segment) and CURL_FLAG.search(segment):
            hits.append("curl -k / --insecure")
        if SCLIENT.search(segment) and not SCLIENT_HELP.search(segment):
            if not SCLIENT_VERIFIES.search(segment):
                hits.append("openssl s_client without -verify_return_error: errors are not fatal")
            elif not SCLIENT_BINDS.search(segment):
                hits.append("openssl s_client verifies the chain but binds no hostname")
        for label, pattern in CHECKS:
            if pattern.search(segment):
                hits.append(label)
    return hits


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings, scanned = [], 0
    try:
        paths = sorted(walk_files(root, SKIP_DIRS, suffixes={".md"}))
    except Exception as exc:
        print(f"  FAIL  could not walk the repository: {exc}")
        return 1

    for path in paths:
        if path.parent != root or path.name in NOT_A_GUIDE:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            findings.append(f"{path.name}: unreadable ({exc})")
            continue
        for lineno, line in logical_lines(text):
            code = strip_comment(line)
            for label in findings_for(code):
                findings.append(f"{path.name}:{lineno}: {label}: {code.strip()[:78]}")

    if findings:
        for f in findings:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    no code block in {scanned} guides matches a known TLS-bypass pattern")
    return 0


if __name__ == "__main__":
    sys.exit(main())
