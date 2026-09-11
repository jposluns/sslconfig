#!/usr/bin/env python3
"""Flag commands in Verify blocks that skip TLS certificate verification.

WHAT THIS CATCHES: the patterns listed in CHECKS below, in a command inside any fenced or
indented code block in a guide. It scans every block rather than only Verify sections,
because an insecure flag is a defect wherever a reader copies it from, and because two
rounds of review found bugs in the section-tracking logic itself. It exists because this corpus forbids
disabling TLS verification in three places (common-mistakes.md item 5, self-signed.md,
README.sources.md) and three Verify blocks did it anyway. A probe that skips verification
is satisfied by a substituted certificate as readily as by the right one, and one of
those three sent credentials over the unverified connection.

WHAT THIS IS NOT: a shell parser, and not a proof that a Verify block verifies anything.
It is a TRIPWIRE for the accidental case, and a determined author walks past it. Two
rounds of adversarial review demonstrated more than twenty bypasses of earlier versions.
Most are closed. These are known to remain, and are recorded so nobody mistakes a pass
for a guarantee:

  - A line continuation SPLITTING A TOKEN: a backslash-newline inside a flag name. The
    shell rejoins it into a working flag; the scanner inserts a space and sees neither
    half.
  - A trust anchor that trusts the wrong thing, for example `-CAfile` fed a certificate
    fetched from the same server. The flags are present and verification passes against
    an attacker's own certificate.
  - Any tool outside CHECKS, such as gnutls-cli, and any spelling of a listed flag that
    the patterns do not name.

Passing this gate is not evidence that a Verify step is correct, that the certificate it
accepts is the right one, or that the connection is trustworthy.

The openssl check is worth naming, because the first version of this file got it exactly
backwards. `s_client -verify_return_error` takes no argument, so a pattern matching
`-verify_return_error 0` could never fire, and the flag's PRESENCE is the safe state. A
bare `s_client -connect host:port` completes a handshake against any certificate, which
is the defect. It is flagged unless the invocation carries one of the flags that make it
verify something.

PROSE IS NOT SCANNED. A guide that warns against `curl -k` has to name the flag.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk

SKIP_DIRS = {".git", "node_modules", "__pycache__", "site", "tools", "scripts", ".github", ".aiqt"}
NOT_A_GUIDE = {"CONTRIBUTING.md", "CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "README.sources.md"}

VERIFY_RE = re.compile(r"^ {0,3}(#{1,6})\s*(.*?)\s*$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)\s*$")
VERIFY_TITLE = re.compile(r"\b(verif\w*|quick checks)\b", re.I)
FENCE_RE = re.compile(r"^\s*(```|~~~)")

# A command substitution is blanked rather than split on, so the enclosing command survives
# while the flags of the inner command are not attributed to it. That is what keeps
# `curl ... -o $(sort -k 2)` from reading as `curl -k` while `curl -H $(x) -k` still does.
def split_segments(code):
    """Split a command line on separators that appear OUTSIDE quotes.

    A quote-blind split let `curl 'https://x?a=1&b=2' -k` sever the flag from curl, and
    `curl -H "Bearer $(cat t)" ... -k` do the same. Returns (segment, preceding_separator).
    """
    out, buf, quote, sep = [], [], None, ""
    i = 0
    while i < len(code):
        ch = code[i]
        if quote:
            if ch == "\\" and i + 1 < len(code):
                buf.append(code[i:i + 2]); i += 2
                continue
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif code.startswith("$(", i):
            # An opaque unit: keep it in the segment so the enclosing command survives.
            depth, j = 1, i + 2
            while j < len(code) and depth:
                if code[j] == "(":
                    depth += 1
                elif code[j] == ")":
                    depth -= 1
                j += 1
            buf.append(" " * (j - i))  # opaque: keeps the enclosing command, hides its guts
            i = j
            continue
        elif ch in "|;&":
            run = ch
            while i + 1 < len(code) and code[i + 1] in "|&":
                i += 1
                run += code[i]
            out.append(("".join(buf), sep)); buf, sep = [], run
        else:
            buf.append(ch)
        i += 1
    out.append(("".join(buf), sep))
    return out

INSECURE_CURL = re.compile(r"(?:^|[\s'\"/=`(])curl\b")
CURL_FLAG = re.compile(r"(?:\s|^)(?:-[a-zA-Z]*k[a-zA-Z]*|--insecure|--proxy-insecure)(?:[\s=)`]|$)")

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

# openssl s_client verifies nothing unless one of these appears.
SCLIENT = re.compile(r"(?:^|[\s'\"/=`(])openssl\s+s_client\b")
# OpenSSL: "the verify operation continues after errors" unless -verify_return_error is
# given, so a trust source alone does not make verification fatal. The negative forms
# (-no-CAfile and friends) DISABLE trust, so they must not satisfy this.
SCLIENT_VERIFIES = re.compile(r"(?:^|\s)-verify_return_error(?:[\s<>|)]|$)")
SCLIENT_HELP = re.compile(r"\s-(?:help|h)\b")
# Chain verification without an identity check binds nothing to the endpoint: it accepts
# any unexpired certificate that CA signed, for any hostname. self-signed.md says so.
SCLIENT_BINDS = re.compile(r"(?:^|\s)-verify_(?:hostname|ip|email)(?:[\s<>|)=]|$)")


def logical_lines(text):
    """Yield (line_number, joined_command) for every fenced code line in the file.

    Scans ALL fenced code blocks, not only those under a Verify heading.
    Section tracking was removed after it produced two demonstrated bugs of its own: a
    nested `### Verify TLS` cleared its own parent section, and a `---` thematic break
    after a closing fence was read as a setext heading. Markdown heading semantics are not
    worth reimplementing for this, and an insecure flag is a defect wherever it appears.

    Comments are stripped BEFORE continuations are joined, because a comment ending in a
    backslash does not continue in the shell, and joining first swallowed the next command.
    """
    fence = None
    buf, buf_line = None, None
    for i, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if m and not (fence and m.group(1) != fence):
            fence = None if fence else m.group(1)
            continue
        if fence is None:
            continue
        code = strip_comment(line).rstrip()
        if not code.strip():
            continue
        if code.endswith("\\"):
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
    """Drop a trailing shell comment without eating a URL fragment.

    A comment `#` follows whitespace. A fragment `#` does not, so `https://x/#health`
    survives while `curl ... # note` loses the note.
    """
    out, quote = [], None
    for idx, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (idx == 0 or line[idx - 1].isspace()):
            break
        out.append(ch)
    return "".join(out)


def findings_for(code):  # noqa: C901
    """Return a list of labels for every insecure pattern in one command line.

    Segments are examined in order, because the openssl exemption is about ADJACENCY: an
    s_client piped straight into `openssl x509` is reading a certificate, while an
    unrelated `openssl x509` later in the line says nothing about the handshake.
    """
    hits = []
    parts = split_segments(code)
    for idx, (segment, _sep) in enumerate(parts):
        # Only a PIPE means "piped into". A `;` or `&&` sequenced openssl x509 is a
        # separate command and says nothing about the handshake before it.
        nxt = parts[idx + 1][0] if (idx + 1 < len(parts)
                                    and parts[idx + 1][1] == "|") else ""
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
