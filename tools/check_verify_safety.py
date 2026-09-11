#!/usr/bin/env python3
"""Flag commands in Verify blocks that skip TLS certificate verification.

WHAT THIS CATCHES: the patterns listed in CHECKS below, in a command inside a fenced or
indented code block inside a Verify section. It exists because this corpus forbids
disabling TLS verification in three places (common-mistakes.md item 5, self-signed.md,
README.sources.md) and three Verify blocks did it anyway. A probe that skips verification
is satisfied by a substituted certificate as readily as by the right one, and one of
those three sent credentials over the unverified connection.

WHAT THIS IS NOT: a shell parser, and not a proof that a Verify block verifies anything.
It matches text. An adversarial review of the first version of this file demonstrated
twelve ways past it, which is why the scanning below joins line continuations, strips
comments without eating URL fragments, follows Markdown section nesting, and accepts
tilde fences and indented blocks. Those were the bypasses someone found. Others exist.
Passing this gate is not evidence that a Verify step is correct, that the certificate it
accepts is the right one, or that some tool or spelling outside CHECKS is absent.

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

VERIFY_RE = re.compile(r"^(#{1,6})\s*(.*?)\s*$")
VERIFY_TITLE = re.compile(r"\b(verif\w*|quick checks)\b", re.I)
FENCE_RE = re.compile(r"^\s*(```|~~~)")

# A command segment ends at a pipe, a separator, or a command substitution, so a flag
# belonging to a later command is not attributed to curl. This is what stops `sort -k`
# inside `curl ... -o $(sort -k 2)` from reading as `curl -k`.
SEGMENT_SPLIT = re.compile(r"\|\||&&|[|;&]|\$\(")

INSECURE_CURL = re.compile(r"(?:^|[\s'\"/=])curl\b")
CURL_FLAG = re.compile(r"(?:\s|^)(?:-[a-zA-Z]*k[a-zA-Z]*|--insecure)(?:\s|=|$)")

CHECKS = (
    ("wget --no-check-certificate (prefix abbreviations included)",
     re.compile(r"(?:^|[\s'\"/=])wget\b[^\n]*?--no-check-cert\w*")),
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
SCLIENT = re.compile(r"(?:^|[\s'\"/=])openssl\s+s_client\b")
# OpenSSL: "the verify operation continues after errors" unless -verify_return_error is
# given, so a trust source alone does not make verification fatal. The negative forms
# (-no-CAfile and friends) DISABLE trust, so they must not satisfy this.
SCLIENT_VERIFIES = re.compile(r"(?<!-no)(?<!-no-)\B-verify_return_error\b")
SCLIENT_HELP = re.compile(r"\s-(?:help|h)\b")
# Piping into `openssl x509` reads a certificate rather than trusting it. Printing an
# issuer or an expiry date is a legitimate use of an unverified handshake, so it is not
# flagged; asserting that the handshake proves the certificate is what this catches.
SCLIENT_INSPECTS = re.compile(r"^\s*openssl\s+x509\b")


def logical_lines(text):
    """Yield (line_number, joined_line) for code inside Verify sections.

    Joins shell line continuations, so a flag on the next line is still part of the
    command. Follows Markdown nesting: a deeper heading stays inside the section, only an
    equal or shallower one leaves it. Handles backtick and tilde fences, and 4-space
    indented blocks.
    """
    lines = text.splitlines()
    verify_depth = None
    fence = None
    buf, buf_line = None, None
    for i, line in enumerate(lines, 1):
        m = FENCE_RE.match(line)
        if m and not (fence and m.group(1) != fence):
            fence = None if fence else m.group(1)
            continue
        if fence is None:
            h = VERIFY_RE.match(line)
            if h and line.lstrip().startswith("#"):
                depth = len(h.group(1))
                if VERIFY_TITLE.search(h.group(2)):
                    verify_depth = depth
                elif verify_depth is not None and depth <= verify_depth:
                    verify_depth = None
                continue
        if verify_depth is None:
            continue
        # Inside a Verify section: a fenced line, or a 4-space indented line, is code.
        if fence is None and not re.match(r"^(\s{4,}|\t)\S", line):
            continue
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            frag = stripped[:-1]
            if buf is None:
                buf, buf_line = frag, i
            else:
                buf += " " + frag.strip()
            continue
        if buf is not None:
            yield buf_line, buf + " " + stripped.strip()
            buf, buf_line = None, None
        else:
            yield i, stripped
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
    segments = SEGMENT_SPLIT.split(code)
    for idx, segment in enumerate(segments):
        nxt = segments[idx + 1] if idx + 1 < len(segments) else ""
        if INSECURE_CURL.search(segment) and CURL_FLAG.search(segment):
            hits.append("curl -k / --insecure")
        if (SCLIENT.search(segment) and not SCLIENT_VERIFIES.search(segment)
                and not SCLIENT_HELP.search(segment)
                and not SCLIENT_INSPECTS.search(nxt)):
            hits.append("openssl s_client without -verify_return_error: errors are not fatal")
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
    print(f"  ok    no Verify block in {scanned} guides matches a known TLS-bypass pattern")
    return 0


if __name__ == "__main__":
    sys.exit(main())
