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

A NOTE ON WHAT COUNTS. Only a real inline block is hashed. A `<script src=...>` loads from
elsewhere and is governed by a source expression rather than a hash, and that exemption
belongs to `script` alone: `src` means nothing on `<style>`, which a browser treats as an
ordinary inline element and still requires a hash for. A reviewer demonstrated that skipping
it shipped a block the browser refuses, with a green gate. The page is read with
`html.parser` rather than regular expressions, because an earlier reviewer demonstrated five
ways the expressions were wrong and every one was a question about HTML that the standard
library already answers.

WHAT IT HASHES, AND WHY THE BYTES MATTER. The raw bytes of the file, decoded once, with no
newline translation. `read_text` would quietly turn a CRLF file into LF before hashing, so a
page committed from a Windows checkout hashed one way here and another way in the browser:
unstyled page, dead script, green gate. A reviewer demonstrated exactly that. `.gitattributes`
pins these two files to LF as the underlying guardrail, and this reads bytes so the gate stays
right even if that pin is removed.

WHERE IT IS NOT COMPETENT: `<style>` inside `<svg>`. That is foreign content, where a browser
parses comments and entities into nodes rather than stylesheet text, while `html.parser`
treats every `<style>` as CDATA wherever it sits. The two disagree about what the hash covers,
so a maintainer obeying a hash this gate computed there would pin one the browser never uses.
The gate refuses to guess: it reports the element and says it cannot hash it.

WHAT IT DOES NOT PROVE: that the CSP is otherwise sound, that the hashed content is safe, or
that any header outside the block matching `/` or `/*` is correct. `script-src` is hash-only
with no `'self'`, so the first external script or stylesheet anyone adds is blocked by the
browser and no gate here says so.
"""
import base64
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

PAGE = Path("site") / "index.html"
HEADERS = Path("site") / "_headers"
# (tag, CSP directive). Only a <script src=...> is skipped; see the docstring on why <style>
# with a src is not.
KINDS = (("script", "script-src"), ("style", "style-src"))


class Inline(HTMLParser):
    """Collect the text of inline <script> and <style>, and any style= attribute.

    An earlier version read the page with regular expressions and a reviewer demonstrated
    five ways that was wrong: a quoted `>` inside an attribute swallowed attribute text into
    the hash, `data-src` matched a test for `src` so a real block was skipped, an uppercase
    `<STYLE>` passed unpinned, a `<style>` written inside a JavaScript string was hashed as
    if it were an element, and stripping HTML comments with a regex changed what was hashed
    when the characters were stylesheet text rather than a comment node.

    Every one of those is a question about HTML, and the standard library answers them. The
    previous docstring said that if the regular expressions stopped being adequate this
    should read the page with a real parser rather than grow more expressions. They did, so
    it does.
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = {"script": [], "style": []}
        self.style_attrs = []
        self.foreign = []
        self._open = None
        self._svg = 0

    def handle_starttag(self, tag, attrs):
        names = {k.lower() for k, _ in attrs}
        if "style" in names:
            self.style_attrs.append((tag, self.getpos()[0]))
        if tag == "svg":
            self._svg += 1
        if tag not in ("script", "style"):
            return
        if tag == "script" and "src" in names:
            # Loaded from elsewhere, so a source expression governs it rather than a hash.
            # This exemption is for `script` only: `src` means nothing on `<style>`.
            self._open = None
            return
        if self._svg:
            self.foreign.append((tag, self.getpos()[0]))
            self._open = None
            return
        self._open = tag
        self.blocks[tag].append([])

    def handle_endtag(self, tag):
        if tag == "svg" and self._svg:
            self._svg -= 1
        if tag == self._open:
            self._open = None

    def handle_data(self, data):
        if self._open:
            self.blocks[self._open][-1].append(data)

    def hashes(self, tag):
        out = []
        for parts in self.blocks[tag]:
            body = "".join(parts)
            out.append(base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode())
        return out


def parse_page(html):
    """Parsed inline blocks, style attributes, and any block this gate cannot hash.

    It does NOT raise on malformed markup, whatever an earlier version of this line claimed.
    `html.parser` is lenient by design, and a reviewer fed it five malformed inputs without
    raising one of them. Bad markup produces whatever the parser makes of it, and the hash
    comparison downstream is what fails.
    """
    p = Inline()
    p.feed(html)
    p.close()
    return p


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
        page = parse_page((root / PAGE).read_bytes().decode("utf-8"))
        headers_text = (root / HEADERS).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  FAIL  could not read the site files: {exc}")
        return 1

    block = applicable_block(headers_text)
    if block is None:
        print(f"  FAIL  {HEADERS} has no path block for / or /*")
        return 1
    csps = [m.group(1) for m in
            (re.match(r"content-security-policy:\s*(.*)$", line, re.I) for line in block) if m]
    if not csps:
        print(f"  FAIL  the applicable {HEADERS} block has no Content-Security-Policy header")
        return 1
    if len(csps) > 1:
        # A browser enforces every policy it is sent, so the strictest wins. Reading the first
        # and stopping meant a second header could forbid everything while this gate passed.
        print(f"  FAIL  the applicable {HEADERS} block has {len(csps)} Content-Security-Policy "
              f"headers; a browser enforces all of them, so this gate would only have checked "
              f"the first")
        return 1
    csp = csps[0]

    pinned = 0
    for tag, directive in KINDS:
        hashes = page.hashes(tag)
        if not hashes:
            findings.append(f"no inline <{tag}> found in {PAGE}; this gate expects at least one")
            continue
        found = None
        for d in csp.split(";"):
            parts = d.split()
            # Exact name. `style-src-attr` is a different directive, and matching it as a
            # prefix of `style-src` let a rename pass unnoticed.
            if parts and parts[0].lower() == directive:
                found = parts
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

    for tag, line in sorted(set(page.foreign)):
        findings.append(
            f"<{tag}> at {PAGE}:{line} sits inside <svg>, which is foreign content. A browser "
            f"parses comments and entities there into nodes rather than text, so this gate "
            f"cannot compute the hash it would use and will not guess one; move the rule into "
            f"the stylesheet")

    for tag, line in sorted(set(page.style_attrs)):
        findings.append(
            f"<{tag}> at {PAGE}:{line} carries a style= attribute. A CSP hash covers an "
            f"element's text, never an attribute, so this needs 'unsafe-hashes' or the rule "
            f"moved into the stylesheet; pinning the block by hash does not cover it")

    if findings:
        for f in findings:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {pinned} inline blocks in {PAGE} are pinned by hash in the {HEADERS} CSP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
