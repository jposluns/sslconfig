#!/usr/bin/env python3
"""Structural floor for guides: a Verify section with a body, and dated, cited Sources.

Deterministic and offline, like every other gate in tools/run_all_checks.sh. It is
also monotonic in time: the only date comparison it makes can turn a failing guide
into a passing one as the clock advances, never the reverse, so the passage of time
can never redden a build that was green. That is why there is no staleness cutoff
here; an expiry rule would fail the suite with no change to the repository.

WHAT THIS GATE PROVES, and it is less than the rule it supports:

  - a Verify-equivalent heading exists AND its section has a body the reader can
    actually see (an HTML comment is not a body);
  - every Sources heading that claims a "checked <Month> <Year>" date names a real
    month, is not in the future, and is followed by at least one absolute http(s)
    URL with a hostname that the reader can see;
  - at least one such Sources section exists.

WHAT IT DOES NOT PROVE, and must not be read as proving:

  - that the Verify body contains a runnable command, or any command at all;
  - that a Verify step FAILS while the service is still exposed, which is the
    property that actually matters and the one a reviewer must establish;
  - that a cited URL is reachable, vendor-owned, relevant, or that it contains the
    configuration line it is cited for;
  - that any particular configuration line is attributable to any particular source.

Those are authoring obligations under CONTRIBUTING.md "What a guide needs" rule 5,
enforced by review. This gate catches only the structural floor: a guide shipped
with no Verify section, an empty one, undated sources, or no citation at all.
"""
import datetime
import pathlib
import re
import sys

NOT_A_GUIDE = {
    "CONTRIBUTING.md",
    "CLAUDE.md",
    "AGENTS.md",
    "CHANGELOG.md",
}

# README.md is a guide for this gate's purposes: it carries a substantive
# verification checklist. Its citations live in a companion file so the front page
# stays readable, so its Sources section is resolved there instead.
README = "README.md"
README_SOURCES = "README.sources.md"

EXEMPT = {
    "common-mistakes.md": (
        "a checklist that links to the fixes rather than carrying its own "
        "Verify and Sources"
    ),
}

VERIFY_RE = re.compile(
    r"^(?:[0-9]+[.)][ \t]+)?(?:Verif\w*|Quick checks)\b",
    re.I,
)

SOURCES_RE = re.compile(
    r"^(?:[0-9]+[.)][ \t]+)?"
    r"(?:[^()]*?\b)?sources\b[ \t]*"
    r"\(checked[ \t]+([A-Za-z]+)[ \t]+([0-9]{1,4})\)",
    re.I,
)

URL_RE = re.compile(
    # Scheme is case insensitive (RFC 3986). Every DNS label must be non-empty, so
    # "https://a..b.com" is not a citation, and a port must be one that can exist.
    r"https?://"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,}"
    r"(?::(?:6553[0-5]|655[0-2]\d|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]\d{4}|[1-9]\d{0,3}))?"
    r"(?:[/?#]\S*)?",
    re.I,
)

# CommonMark HTML block type 6: Markdown inside one of these is NOT parsed as
# Markdown, so a "## heading" there is literal text, never a section boundary.
HTML_BLOCK_TAGS = (
    "address|article|aside|base|basefont|blockquote|body|caption|center|col|"
    "colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|"
    "form|frame|frameset|h1|h2|h3|h4|h5|h6|head|header|hr|html|iframe|legend|li|"
    "link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|"
    "section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul"
)
HTML_BLOCK_RE = re.compile(
    r"^[ ]{0,3}</?(?:" + HTML_BLOCK_TAGS + r")(?:[ \t>]|/>|$)", re.I
)

# A Markdown link whose target is the companion file, so a bare prose mention of the
# filename, or a link buried in an HTML comment, does not satisfy the requirement
# that the reader has a path from the checklist to its citations.
README_SOURCES_LINK_RE = re.compile(
    r"\]\([ \t]*(?:\./)?" + re.escape(README_SOURCES) + r"(?:#[^)]*)?[ \t]*\)"
)

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

FENCE_RE = re.compile(r"^(?P<indent>[ ]{0,3})(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
ATX_RE = re.compile(
    # CommonMark permits an empty ATX heading ("##"), which still opens a section.
    r"^[ ]{0,3}(?P<hashes>#{1,6})(?:[ \t]+(?P<text>.*?))??(?:[ \t]+#+)?[ \t]*$"
)
SETEXT_RE = re.compile(r"^[ ]{0,3}(?P<rule>=+|-+)[ \t]*$")


def _strip_comments(line, in_comment):
    """Remove HTML comments from one line, respecting inline code spans.

    A literal "<!--" shown inside backticks is content a reader sees, not a comment
    opener, so it must not blind the scanner to everything that follows. Returns the
    cleaned text and whether a comment is still open at end of line.
    """
    out = []
    i = 0
    span = 0  # length of the backtick run that opened the current inline code span

    while i < len(line):
        if in_comment:
            end = line.find("-->", i)
            if end == -1:
                return "".join(out), True
            i = end + 3
            in_comment = False
            continue

        if line[i] == "`":
            run = len(line) - len(line[i:].lstrip("`"))
            if span == 0:
                span = run
            elif run == span:
                span = 0
            out.append(line[i:i + run])
            i += run
            continue

        if span == 0 and line.startswith("<!--", i):
            end = line.find("-->", i + 4)
            if end == -1:
                return "".join(out), True
            i = end + 3
            continue

        out.append(line[i])
        i += 1

    return "".join(out), False


def scan(text):
    """Per-line views of a document.

    Returns (content, visible):
      content[i] - the line with HTML comments removed, code fences PRESERVED. This
                   is what a reader sees, so it is what section bodies are measured
                   and searched against.
      visible    - {index: text} for lines that are prose outside any fence. Only
                   these can be headings, so a '## heading' printed inside a code
                   block can never open or close a section.
    """
    lines = text.splitlines()
    content = [""] * len(lines)
    visible = {}

    fence = None
    in_comment = False
    in_html_block = False

    for i, raw in enumerate(lines):
        if fence is not None:
            content[i] = raw
            m = FENCE_RE.match(raw)
            if (m and m.group("marker")[0] == fence[0]
                    and len(m.group("marker")) >= fence[1]
                    and not m.group("info").strip()):
                fence = None
            continue

        if in_html_block:
            # A CommonMark type 6 HTML block runs to the next blank line, and its
            # contents are raw HTML: a "## heading" inside it is literal text a
            # reader sees, never a Markdown section boundary.
            content[i] = raw
            if not raw.strip():
                in_html_block = False
            continue

        if in_comment:
            cleaned, in_comment = _strip_comments(raw, True)
            content[i] = cleaned
            continue

        m = FENCE_RE.match(raw)
        if m and not (m.group("marker")[0] == "`" and "`" in m.group("info")):
            # CommonMark forbids a backtick in a backtick fence's info string, so
            # such a line is an ordinary paragraph rather than a fence opener.
            fence = (m.group("marker")[0], len(m.group("marker")))
            content[i] = raw
            continue

        opens_comment = raw.lstrip(" ").startswith("<!--")
        cleaned, in_comment = _strip_comments(raw, False)
        content[i] = cleaned

        if HTML_BLOCK_RE.match(raw):
            in_html_block = bool(raw.strip())
            continue

        if opens_comment:
            # The line is an HTML comment block, so whatever survives comment
            # removal is literal text on that line, not a Markdown heading.
            continue

        visible[i] = cleaned

    return content, visible


def headings(text):
    """(index, level, title, body_start) for ATX and setext headings.

    body_start is the first line BELOW the heading: one past an ATX heading, two past
    a setext one, so the ==== underline is never counted as section content.
    """
    _, visible = scan(text)
    found = []

    for i in sorted(visible):
        line = visible[i]

        m = ATX_RE.match(line)
        if m:
            title = (m.group("text") or "").strip()
            found.append((i, len(m.group("hashes")), title, i + 1))
            continue

        # Setext: the underline must be the IMMEDIATELY FOLLOWING physical line and
        # must itself be visible. Using the next *visible* line would let a fenced
        # block sit between a paragraph and a thematic break, turning that paragraph
        # into a phantom heading.
        nxt = visible.get(i + 1)
        if nxt is None or not line.strip():
            continue
        sm = SETEXT_RE.match(nxt)
        if sm and not ATX_RE.match(line):
            level = 1 if sm.group("rule").startswith("=") else 2
            found.append((i, level, line.strip(), i + 2))

    return found


def section_body(text, heads, body_start, heading_level):
    """Reader-visible lines of a section, up to the next heading of equal or higher rank."""
    content, _ = scan(text)
    end = None
    for i, level, _title, _bs in heads:
        if i >= body_start and level <= heading_level:
            end = i
            break
    return "\n".join(content[body_start:end])


def find_verify(name, text):
    heads = headings(text)
    for i, level, title, body_start in heads:
        if VERIFY_RE.match(title):
            if not section_body(text, heads, body_start, level).strip():
                return [
                    f"{name}: the Verify section '{title}' has no body a reader can "
                    f"see. A heading alone, or a heading over only an HTML comment, "
                    f"gives the reader nothing to run."
                ]
            return []
    return [
        f"{name}: no Verify section. Every guide owes the reader checks it can run; "
        f"expected a 'Verify', 'Verification' or 'Quick checks' heading."
    ]


def find_sources(name, text, today, origin=None):
    """Every dated Sources section must be well formed, and at least one must exist.

    Strict rather than existential on purpose: a heading that matches SOURCES_RE is
    CLAIMING to be a dated citation list, so a malformed one is a broken compliance
    marker even when a valid section exists elsewhere in the file. Tolerating it
    would let a date typo survive behind an older good block.
    """
    where = f"{name} (via {origin})" if origin else name
    heads = headings(text)
    candidates = [
        (i, level, title, body_start, SOURCES_RE.match(title))
        for i, level, title, body_start in heads
    ]
    candidates = [c for c in candidates if c[4]]

    if not candidates:
        return [
            f"{where}: no dated Sources heading. Expected "
            f"'## Sources (checked <Month> <Year>)' so a reader can tell how stale "
            f"the citations are."
        ]

    problems = []
    for i, level, title, body_start, match in candidates:
        month_name, year_text = match.group(1).lower(), match.group(2)

        if month_name not in MONTHS:
            problems.append(
                f"{where}: Sources heading '{title}' says checked "
                f"'{match.group(1)} {year_text}', and '{match.group(1)}' is not a "
                f"month name."
            )
            continue

        try:
            checked = datetime.date(int(year_text), MONTHS.index(month_name) + 1, 1)
        except ValueError:
            problems.append(
                f"{where}: Sources heading '{title}' says checked "
                f"'{match.group(1)} {year_text}', which is not a usable date."
            )
            continue

        if checked > today.replace(day=1):
            problems.append(
                f"{where}: Sources heading '{title}' says checked "
                f"{month_name.title()} {int(year_text)}, which is in the future."
            )
            continue

        if not URL_RE.search(section_body(text, heads, body_start, level)):
            problems.append(
                f"{where}: the Sources section '{title}' cites no absolute http(s) "
                f"URL with a hostname that a reader can see."
            )

    return problems


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    today = datetime.date.today()

    failures = []
    checked_count = 0

    for path in sorted(root.glob("*.md")):
        name = path.name
        if name in NOT_A_GUIDE or name in EXEMPT or name == README_SOURCES:
            continue

        text = path.read_text(encoding="utf-8")
        checked_count += 1

        failures.extend(find_verify(name, text))

        if name == README:
            companion = root / README_SOURCES
            if not companion.is_file():
                failures.append(
                    f"{name}: its citations live in {README_SOURCES}, which is missing."
                )
                continue
            failures.extend(
                find_sources(
                    name, companion.read_text(encoding="utf-8"), today,
                    origin=README_SOURCES,
                )
            )
            readme_content, _ = scan(text)
            if not README_SOURCES_LINK_RE.search("\n".join(readme_content)):
                failures.append(
                    f"{name}: has no Markdown link to {README_SOURCES}, so a reader "
                    f"has no path from the checklist to its citations."
                )
        else:
            failures.extend(find_sources(name, text, today))

    if not checked_count:
        print("  FAIL  guide-shape gate found no guides to check; run it from the "
              "repository root")
        return 1

    for line in failures:
        print(f"  FAIL  {line}")

    if failures:
        return 1

    print(f"  ok    all {checked_count} guides carry a Verify section with a visible "
          f"body and dated, cited Sources ({len(EXEMPT)} documented exemption"
          f"{'' if len(EXEMPT) == 1 else 's'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
