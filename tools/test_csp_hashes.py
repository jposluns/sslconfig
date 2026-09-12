#!/usr/bin/env python3
"""Cases for check_csp_hashes.py, one per defect a reviewer demonstrated against it.

Five rounds are recorded, and the arc matters more than any single case. Round 1 broke a
regular-expression reader and the gate moved to `html.parser`. Rounds 2, 3 and 4 then spent
themselves teaching that parser about HTML: `src` on a style, foreign content, integration
points, MathML, inert script types. Round 3 found that a round-2 fix was BACKWARDS and that the
case written for it was holding the wrong answer in place. Round 4 found two more silent
fail-opens in the same family, a `<style>` inside `<svg><title>` that `html.parser` swallows
entirely and a `<script>` whose escape states it misreads. Round 5 found three wrong pages that
satisfied every one of the new guards, the worst of which had this gate printing the hash of the
EMPTY STRING in its own failure message and going green once an author pinned what it asked for.

So the gate stopped modelling HTML and started refusing what it cannot model, and most of the
cases below are now assertions that it refuses. Several of them USED to be passes, and each
says so, because a case that quietly changes direction is how round 2's regression survived.

Two kinds of case appear here. Most modify the page and assert the gate FAILS. The rest modify
the page, repin the CSP to the hash a browser would actually compute, and assert it PASSES;
those hold a closed defect closed, because reintroducing the old behaviour moves the computed
hash and the case goes red. `body_hash` computes that pin independently of the gate.
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
        # Bytes, not text: the newline cases are only cases if the bytes survive the write.
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


def alt_pin(page, tag, fn):
    """The same element text under another CSP-permitted hash algorithm."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", page, re.S)
    return base64.b64encode(fn(m.group(1).encode("utf-8")).digest()).decode()


STYLE_PIN = f"'sha256-{body_hash(PAGE, 'style')}'"
SCRIPT_PIN = f"'sha256-{body_hash(PAGE, 'script')}'"

COMMENTY = "/* <!-- keep this --> */\n    :root"
STRINGY = "(function () {\n  var tpl = \"<style>h1{color:red}</style>\";"
COMMENT_PAGE = PAGE.replace(":root", COMMENTY, 1)
STRING_PAGE = PAGE.replace("(function () {", STRINGY, 1)
SCRIPT_PAGE = PAGE.replace("(function () {", "(function () {\n  /* an edit */", 1)
CRLF_PAGE = PAGE.replace("\n", "\r\n")
CR_PAGE = PAGE.replace("\n", "\r")
CRLF_PINS = HEADERS.replace(STYLE_PIN, f"'sha256-{body_hash(CRLF_PAGE, 'style')}'").replace(
    SCRIPT_PIN, f"'sha256-{body_hash(CRLF_PAGE, 'script')}'")

# (description, page, headers, must_fail, expected substring or None)
CASES = (
    ("the site as it stands", None, None, False, None),
    ("an edited stylesheet nobody repinned",
     PAGE.replace(":root", "/* an edit */\n    :root", 1), None, True, "lacks the hash"),
    ("an edited inline script nobody repinned", SCRIPT_PAGE, None, True, "lacks the hash"),
    ("a style= attribute, which no hash can ever cover",
     PAGE.replace("<body", '<body style="color:red"', 1), None, True, "style= attribute"),
    ("'unsafe-inline' coming back",
     None, re.sub(r"style-src '[^']*'", "style-src 'unsafe-inline'", HEADERS, count=1), True,
     "'unsafe-inline'"),

    # THE PAGE OUTGROWING THE GATE. Each of these used to be modelled, mostly wrongly.
    ("a second inline block, which this gate no longer tries to tell apart",
     PAGE.replace("</style>", "</style>\n<style>h1{color:red}</style>", 1), None, True,
     "models exactly one"),
    ("a <style src=>, once skipped as external and once hashed",
     PAGE.replace("</style>", "</style>\n<style src=\"theme.css\">h1{color:red}</style>", 1),
     None, True, "models exactly one"),
    ("an attribute on the hashed block, where a browser's rules decide whether it runs",
     PAGE.replace("<style>", '<style title="a > b">', 1), None, True, "carries attributes"),
    ("a <script> with a type, which used to be judged live or inert here",
     PAGE.replace("<script>", '<script type="module">', 1), None, True, "carries attributes"),
    # ROUND 4, and a silent fail-open before this: html.parser treats <title> as RCDATA, so the
    # <style> inside <svg><title> produces no start tag at all. It is an HTML-namespace style
    # element in a browser, applied and CSP-checked, and the gate reported nothing.
    ("a <style> inside <svg><title>, which html.parser never reports",
     PAGE.replace("</svg>", "<title><style>p{color:red}</style></title>\n    </svg>", 1), None,
     True, "openers"),
    ("a <style> inside the inline <svg>",
     PAGE.replace("</svg>", "<style>circle{fill:red}</style>\n    </svg>", 1), None, True,
     "models exactly one"),
    ("a <style> inside <math>",
     PAGE.replace("</style>", "</style>\n<math><style>m{color:red}</style></math>", 1), None,
     True, "models exactly one"),
    # ROUND 4: html.parser stops at the first </script>, a browser does not.
    ("a <script> containing <!--, which opens HTML's script-data escape states",
     PAGE.replace("(function () {", "// <!--<script>x</script>-->\n(function () {", 1), None,
     True, "escape states"),
    ("a NUL byte, which a browser replaces with U+FFFD before hashing",
     PAGE.replace(":root", "\x00:root", 1), None, True, "NUL byte"),

    # DIRECTIVE RESOLUTION, per CSP3's fallback chain.
    ("script-src-elem 'none' added beside a correct script-src",
     None, HEADERS.replace("; img-src", "; script-src-elem 'none'; img-src", 1), True,
     "script-src-elem lacks the hash"),
    ("style-src-elem carrying the correct hash is what gets used",
     None, HEADERS.replace("; img-src", f"; style-src-elem {STYLE_PIN}; img-src", 1),
     False, None),
    ("style-src-elem 'none' added beside a correct style-src",
     None, HEADERS.replace("; img-src", "; style-src-elem 'none'; img-src", 1), True,
     "style-src-elem lacks the hash"),
    # ROUND 4: default-src is the last fallback, and failing a page it governs was a false alarm.
    ("default-src carrying both hashes, with no script-src or style-src",
     None, HEADERS.replace(
         f"default-src 'none'; script-src {SCRIPT_PIN}; style-src {STYLE_PIN}",
         f"default-src {SCRIPT_PIN} {STYLE_PIN}", 1), False, None),
    ("a directive repeated, the first one hostile, which is the one a browser takes",
     None, HEADERS.replace("style-src ", "style-src 'none'; style-src ", 1), True,
     "style-src lacks the hash"),
    ("a directive name in mixed case, which CSP3 matches case-insensitively",
     None, HEADERS.replace("style-src ", "Style-Src ", 1), False, None),
    ("the style hash pinned under script-src instead of style-src",
     None, HEADERS.replace(f"style-src {STYLE_PIN}", "style-src 'none'", 1)
     .replace("script-src 'sha256-", f"script-src {STYLE_PIN} 'sha256-", 1),
     True, "style-src lacks the hash"),

    # THE HEADERS FILE, whose syntax is Cloudflare's and does more than this once assumed.
    # ROUND 4: a detach line has no colon, so it was invisible, and it removes the policy.
    ("a later rule detaching the Content-Security-Policy entirely",
     None, HEADERS + "\n/*\n  ! Content-Security-Policy\n", True, "detaches"),
    # ROUND 4: an absolute https rule reaches the root as surely as /* does.
    ("a hostile CSP in a host-scoped rule, which also reaches the root",
     None, HEADERS + "\nhttps://secureconfig.example/*\n  Content-Security-Policy: style-src 'none'\n",
     True, "reach the site root"),
    # ROUND 4: `#` is a comment, and reading it as a path stole the headers under it.
    ("a comment between a rule and its headers, which is valid in _headers",
     None, HEADERS.replace("/*\n", "/*\n# the policy below is pinned by tools/check_csp_hashes.py\n", 1),
     False, None),
    ("a hostile CSP in a separate / block beside the checked /* block",
     None, "/\n  Content-Security-Policy: default-src 'none'\n\n" + HEADERS, True,
     "reach the site root"),
    ("two /* blocks, the hostile policy in the first",
     None, "/*\n  Content-Security-Policy: default-src 'none'\n\n" + HEADERS, True,
     "reach the site root"),
    ("no rule reaching the root at all",
     None, HEADERS.replace("/*", "/assets/*", 1), True, "reaches the site root"),
    ("a root rule with no Content-Security-Policy line",
     None, re.sub(r"^  Content-Security-Policy:.*$", "  X-Other: 1", HEADERS, count=1,
                  flags=re.M), True, "Content-Security-Policy header"),

    # NEWLINES. Round 2 recorded this backwards and the case killed the mutant that fixed it.
    ("a CRLF page against the real pins, which a browser renders correctly",
     CRLF_PAGE, None, False, None),
    ("a CRLF page pinned to the hash of its CRLF bytes, which no browser computes",
     CRLF_PAGE, CRLF_PINS, True, "lacks the hash"),
    ("a lone-CR page against the real pins, normalized the same way",
     CR_PAGE, None, False, None),

    # ROUND 5. Three wrong pages that passed every guard, each verified against html5lib and
    # Gumbo. The first is the worst thing this gate has done: it handed the author the hash of
    # the EMPTY STRING and went green once that was pinned, while a browser refused the whole
    # stylesheet. html.parser routes `<style/>` to handle_startendtag and never enters CDATA.
    ("a self-closing <style/>, which html.parser reads as empty and a browser does not",
     PAGE.replace("<style>", "<style/>", 1), None, True, "self-closing"),
    ("a charset declaration this gate does not obey",
     PAGE.replace('<meta charset="utf-8">', '<meta charset="windows-1252">', 1), None, True,
     "charset"),
    # The round-4 RCDATA blind spot, still open for ATTRIBUTES: <title> content is swallowed,
    # so the parser never reported the style= and a browser applies it.
    ("a style= attribute smuggled through <svg><title>",
     PAGE.replace("</svg>", '<title>t<div style="display:none">x</div></title>\n    </svg>', 1),
     None, True, "style="),
    # A CSP value is a comma-separated LIST of policies and a browser enforces all of them.
    ("a comma splitting the CSP into two policies, the first hostile",
     None, HEADERS.replace("style-src ", "style-src 'none', style-src ", 1), True, "comma"),
    # Kills the mutant that drops re.I from the opener expression: both browser parsers report
    # this as a live style element.
    ("an uppercase <STYLE> smuggled through <svg><title>",
     PAGE.replace("</svg>", "<title>t<STYLE>p{color:red}</STYLE></title>\n    </svg>", 1),
     None, True, "openers"),
    ("a CSP with no style-src, style-src-elem or default-src at all",
     None, re.sub(r"Content-Security-Policy: .*$", "Content-Security-Policy: img-src 'self'",
                  HEADERS, count=1, flags=re.M), True, "no script-src directive"),
    # Kills the mutant that matches a pin as a substring: a browser ignores an invalid source
    # expression, so the style is blocked.
    ("the correct hash embedded in a longer, invalid token",
     None, HEADERS.replace(STYLE_PIN, STYLE_PIN[:-1] + "x'", 1), True, "lacks the hash"),
    # Kills the mutant that only checks 'unsafe-inline' on the style directive.
    ("'unsafe-inline' on script-src beside the correct pin",
     None, HEADERS.replace("script-src ", "script-src 'unsafe-inline' ", 1), True,
     "'unsafe-inline'"),
    # CSP3 matches the algorithm name case-insensitively, and sha384 is as valid as sha256.
    ("a pin whose algorithm name is upper case, which CSP3 accepts",
     None, HEADERS.replace(STYLE_PIN, STYLE_PIN.replace("sha256", "SHA256"), 1), False, None),
    ("a sha384 pin, which is stronger and equally valid",
     None, HEADERS.replace(STYLE_PIN, f"'sha384-{alt_pin(PAGE, 'style', hashlib.sha384)}'", 1),
     False, None),

    # REPINNED, ASSERTING A PASS. These hold a closed round-1 defect closed.
    ("stylesheet text containing <!-- and -->, which is text and not a comment node",
     COMMENT_PAGE, repinned(COMMENT_PAGE, "style"), False, None),
    ("a <style> written inside a JavaScript string, which is a string and not an element",
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
    print(f"  ok    {len(CASES)} recorded cases for the CSP hash gate, across five review "
          f"rounds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
