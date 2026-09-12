#!/usr/bin/env python3
"""Cases for check_csp_hashes.py, one per defect a reviewer demonstrated against it.

The gate's first version read the page with regular expressions, and its docstring said
that if those stopped being adequate it should move to a real parser rather than grow more
expressions. A reviewer demonstrated five ways they were inadequate, so it did. A second
reviewer then demonstrated four more against the parser version, and this file records both
rounds: the description of each case says which defect it holds shut.

Two kinds of case appear here, and the difference matters. Most modify the page and assert
the gate FAILS. The rest modify the page, repin the CSP to the hash the browser would
actually compute, and assert the gate PASSES; those are the ones that hold a closed defect
closed, because reintroducing the old behaviour makes the gate compute a different hash and
the case goes red. `body_hash` computes that pin independently of the gate, from the element
text, which is what a browser hashes.

One case is worth reading carefully, because writing it nearly recorded the wrong answer. A
quoted `>` inside a `<style>` attribute is a FALSE ALARM in the old version, not a miss: the
regex swallowed attribute text into the hash and rejected a page that was correct. The
parser ignores attributes, computes the pinned hash, and passes. The first draft of this
file asserted that it should fail, which would have pinned the bug in place as though it
were the fix.
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
        # Bytes, not text: the CRLF case below is only a case if the bytes survive the write.
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


def repinned(page, tag):
    """HEADERS with that element's pin replaced by what the page now hashes to."""
    return HEADERS.replace(f"'sha256-{body_hash(PAGE, tag)}'", f"'sha256-{body_hash(page, tag)}'")


EXTRA_STYLE = "</style>\n<style data-src=\"theme\">h1{color:red}</style>"
# `src` is meaningless on <style>: a browser treats this as an ordinary inline element and
# demands its hash. The gate skipped it as though it were a <script src=...>, so this block
# shipped green and the browser refused it.
SRC_STYLE = "</style>\n<style src=\"theme.css\">h1{color:red}</style>"
SVG_STYLE = "<style>circle{fill:red}</style>\n    </svg>"
# Stylesheet text that a regex comment-stripper would have deleted before hashing.
COMMENTY = "/* <!-- keep this --> */\n    :root"
# An element written inside a JavaScript string, which is a string and not an element.
STRINGY = "(function () {\n  var tpl = \"<style>h1{color:red}</style>\";"

COMMENT_PAGE = PAGE.replace(":root", COMMENTY, 1)
STRING_PAGE = PAGE.replace("(function () {", STRINGY, 1)
SCRIPT_PAGE = PAGE.replace("(function () {", "(function () {\n  /* an edit */", 1)

# (description, page, headers, must_fail, expected substring or None)
CASES = (
    ("the site as it stands", None, None, False, None),
    ("an edited stylesheet nobody repinned",
     PAGE.replace(":root", "/* an edit */\n    :root", 1), None, True, "style-src lacks the hash"),
    # Round 2: every fixture above mutates the style side, so deleting script coverage from the
    # gate entirely was caught by nothing. This is the script half of the gate's job.
    ("an edited inline script nobody repinned",
     SCRIPT_PAGE, None, True, "script-src lacks the hash"),
    ("a style= attribute, which no hash can ever cover",
     PAGE.replace("<body", '<body style="color:red"', 1), None, True, "style= attribute"),
    ("a second block whose data-src is not src",
     PAGE.replace("</style>", EXTRA_STYLE, 1), None, True, "style-src lacks the hash"),
    # Round 2: src means nothing on <style>, and skipping it shipped a block the browser refuses.
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
    # Round 2: a browser enforces every CSP header it is sent, so the strictest wins. Reading
    # the first and stopping meant a second header could forbid everything, invisibly.
    ("a second Content-Security-Policy line in the same block",
     None, HEADERS.replace("\n  Content-Security-Policy:",
                           "\n  Content-Security-Policy: default-src 'none'\n"
                           "  Content-Security-Policy:", 1),
     True, "Content-Security-Policy headers"),
    # Round 2: CRLF. read_text translated the newlines away before hashing, so a page committed
    # from a Windows checkout hashed one way here and another way in the browser, and the gate
    # stayed green over an unstyled page. Reading bytes makes it fail instead, which is right:
    # the pinned hash genuinely does not cover these bytes.
    ("a page saved with CRLF line endings",
     PAGE.replace("\n", "\r\n"), None, True, "lacks the hash"),
    # Round 2: <style> inside <svg> is foreign content, where a browser parses comments and
    # entities into nodes. html.parser treats every <style> as CDATA, so the two disagree about
    # what the hash covers. The gate must refuse rather than demand a hash no browser computes.
    ("a <style> inside the inline <svg>, which this gate cannot hash",
     PAGE.replace("</svg>", SVG_STYLE, 1), None, True, "foreign content"),
    # A FALSE ALARM in the regex version, not a miss. See the module docstring.
    ("a quoted > inside a style attribute, which changes no stylesheet text",
     PAGE.replace("<style>", '<style title="a > b">', 1), None, False, None),
    # The two below repin and assert PASS. They hold a closed round-1 defect closed: restore
    # either old behaviour and the gate computes a different hash, so the case goes red.
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

    # The two repinned cases only mean something if their repin actually moved the hash.
    for page, tag, desc in ((COMMENT_PAGE, "style", "the <!-- in stylesheet text"),
                            (STRING_PAGE, "script", "the <style> in a JavaScript string")):
        if body_hash(page, tag) == body_hash(PAGE, tag):
            failures.append(
                f"{desc} case no longer discriminates: the edit did not change the "
                f"<{tag}> hash, so the gate would pass with or without the defect restored")

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {len(CASES)} recorded cases for the CSP hash gate, across two review rounds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
