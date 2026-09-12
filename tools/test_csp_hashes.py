#!/usr/bin/env python3
"""Cases for check_csp_hashes.py, one per defect a reviewer demonstrated against it.

The gate's first version read the page with regular expressions, and its docstring said
that if those stopped being adequate it should move to a real parser rather than grow more
expressions. A reviewer then demonstrated six ways they were inadequate, so it did. Every
case below is one of those, run against the real gate with a modified copy of the page.

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
PAGE = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
HEADERS = (ROOT / "site" / "_headers").read_text(encoding="utf-8")


def run_against(page=None, headers=None):
    """Run the real gate against a copy of the site. Returns (exit, first output line)."""
    d = Path(tempfile.mkdtemp())
    try:
        (d / "tools").mkdir()
        (d / "site").mkdir()
        shutil.copy(TOOLS / "check_csp_hashes.py", d / "tools" / "check_csp_hashes.py")
        (d / "site" / "index.html").write_text(page if page is not None else PAGE, encoding="utf-8")
        (d / "site" / "_headers").write_text(
            headers if headers is not None else HEADERS, encoding="utf-8")
        r = subprocess.run([sys.executable, "tools/check_csp_hashes.py"], cwd=d,
                           capture_output=True, text=True)
        out = r.stdout.strip().splitlines()
        return r.returncode, (out[0] if out else "")
    finally:
        shutil.rmtree(d, ignore_errors=True)


EXTRA_STYLE = "</style>\n<style data-src=\"theme\">h1{color:red}</style>"

# (description, page, headers, must_fail, expected substring or None)
CASES = (
    ("the site as it stands", None, None, False, None),
    ("an edited stylesheet nobody repinned",
     PAGE.replace(":root", "/* an edit */\n    :root", 1), None, True, "style-src lacks the hash"),
    ("a style= attribute, which no hash can ever cover",
     PAGE.replace("<body", '<body style="color:red"', 1), None, True, "style= attribute"),
    ("a second block whose data-src is not src",
     PAGE.replace("</style>", EXTRA_STYLE, 1), None, True, "style-src lacks the hash"),
    ("an uppercase STYLE block",
     PAGE.replace("</style>", "</style>\n<STYLE>h1{color:red}</STYLE>", 1), None, True,
     "style-src lacks the hash"),
    ("style-src renamed to the different directive style-src-attr",
     None, HEADERS.replace("style-src ", "style-src-attr ", 1), True, "no style-src directive"),
    ("'unsafe-inline' coming back",
     None, re.sub(r"style-src '[^']*'", "style-src 'unsafe-inline'", HEADERS, count=1), True,
     "'unsafe-inline'"),
    # A FALSE ALARM in the regex version, not a miss. See the module docstring.
    ("a quoted > inside a style attribute, which changes no stylesheet text",
     PAGE.replace("<style>", '<style title="a > b">', 1), None, False, None),
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

    if failures:
        for f in failures:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {len(CASES)} recorded cases for the CSP hash gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
