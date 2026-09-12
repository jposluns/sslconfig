#!/usr/bin/env python3
"""Cases for check_csp_hashes.py, one per defect a reviewer demonstrated against it.

Three rounds are recorded here. Round 1 broke a regular-expression reader, and the gate moved
to `html.parser`. Round 2 found four defects in that parser version. Round 3 found that one of
the round-2 FIXES was backwards and that the test written for it was holding the wrong answer
in place, which is the most useful thing any round has produced.

That case is the CRLF pair below, and it is worth reading before the rest. HTML's input-stream
preprocessing normalizes CR and CRLF to LF before tokenizing, so a browser's DOM never
contains a CR and its CSP hash covers the normalized text. Round 2 read that backwards, made
the gate hash raw bytes, and recorded a case asserting that a CRLF page must FAIL against the
unchanged CSP. A CRLF page against the unchanged CSP works perfectly in a browser. The case
did not merely miss the defect; it killed the mutant that would have fixed it. Both directions
are now recorded: a CRLF page with the real pins must PASS, and a CRLF page with pins computed
from the CRLF bytes must FAIL.

Two kinds of case appear here. Most modify the page and assert the gate FAILS. The rest modify
the page, repin the CSP to the hash the browser would actually compute, and assert the gate
PASSES; those hold a closed defect closed, because reintroducing the old behaviour makes the
gate compute a different hash and the case goes red. `body_hash` computes that pin
independently of the gate, from the element text, which is what a browser hashes.

One round-1 case nearly recorded the wrong answer too. A quoted `>` inside a `<style>`
attribute is a FALSE ALARM in the regex version, not a miss: the regex swallowed attribute
text into the hash and rejected a page that was correct. The first draft asserted it should
fail, which would have pinned the bug in place as though it were the fix. Twice now.
"""
import base64
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
PAGE = (ROOT / "site" / "index.html").read_bytes().decode("utf-8")
HEADERS = (ROOT / "site" / "_headers").read_text(encoding="utf-8")


def run_against(page=None, headers=None):
    """Run the real gate against a copy of the site. Returns (exit, first output line)."""
    d = Path(tempfile.mkdtemp())
    try:
        (d / "tools").mkdir()
        (d / "site").mkdir()
        shutil.copy(TOOLS / "check_csp_hashes.py", d / "tools" / "check_csp_hashes.py")
        # Bytes, not text: the CRLF cases are only cases if the bytes survive the write.
        (d / "site" / "index.html").write_bytes(
            (page if page is not None else PAGE).encode("utf-8"))
        (d / "site" / "_headers").write_text(
            headers if headers is not None else HEADERS, encoding="utf-8")
        r = subprocess.run([sys.executable, "tools/check_csp_hashes.py"], cwd=d,
                           capture_output=True, text=True)
        out = r.stdout.strip().splitlines()
        return r.returncode, (out[0] if out else "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def body_hash(page, tag):
    """sha256 of an element's text, computed here rather than asked of the gate."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", page, re.S)
    return base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode()


def repinned(page, tag, headers=None):
    """HEADERS with that element's pin replaced by what the page now hashes to."""
    base = HEADERS if headers is None else headers
    return base.replace(f"'sha256-{body_hash(PAGE, tag)}'", f"'sha256-{body_hash(page, tag)}'")


EXTRA_STYLE = "</style>\n<style data-src=\"theme\">h1{color:red}</style>"
SRC_STYLE = "</style>\n<style src=\"theme.css\">h1{color:red}</style>"
SVG_STYLE = "<style>circle{fill:red}</style>\n    </svg>"
MATH_STYLE = "</style>\n<math><style>m{color:red}</style></math>"
FOREIGNOBJ = "</style>\n<svg><foreignObject><style>p{color:red}</style></foreignObject></svg>"
INERT_SCRIPT = "</style>\n<script type=\"text/template\"><b>{{x}}</b></script>"
INERT_STYLE = "</style>\n<style type=\"text/plain\">h1{color:red}</style>"
COMMENTY = "/* <!-- keep this --> */\n    :root"
STRINGY = "(function () {\n  var tpl = \"<style>h1{color:red}</style>\";"

COMMENT_PAGE = PAGE.replace(":root", COMMENTY, 1)
STRING_PAGE = PAGE.replace("(function () {", STRINGY, 1)
SCRIPT_PAGE = PAGE.replace("(function () {", "(function () {\n  /* an edit */", 1)
CRLF_PAGE = PAGE.replace("\n", "\r\n")
# The pins a browser would never compute: sha256 over the CRLF bytes, which is what the
# round-2 version of this gate demanded.
CRLF_PINS = HEADERS.replace(
    f"'sha256-{body_hash(PAGE, 'style')}'", f"'sha256-{body_hash(CRLF_PAGE, 'style')}'").replace(
    f"'sha256-{body_hash(PAGE, 'script')}'", f"'sha256-{body_hash(CRLF_PAGE, 'script')}'")

# (description, page, headers, must_fail, expected substring or None)
CASES = (
    ("the site as it stands", None, None, False, None),
    ("an edited stylesheet nobody repinned",
     PAGE.replace(":root", "/* an edit */\n    :root", 1), None, True, "style-src lacks the hash"),
    ("an edited inline script nobody repinned",
     SCRIPT_PAGE, None, True, "script-src lacks the hash"),
    ("a style= attribute, which no hash can ever cover",
     PAGE.replace("<body", '<body style="color:red"', 1), None, True, "style= attribute"),
    ("a second block whose data-src is not src",
     PAGE.replace("</style>", EXTRA_STYLE, 1), None, True, "style-src lacks the hash"),
    ("a <style src=>, which a browser still treats as inline",
     PAGE.replace("</style>", SRC_STYLE, 1), None, True, "style-src lacks the hash"),
    ("an uppercase STYLE block",
     PAGE.replace("</style>", "</style>\n<STYLE>h1{color:red}</STYLE>", 1), None, True,
     "style-src lacks the hash"),
    ("style-src renamed to the different directive style-src-attr",
     None, HEADERS.replace("style-src ", "style-src-attr ", 1), True, "no style-src directive"),
    ("'unsafe-inline' coming back",
     None, re.sub(r"style-src '[^']*'", "style-src 'unsafe-inline'", HEADERS, count=1), True,
     "'unsafe-inline'"),

    # ROUND 3. A browser checks an inline element against the -elem directive first and falls
    # back to the plain one only when -elem is absent. Reading only the plain one left the gate
    # green over a page the browser refuses outright.
    ("script-src-elem 'none' added beside a correct script-src",
     None, HEADERS.replace("; img-src", "; script-src-elem 'none'; img-src", 1), True,
     "script-src-elem lacks the hash"),
    ("style-src-elem carrying the correct hash is what gets used",
     None, HEADERS.replace("; img-src",
                           f"; style-src-elem 'sha256-{body_hash(PAGE, 'style')}'; img-src", 1),
     False, None),

    # ROUND 3. Every block matching the site root reaches the browser. Reading one of them,
    # and letting a dict overwrite a duplicate path, both hid a hostile policy.
    ("a hostile CSP in a separate / block beside the checked /* block",
     None, "/\n  Content-Security-Policy: default-src 'none'\n\n" + HEADERS, True,
     "Content-Security-Policy headers reach the site root"),
    ("two /* blocks, the hostile policy in the first",
     None, "/*\n  Content-Security-Policy: default-src 'none'\n\n" + HEADERS, True,
     "Content-Security-Policy headers reach the site root"),

    # ROUND 3. Foreign content and its integration points, each checked against html5lib.
    ("a <style> inside the inline <svg>, which this gate will not hash",
     PAGE.replace("</svg>", SVG_STYLE, 1), None, True, "foreign content"),
    ("a <style> inside <math>, the unhandled sibling of <svg>",
     PAGE.replace("</style>", MATH_STYLE, 1), None, True, "foreign content"),
    # foreignObject returns to HTML parsing, so this IS a stylesheet and DOES need a hash.
    # The round-2 gate refused it, which was a false alarm on a block the browser applies.
    ("a <style> inside <svg><foreignObject>, which is HTML again",
     PAGE.replace("</style>", FOREIGNOBJ, 1), None, True, "style-src lacks the hash"),

    # ROUND 3. A browser never runs these, so it never hashes them, so neither does this.
    ("a <script> with a type no browser executes",
     PAGE.replace("</style>", INERT_SCRIPT, 1), None, True, "never runs or applies"),
    ("a <style> with a type no browser applies",
     PAGE.replace("</style>", INERT_STYLE, 1), None, True, "never runs or applies"),

    # ROUND 3. The CRLF pair. See the module docstring: round 2 recorded this backwards.
    ("a CRLF page against the real pins, which a browser renders correctly",
     CRLF_PAGE, None, False, None),
    ("a CRLF page pinned to the hash of its CRLF bytes, which no browser computes",
     CRLF_PAGE, CRLF_PINS, True, "lacks the hash"),

    # ROUND 3. Branches no case exercised, each of which a mutant survived in.
    ("no block matching / or /* at all",
     None, HEADERS.replace("/*", "/assets/*", 1), True, "no path block"),
    ("a block with no Content-Security-Policy line",
     None, re.sub(r"^  Content-Security-Policy:.*$", "  X-Other: 1", HEADERS, count=1,
                  flags=re.M), True, "has a Content-Security-Policy"),
    ("the style hash pinned under script-src instead of style-src",
     None, HEADERS.replace(f"style-src 'sha256-{body_hash(PAGE, 'style')}'", "style-src 'none'", 1)
     .replace("script-src 'sha256-", f"script-src 'sha256-{body_hash(PAGE, 'style')}' 'sha256-", 1),
     True, "style-src lacks the hash"),

    # A FALSE ALARM in the regex version, not a miss. See the module docstring.
    ("a quoted > inside a style attribute, which changes no stylesheet text",
     PAGE.replace("<style>", '<style title="a > b">', 1), None, False, None),
    # These two repin and assert PASS, holding a closed round-1 defect closed.
    ("stylesheet text containing <!-- and -->, which is text and not a comment node",
     COMMENT_PAGE, repinned(COMMENT_PAGE, "style"), False, None),
    ("a <style> written inside a JavaScript string, which is a string",
     STRING_PAGE, repinned(STRING_PAGE, "script"), False, None),
)


def main() -> int:
    failures = []
    for desc, page, headers, must_fail, expected in CASES:
        rc, out = run_against(page, headers)
        if bool(rc) != must_fail:
            want = "fail" if must_fail else "pass"
            failures.append(f"{desc}: expected the gate to {want}, it did not ({out})")
        elif expected is not None and expected not in out:
            failures.append(
                f"{desc}: the gate's exit status was right but its message was not. "
                f"Expected it to contain {expected!r}. It said: {out!r}")

    # The quoted-attribute case only means something if the old approach really failed it.
    page = PAGE.replace("<style>", '<style title="a > b">', 1)
    m = re.search(r"<style(\s[^>]*)?>(.*?)</style>", page, re.S)
    regex_hash = base64.b64encode(hashlib.sha256(m.group(2).encode()).digest()).decode()
    if f"'sha256-{regex_hash}'" in HEADERS:
        failures.append(
            "the quoted-attribute case no longer discriminates: the regex approach now "
            "computes the pinned hash, so it records nothing")

    # The repinned cases only mean something if their repin actually moved the hash.
    for page, tag, desc in ((COMMENT_PAGE, "style", "the <!-- in stylesheet text"),
                            (STRING_PAGE, "script", "the <style> in a JavaScript string"),
                            (CRLF_PAGE, "style", "the CRLF")):
        if body_hash(page, tag) == body_hash(PAGE, tag):
            failures.append(
                f"{desc} case no longer discriminates: the edit did not change the raw "
                f"<{tag}> text, so the gate would answer the same with the defect restored")

    # A finding has to name the line a reader can go to. No case asserted one, and a reviewer
    # mutated the reported line number without anything noticing.
    rc, out = run_against(PAGE.replace("<body", '<body style="color:red"', 1))
    want = PAGE[:PAGE.index("<body")].count("\n") + 1
    if f"site/index.html:{want}" not in out:
        failures.append(
            f"the style= finding does not name the right line: <body> is on line {want}. "
            f"It said: {out!r}")

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {len(CASES)} recorded cases for the CSP hash gate, across three review "
          f"rounds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
