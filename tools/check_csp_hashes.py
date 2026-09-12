#!/usr/bin/env python3
"""Check that every inline script and style in the site is pinned by hash in the CSP.

WHAT THIS PROVES: that `site/_headers` names the sha256 of every inline `<script>` and
`<style>` in `site/index.html`, so an edited block cannot ship with a stale hash. A stale
script hash means the browser refuses to run the script; a stale style hash means it
refuses to apply the stylesheet, and the page renders unstyled. Both are silent in a diff
and obvious to a visitor.

WHY STYLE AS WELL AS SCRIPT: the script side was pinned and the style side was
`'unsafe-inline'`, which permits any inline style at all, including one injected into the
page. The page has exactly one `<style>` block and no `style=` attributes, so the hash
costs nothing to pin. `'unsafe-inline'` was the easy default rather than a considered one.

WHAT IT DOES NOT PROVE: that the CSP is otherwise sound, that the hashed content is safe,
or that any header outside the block matching `/` or `/*` is correct. It compares two
files and says whether they agree.

A NOTE ON WHAT COUNTS. Only a real inline block is hashed: a `<script src=...>` loads from
elsewhere and is governed by a source expression rather than a hash. HTML comments are
stripped first, because a commented-out block is not served. This reads HTML with a regular
expression, which is not a parser; the site is one hand-written page and the expression is
anchored on the tags it actually uses. If that stops being true, this should read the page
with a real parser rather than grow more expressions, which is a lesson this repository
learned expensively elsewhere.
"""
import base64
import hashlib
import re
import sys
from pathlib import Path

PAGE = Path("site") / "index.html"
HEADERS = Path("site") / "_headers"
# (tag, CSP directive). A tag carrying src= is not inline and is skipped.
KINDS = (("script", "script-src"), ("style", "style-src"))


def inline_hashes(html, tag):
    """The sha256 of every inline block of one tag, base64 encoded, in document order."""
    out = []
    for attrs, body in re.findall(rf"<{tag}(\s[^>]*)?>(.*?)</{tag}>", html, re.S):
        if attrs and re.search(r"\bsrc\s*=", attrs):
            continue
        out.append(base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode())
    return out


def applicable_block(headers_text):
    """The header lines of the block matching /* or /, or None."""
    blocks, path, lines = {}, None, []
    for raw in headers_text.splitlines():
        if not raw.strip():
            continue
        if not raw[0].isspace():
            if path is not None:
                blocks[path] = lines
            path, lines = raw.strip(), []
        else:
            lines.append(raw.strip())
    if path is not None:
        blocks[path] = lines
    return blocks.get("/*", blocks.get("/"))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = []
    try:
        html = re.sub(r"<!--.*?-->", "", (root / PAGE).read_text(encoding="utf-8"), flags=re.S)
        headers_text = (root / HEADERS).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  FAIL  could not read the site files: {exc}")
        return 1

    block = applicable_block(headers_text)
    if block is None:
        print(f"  FAIL  {HEADERS} has no path block for / or /*")
        return 1
    csp = None
    for line in block:
        m = re.match(r"content-security-policy:\s*(.*)$", line, re.I)
        if m:
            csp = m.group(1)
            break
    if csp is None:
        print(f"  FAIL  the applicable {HEADERS} block has no Content-Security-Policy header")
        return 1

    pinned = 0
    for tag, directive in KINDS:
        hashes = inline_hashes(html, tag)
        if not hashes:
            findings.append(f"no inline <{tag}> found in {PAGE}; this gate expects at least one")
            continue
        found = None
        for d in csp.split(";"):
            d = d.strip()
            if re.match(rf"{directive}\b", d, re.I):
                found = d.split()
                break
        if found is None:
            findings.append(f"the Content-Security-Policy has no {directive} directive")
            continue
        if "'unsafe-inline'" in found:
            findings.append(
                f"{directive} carries 'unsafe-inline', which permits any inline <{tag}> including "
                f"one injected into the page; pin the hash instead")
        for h in hashes:
            if f"'sha256-{h}'" not in found:
                findings.append(
                    f"{directive} lacks the hash of an inline <{tag}> in {PAGE} (sha256-{h})")
            else:
                pinned += 1

    if findings:
        for f in findings:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {pinned} inline blocks in {PAGE} are pinned by hash in the {HEADERS} CSP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
