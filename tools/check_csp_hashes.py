#!/usr/bin/env python3
"""Check that every inline block in site/index.html is pinned by hash in the site/_headers CSP.

WHY: the site drops `'unsafe-inline'` and pins its one inline stylesheet and one inline script
by hash. A hash is exact, so editing either block without repinning it produces a page whose
style or script the browser silently refuses. Nothing said so, and the page is the first thing
a security-minded reader inspects.

IT REFUSES WHAT IT CANNOT MODEL, WHICH IS THE WHOLE DESIGN. Three rounds were spent teaching
this gate about HTML: `src` on a style, foreign content in `<svg>`, HTML integration points,
MathML, inert script types. Each round closed the case in front of it and the next round found
another divergence between `html.parser` and a browser, including two silent fail-opens: a
`<style>` inside `<svg><title>` that `html.parser` swallows as RCDATA and never reports at all,
and a `<script>` containing `<!--<script>` where the parser stops at the first `</script>` and
a browser does not. Modelling HTML well enough to hash it is a real project, and this page is
one hand-written file with two inline blocks.

So the model is deliberately tiny and everything outside it is a finding:

  - exactly one `<style>` and one `<script>`, each carrying NO attributes;
  - every literal `<style` or `<script` in the file accounted for, either as one of those two
    elements or as text INSIDE one of them (a `<style>` written in a JavaScript string is
    fine and is the round-1 case; one hiding anywhere else is not);
  - no `<!--` inside the script, because that is what opens HTML's script-data escape states,
    which is where the parser and the browser part company;
  - no NUL byte, which a browser's tokenizer turns into U+FFFD before hashing and this would
    not.

Any of those fails with a message saying the page outgrew the gate. That is a real cost: a
page that legitimately needs a second script has to change this file. It buys the property no
amount of parser detail delivered, which is that a green result means the hash is right.

WHAT IT HASHES, AND WHY THIS LINE WAS ONCE WRONG IN BOTH DIRECTIONS. The file's bytes, decoded,
with CRLF and lone CR normalized to LF. It was `read_text`; a reviewer called that a CRLF
fail-open; acting on that without checking the browser's definition made it strictly worse,
because HTML's input-stream preprocessing normalizes CR and CRLF to LF BEFORE tokenizing, so a
DOM never contains a CR and a CSP hash covers the normalized text. Reading raw bytes made this
gate demand a hash no browser computes. Checked against html5lib and Gumbo: for the committed
page converted to CRLF, both produce element text with no CR and hashing to the pinned values.

WHICH DIRECTIVE GOVERNS. CSP3's fallback chain, in order: `script-src-elem`, then `script-src`,
then `default-src`, and the style equivalent. Reading only the plain directive left the gate
green over a page whose `script-src-elem 'none'` the browser refuses; reading only those two
made it fail a page governed perfectly well by `default-src`. Names are matched
case-insensitively and the first occurrence of a directive wins, both per CSP3.

THE HEADERS FILE IS CLOUDFLARE'S, AND ITS SYNTAX DOES MORE THAN THIS ONCE ASSUMED. All of this
is from the Pages documentation. A rule may be an absolute URL, so `https://host/*` reaches the
root as surely as `/*` does, and "an incoming request which matches multiple rules' URL patterns
will inherit all rules' headers", so every matching block counts. `#` starts a comment, which
this gate used to read as a path and so stole the following headers. And a header name prefixed
with `!` DETACHES it: a later `/* ! Content-Security-Policy` removes the policy completely and
the page ships with no CSP at all, which passed silently because a detach line has no colon.

WHAT IT DOES NOT PROVE: that the CSP is otherwise sound, or that the hashed content is safe.
`script-src` is hash-only with no `'self'`, so the first external script or stylesheet anyone
adds is blocked by the browser and no gate here says so.
"""
import base64
import hashlib
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

PAGE = Path("site") / "index.html"
HEADERS = Path("site") / "_headers"
# (tag, the directives that can govern an inline element of that tag, in CSP3 fallback order).
KINDS = (("script", ("script-src-elem", "script-src", "default-src")),
         ("style", ("style-src-elem", "style-src", "default-src")))
OPENER = re.compile(r"<(style|script)\b", re.I)
CSP = "content-security-policy"


class Inline(HTMLParser):
    """Collect the text of every <script> and <style>, and any style= attribute."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.blocks = {"script": [], "style": []}
        self.attrs = {"script": [], "style": []}
        self.style_attrs = []
        self._open = None

    def handle_starttag(self, tag, attrs):
        if any(k.lower() == "style" for k, _ in attrs):
            self.style_attrs.append((tag, self.getpos()[0]))
        if tag in ("script", "style"):
            self._open = tag
            self.blocks[tag].append([])
            self.attrs[tag].append(([k.lower() for k, _ in attrs], self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag == self._open:
            self._open = None

    def handle_data(self, data):
        if self._open:
            self.blocks[self._open][-1].append(data)

    def bodies(self, tag):
        return ["".join(parts) for parts in self.blocks[tag]]


def sha256_b64(text):
    return base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode()


def normalized(data: bytes) -> str:
    """The page as a browser's tokenizer sees it. See WHAT IT HASHES in the docstring."""
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def parse_page(html):
    """Parsed inline blocks and style attributes.

    It does NOT raise on malformed markup, whatever an earlier version of this line claimed.
    `html.parser` is lenient by design, and a reviewer fed it five malformed inputs without
    raising one. Bad markup produces whatever the parser makes of it, and the checks in
    `simple_enough` are what refuse it.
    """
    p = Inline()
    p.feed(html)
    p.close()
    return p


def simple_enough(page, html):
    """Reasons this page is outside the shape the gate can hash. See the docstring."""
    out = []
    if "\x00" in html:
        out.append("the page contains a NUL byte, which a browser's tokenizer replaces with "
                   "U+FFFD before hashing and this gate would not")
    for tag in ("style", "script"):
        bodies = page.bodies(tag)
        if len(bodies) != 1:
            out.append(f"the page has {len(bodies)} <{tag}> elements and this gate models "
                       f"exactly one; pinning more than one by hash needs a gate that knows "
                       f"which is which")
            continue
        names, line = page.attrs[tag][0]
        if names:
            out.append(f"the <{tag}> at {PAGE}:{line} carries attributes ({', '.join(names)}), "
                       f"and whether a browser runs an element with them depends on rules this "
                       f"gate does not model; keep it bare or extend the gate deliberately")
    scripts = page.bodies("script")
    if len(scripts) == 1 and "<!--" in scripts[0]:
        out.append("the inline <script> contains `<!--`, which opens HTML's script-data escape "
                   "states; a browser reads to a later </script> than this parser does, so the "
                   "hash here would not be the hash there")
    # Every literal opener has to be one of the two elements or text inside one of them. This
    # is what catches an element the parser never reported: a <style> inside <svg><title> is
    # swallowed as RCDATA and produces no start tag at all, and it is live in a browser.
    inside = sum(len(OPENER.findall(b)) for tag in ("style", "script") for b in page.bodies(tag))
    total = len(OPENER.findall(html))
    expected = len(page.bodies("style")) + len(page.bodies("script")) + inside
    if total != expected:
        out.append(f"the page contains {total} literal <style or <script openers and this gate "
                   f"accounts for {expected}; one of them is somewhere the parser did not "
                   f"report an element, such as inside <svg>, <title> or a comment, and a "
                   f"browser may well run it")
    return out


def root_blocks(headers_text):
    """Every block whose rule reaches the site root, in file order, duplicates kept.

    A rule may be a path or an absolute https URL, and Cloudflare says a request matching
    several rules inherits all of their headers, so every one of them counts. `#` is a comment:
    reading it as a path stole the headers that followed it.
    """
    out, reaches, lines = [], False, []
    for raw in headers_text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw[0].isspace():
            if reaches:
                out.append((rule, lines))
            rule, lines = raw.strip(), []
            path = urlsplit(rule).path if "://" in rule else rule
            reaches = path in ("/", "/*")
        else:
            lines.append(raw.strip())
    if reaches:
        out.append((rule, lines))
    return out


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = []
    try:
        html = normalized((root / PAGE).read_bytes())
        page = parse_page(html)
        headers_text = (root / HEADERS).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  FAIL  could not read the site files: {exc}")
        return 1

    outgrown = simple_enough(page, html)
    if outgrown:
        for why in outgrown:
            print(f"  FAIL  {why}")
        return 1

    blocks = root_blocks(headers_text)
    if not blocks:
        print(f"  FAIL  no rule in {HEADERS} reaches the site root")
        return 1

    detached = [rule for rule, lines in blocks for line in lines
                if line.lower().startswith("!") and line[1:].strip().lower() == CSP]
    if detached:
        print(f"  FAIL  {HEADERS} detaches the Content-Security-Policy at the site root "
              f"({detached[0]}), so the page is served without one at all")
        return 1

    csps = [(rule, line.split(":", 1)[1].strip()) for rule, lines in blocks for line in lines
            if line.split(":", 1)[0].strip().lower() == CSP]
    if not csps:
        print(f"  FAIL  no rule in {HEADERS} reaching the site root has a "
              f"Content-Security-Policy header")
        return 1
    if len(csps) > 1:
        where = ", ".join(rule for rule, _ in csps)
        print(f"  FAIL  {len(csps)} Content-Security-Policy headers reach the site root "
              f"({where}); a browser enforces all of them, so this gate cannot say which "
              f"governs an inline block")
        return 1
    csp = csps[0][1]

    directives = {}
    for d in csp.split(";"):
        parts = d.split()
        if parts:
            # First occurrence wins, per CSP3.
            directives.setdefault(parts[0].lower(), parts)

    pinned = 0
    for tag, names in KINDS:
        body = page.bodies(tag)[0]
        used = next((n for n in names if n in directives), None)
        if used is None:
            findings.append(
                f"the Content-Security-Policy has no {names[1]} directive, and neither "
                f"{names[0]} nor {names[2]} to fall back to")
            continue
        found = directives[used]
        if "'unsafe-inline'" in found:
            findings.append(
                f"{used} carries 'unsafe-inline', which permits any inline <{tag}> including "
                f"one injected into the page; pin the hash instead")
        h = sha256_b64(body)
        if f"'sha256-{h}'" not in found:
            findings.append(f"{used} lacks the hash of the inline <{tag}> in {PAGE} (sha256-{h})")
        else:
            pinned += 1

    for tag, line in sorted(set(page.style_attrs)):
        findings.append(
            f"<{tag}> at {PAGE}:{line} carries a style= attribute. A CSP hash covers an "
            f"element's text, never an attribute, so it needs the rule moved into the "
            f"stylesheet, or a style-src-attr directive carrying 'unsafe-hashes' and the "
            f"attribute's own hash, which this gate does not check")

    if findings:
        for f in findings:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {pinned} inline blocks in {PAGE} are pinned by hash in the {HEADERS} CSP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
