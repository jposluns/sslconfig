#!/usr/bin/env python3
"""Check that every inline block in site/index.html is pinned by hash in the site/_headers CSP.

WHY: the site drops `'unsafe-inline'` and pins its one inline stylesheet and one inline
script by hash. A hash is exact, so editing either block without repinning it produces a page
whose style or script the browser silently refuses. Nothing said so, and the page is the first
thing a security-minded reader inspects.

WHAT IT COMPARES: the hash of each inline block's text against the `'sha256-...'` tokens in
the directive that actually governs it.

WHICH DIRECTIVE GOVERNS. `script-src-elem` and `style-src-elem`, when present, are what a
browser checks an inline ELEMENT against; it falls back to `script-src` or `style-src` only
when the `-elem` form is absent. This gate read only the non-elem form, so adding
`script-src-elem 'none'` left it green over a page the browser refuses entirely. It now
resolves the same way a browser does and says which directive it used.

A NOTE ON WHAT COUNTS. Only a real inline block is hashed. A `<script src=...>` loads from
elsewhere and is governed by a source expression rather than a hash, and that exemption
belongs to `script` alone: `src` means nothing on `<style>`, which a browser treats as an
ordinary inline element and still requires a hash for. Inert blocks are skipped, because a
browser never runs them and so never hashes them: a `<script>` whose `type` is neither empty,
`module`, nor a JavaScript MIME, and a `<style>` whose `type` is set to anything but
`text/css`. Demanding a pin for those would also whitelist that text should it ever move into
a live context.

WHAT IT HASHES, AND WHY THIS LINE HAS BEEN WRONG TWICE. The file's bytes, decoded, with CRLF
and lone CR normalized to LF. It was `read_text`, and a reviewer called that a fail-open
because universal-newline translation erased CRLF before hashing. Acting on that without
checking the browser's own definition made it strictly worse: HTML's input-stream
preprocessing normalizes CR and CRLF to LF BEFORE tokenizing, so a DOM never contains a CR
and a CSP hash covers the normalized text. Reading raw bytes made this gate demand the hash
of the CRLF text, which no browser computes, and a maintainer obeying that message would have
produced exactly the dead script and unstyled page the change claimed to prevent. Checked
here against html5lib and Gumbo: for the committed page converted to CRLF, both produce
element text containing no CR at all and hashing to the values already pinned. So the read is
explicit now rather than incidental: decode, which keeps the fail-closed behaviour on a
non-UTF-8 byte, then apply the spec's normalization rather than the platform's.
`.gitattributes` still pins these two files to LF, which is worth having on its own.

WHERE IT IS NOT COMPETENT: foreign content. Inside `<svg>` and `<math>`, a `<style>` is not an
HTML style element, a browser never applies it as a stylesheet and never CSP-checks it, while
`html.parser` treats every `<style>` as CDATA wherever it sits. Hashing one would tell a
maintainer to pin a hash no browser uses, so the gate reports the element and refuses to guess.
The HTML integration points are the exception and are treated as ordinary HTML, because they
are: `foreignObject`, `desc` and `title` inside `<svg>`, and `mi`, `mo`, `mn`, `ms` and
`mtext` inside `<math>`. Each of those was checked against html5lib rather than assumed.

WHAT IT DOES NOT PROVE: that the CSP is otherwise sound, or that the hashed content is safe.
`script-src` is hash-only with no `'self'`, so the first external script or stylesheet anyone
adds is blocked by the browser and no gate here says so. Two parsing limits are disclosed
rather than handled, neither reachable by this page: an element that breaks out of foreign
content some other way, such as a `<p>` inside `<svg>`, is still counted as foreign; and an
unclosed `<svg>` leaves everything after it counted as foreign, which fails noisily rather
than quietly.
"""
import base64
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

PAGE = Path("site") / "index.html"
HEADERS = Path("site") / "_headers"
# (tag, the directive that governs an inline element of that tag, preferred form first).
KINDS = (("script", ("script-src-elem", "script-src")),
         ("style", ("style-src-elem", "style-src")))

FOREIGN = {"svg", "math"}
# Inside foreign content these return to HTML parsing, so a <style> here IS a stylesheet.
# Verified against html5lib rather than taken from memory.
INTEGRATION = {"foreignobject", "desc", "title", "mi", "mo", "mn", "ms", "mtext"}
# A browser runs a script only for these type values (empty or absent included).
JS_TYPES = {"", "module", "text/javascript", "application/javascript",
            "text/ecmascript", "application/ecmascript", "text/jscript"}


class Inline(HTMLParser):
    """Collect the text of inline <script> and <style>, and any style= attribute.

    An earlier version read the page with regular expressions and a reviewer demonstrated
    five ways that was wrong: a quoted `>` inside an attribute swallowed attribute text into
    the hash, `data-src` matched a test for `src` so a real block was skipped, an uppercase
    `<STYLE>` passed unpinned, a `<style>` written inside a JavaScript string was hashed as
    if it were an element, and stripping HTML comments with a regex changed what was hashed
    when the characters were stylesheet text rather than a comment node.

    Every one of those is a question about HTML, and the standard library answers them.
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = {"script": [], "style": []}
        self.style_attrs = []
        self.foreign = []
        self.inert = []
        self._open = None
        self._foreign = 0
        self._integration = 0

    def _inert(self, tag, attrs):
        """True when a browser would never run or apply this block, so never hash it."""
        value = None
        for k, v in attrs:
            if k.lower() == "type":
                value = (v or "").strip().lower()
        if value is None:
            return False
        if tag == "script":
            return value not in JS_TYPES
        return value not in ("", "text/css")

    def handle_starttag(self, tag, attrs):
        names = {k.lower() for k, _ in attrs}
        if "style" in names:
            self.style_attrs.append((tag, self.getpos()[0]))
        if tag in FOREIGN:
            self._foreign += 1
        elif self._foreign and tag in INTEGRATION:
            self._integration += 1
        if tag not in ("script", "style"):
            return
        if tag == "script" and "src" in names:
            # Loaded from elsewhere, so a source expression governs it rather than a hash.
            # This exemption is for `script` only: `src` means nothing on `<style>`.
            self._open = None
            return
        if self._foreign and not self._integration:
            self.foreign.append((tag, self.getpos()[0]))
            self._open = None
            return
        if self._inert(tag, attrs):
            self.inert.append((tag, self.getpos()[0]))
            self._open = None
            return
        self._open = tag
        self.blocks[tag].append([])

    def handle_endtag(self, tag):
        if tag in FOREIGN and self._foreign:
            self._foreign -= 1
        elif self._foreign and tag in INTEGRATION and self._integration:
            self._integration -= 1
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


def normalized(data: bytes) -> str:
    """The page as a browser's tokenizer sees it. See WHAT IT HASHES in the docstring."""
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def parse_page(html):
    """Parsed inline blocks, style attributes, and any block this gate will not hash.

    It does NOT raise on malformed markup, whatever an earlier version of this line claimed.
    `html.parser` is lenient by design, and a reviewer fed it five malformed inputs without
    raising one. Bad markup produces whatever the parser makes of it, and the hash comparison
    downstream is what fails.
    """
    p = Inline()
    p.feed(html)
    p.close()
    return p


def applicable_blocks(headers_text):
    """Every block whose path matches the site root, in file order, duplicates kept.

    This used to build a dict and take one entry. Two blocks reach the root, `/` and `/*`, and
    a browser is sent whatever each matching rule contributes; the dict also let a duplicate
    path silently overwrite its twin. So a hostile policy in the block this gate did not read
    passed. Returning all of them is the only reading that cannot hide one.
    """
    out, path, lines = [], None, []
    for raw in headers_text.splitlines():
        if not raw.strip():
            continue
        if not raw[0].isspace():
            if path in ("/", "/*"):
                out.append((path, lines))
            path, lines = raw.strip(), []
        else:
            lines.append(raw.strip())
    if path in ("/", "/*"):
        out.append((path, lines))
    return out


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = []
    try:
        page = parse_page(normalized((root / PAGE).read_bytes()))
        headers_text = (root / HEADERS).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  FAIL  could not read the site files: {exc}")
        return 1

    blocks = applicable_blocks(headers_text)
    if not blocks:
        print(f"  FAIL  {HEADERS} has no path block for / or /*")
        return 1
    csps = [(path, m.group(1)) for path, lines in blocks
            for m in (re.match(r"content-security-policy:\s*(.*)$", line, re.I) for line in lines)
            if m]
    if not csps:
        print(f"  FAIL  no block in {HEADERS} matching / or /* has a Content-Security-Policy "
              f"header")
        return 1
    if len(csps) > 1:
        where = ", ".join(path for path, _ in csps)
        print(f"  FAIL  {len(csps)} Content-Security-Policy headers reach the site root "
              f"({where}); a browser enforces all of them, so this gate cannot say which "
              f"governs an inline block")
        return 1
    csp = csps[0][1]

    directives = {}
    for d in csp.split(";"):
        parts = d.split()
        if parts:
            directives.setdefault(parts[0].lower(), parts)

    pinned = 0
    for tag, names in KINDS:
        hashes = page.hashes(tag)
        if not hashes:
            findings.append(f"no inline <{tag}> found in {PAGE}; this gate expects at least one")
            continue
        used = next((n for n in names if n in directives), None)
        if used is None:
            findings.append(
                f"the Content-Security-Policy has no {names[-1]} directive, and no "
                f"{names[0]} either")
            continue
        found = directives[used]
        if "'unsafe-inline'" in found:
            findings.append(
                f"{used} carries 'unsafe-inline', which permits any inline <{tag}> including "
                f"one injected into the page; pin the hash instead")
        for h in hashes:
            if f"'sha256-{h}'" not in found:
                findings.append(
                    f"{used} lacks the hash of an inline <{tag}> in {PAGE} (sha256-{h})")
            else:
                pinned += 1

    for tag, line in sorted(set(page.foreign)):
        findings.append(
            f"<{tag}> at {PAGE}:{line} sits inside <svg> or <math>, which is foreign content. "
            f"A browser does not apply it and does not CSP-check it, so this gate cannot "
            f"compute the hash it would use and will not guess one; move the rule into the "
            f"stylesheet")

    for tag, line in sorted(set(page.inert)):
        findings.append(
            f"<{tag}> at {PAGE}:{line} carries a type a browser never runs or applies. It "
            f"needs no hash, and pinning one would whitelist that text if it ever moved into "
            f"a live context; remove the block or give it a live type deliberately")

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
