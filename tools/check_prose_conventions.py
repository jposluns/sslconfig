#!/usr/bin/env python3
"""Fail on British -ise spellings in prose, and on placeholders outside the house set.

WHAT THIS PROVES: two conventions this repository states and did not enforce.

Spelling. CONTRIBUTING rule 2 and the project's writing standard settle on Oxford English
with -ize. That CONTRIBUTING sentence was added when this gate was, because a reviewer
pointed out that the gate cited a rule its source did not state, which is the same defect
class the gate exists to catch. A corpus-wide conversion missed `randomised`, because the
word list used for that conversion was itself incomplete, and the same word was then
written into a new guide hours later. A word list in a gate is checked by the gate; a
word list in someone's head is not.

Placeholders. CONTRIBUTING rule 2 fixes the placeholder set: example.com and its
subdomains, hosts under .internal, loopback, and RFC 1918 addresses. `yourdomain.com` is
a real registered domain and reached the corpus anyway.

QUOTED TEXT IS EXEMPT FROM THE SPELLING CHECK ONLY. The changelog entry recording the
spelling conversion has to quote the old spelling to say what changed, and a guide
quoting a vendor must not have the quotation silently edited, so a spelling match inside
`backticks` or "double quotes" is skipped. A backtick span may be fenced by any run of
backticks, and this closes a run on the next run of the same length, which is what makes
``serialise(`value`)`` one span rather than three. It is not CommonMark's rule, which
requires the closing run to be a MAXIMAL run of exactly that length, so a line carrying
unequal runs is matched differently here than a renderer would match it. Two demonstrated
cases sit either side of that difference and are recorded as known limits.

The placeholder check does NOT take that exemption, because a placeholder's natural home
is a command inside backticks. Applying the carve-out to both is how the first draft of
this gate missed `./pocketbase serve yourdomain.com`, which is the defect it was written
to catch.

EXEMPTIONS, each with a reason. Spelling skips `backticks`, "double quotes", URLs, fenced
code and block quotations, because a quotation must not be silently edited, a URL path
cannot be respelled without breaking the link, and `def serialise(value)` is an identifier.
The URL exemption keys on the scheme, so `https://host/tls#minimise` is skipped and a bare
`/tls#minimise` is not. Exempting bare paths would mean blanking any run of text containing
a slash, which is most comments in this corpus. Single quotes are NOT an exemption: an
apostrophe pair spanning contractions blanked the prose between them, so "Don't authorise
this with the admin's key" passed. A comment inside a fence IS read, because it is a
sentence a reader reads, including one that starts in column one: an earlier version
required a space before the `#` and so skipped every full-line comment in the corpus. A
BLOCK QUOTATION is not scanned at all; passing one to the fence-comment reader turned the
`#` of a quoted Markdown heading into a comment delimiter and flagged `> ## Authorisation`.
The placeholder check skips CHANGELOG.md, because an entry recording a placeholder
replacement has to name the old value, and a changelog line is not something a reader pastes
into a server.

NOT ON THE LIST, deliberately: `analyse` and `paralyse`. Oxford English keeps those. They
are not -ize verbs, and an earlier version of this file wrongly flagged `analyse`.

WHAT THIS DOES NOT PROVE: that the prose is otherwise correct, that -ize was applied to
words outside this list, or that a placeholder outside this list is safe. Both checks are
closed lists, and a closed list only catches what it names. The first version of this file
also listed example.org as a bad placeholder, which is wrong: RFC 2606 reserves
example.com, example.net and example.org alike. A placeholder is also only judged on its
own labels: `yourdomain.com.internal` and `yourdomain.com.example.com` are house
placeholders whatever the label on the left, so the match is extended to the end of the
hostname before it is judged. The suffix list also accepts `.example.net` and
`.example.org`, which RFC 2606 reserves alongside example.com, and CONTRIBUTING rule 2
now names all three so that the gate is not quietly more permissive than the rule it
enforces. Two exemption limits are known and left open rather than papered over. Quote
state is per line, so a quotation opened on one line and closed on another does not
blank the lines between. And inside a fenced block only a shell-style trailing comment is
read as prose, which means a `#` inside a Python triple-quoted string is read as one;
treating it correctly would mean tracking multiline string state per language, which is a
parser, and this is not one.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk
from _markdown import Fences  # noqa: E402  one shared definition of a fenced block

SKIP_DIRS = {".git", "node_modules", "__pycache__", "tools", "scripts", ".github", ".aiqt"}

# Generated. Its content comes from the guides, so a finding here is a duplicate of one
# there, and reporting both would send a reader to the file they must not hand-edit.
GENERATED = {"llms-full.txt"}

# The changelog records what changed, which for a placeholder replacement means naming the
# old value. Scanning it would make this very change undocumentable: an honest entry saying
# `yourdomain.com` was replaced would turn the build red. A changelog entry is also not
# something a reader copies into a server, which is what the placeholder rule protects.
NO_PLACEHOLDER_CHECK = {"CHANGELOG.md"}

# British -ise forms whose Oxford counterpart is -ize. Deliberately a closed list: a
# regex for "any -ise word" would flag exercise, advertise, comprise and the rest.
ISE_STEMS = (
    "authoris", "organis", "recognis", "randomis", "normalis", "synchronis",
    "initialis", "customis", "minimis", "maximis", "categoris", "prioritis",
    "standardis", "summaris", "utilis", "optimis", "serialis", "deserialis",
    "sanitis", "virtualis", "parameteris",
    "tokenis", "anonymis", "pseudonymis", "capitalis", "centralis", "generalis",
    "localis", "modernis", "specialis", "visualis", "finalis", "dockeris",
    "stabilis", "modularis", "operationalis", "containeris",
)
# No leading \b: `unauthorised` and `reinitialised` carry a listed stem mid-word, and an
# anchored prefix let both through while claiming to cover `authoris` and `initialis`.
ISE_RE = re.compile(r"(" + "|".join(ISE_STEMS) +
                    r")(e|es|ed|ing|ation|ations|er|ers|able|ables|ability|abilities|ational)?\b", re.I)

# Placeholders that are not in the house set. Each is a domain someone may actually own.
BAD_PLACEHOLDERS = re.compile(
    r"\b(yourdomain\.com|yoursite\.com|mydomain\.com|mysite\.com|yourcompany\.com|"
    r"yourserver\.com|mycompany\.com|foo\.com|bar\.com)\b", re.I
)

# CONTRIBUTING rule 2's house set. A match is judged against the WHOLE hostname it sits in,
# so a left label that happens to be a bad placeholder does not condemn a house host.
HOUSE_SUFFIXES = (".example.com", ".example.net", ".example.org", ".internal")
HOSTNAME_TAIL = re.compile(r"[A-Za-z0-9.-]*")

# Single quotes are NOT treated as a quotation delimiter: an apostrophe pair spanning a
# contraction ("Don't ... admin's") blanked the prose between them and hid a real finding.
# A code span may be fenced by any RUN of backticks, and it closes only on a run of the same
# length. The single-backtick form read the opening ``  of ``serialise(`value`)`` as an empty
# span and then flagged the identifier inside it.
QUOTED_RE = re.compile(r"(`+)(?:(?!\1)[\s\S])*?\1|\"[^\"]*\"")
# A cited URL may contain a British spelling in its path, and respelling it breaks the
# link. UK government and vendor documentation routinely does this. The URL stops at a
# quotation mark, a backtick or an angle bracket rather than running to whitespace: a
# `\S+` tail ate the closing `"` of a quoted sentence, and the quotation blanking that
# followed then hid real prose after the quotation ended. An apostrophe is not in that set:
# single quotes are not a quotation delimiter here, so excluding one only truncated a valid
# URL path.
URL_RE = re.compile(r"""https?://[^\s"`<>]+""")


def unquoted(line):
    """The line with backticked and double-quoted spans blanked out, so matches inside a
    quotation are not found. Length is preserved so column positions stay meaningful."""
    blanked = URL_RE.sub(lambda m: " " * len(m.group(0)), line)
    return QUOTED_RE.sub(lambda m: " " * len(m.group(0)), blanked)


def _fence_comment(line):
    """The comment part of a line inside a fence, or "" if it has none.

    A comment `#` begins the line or follows whitespace. A URL fragment `#` does neither,
    so splitting on the first `#` stripped the scheme off `https://host/tls#minimise` and
    handed the fragment to the spelling check as prose. Requiring a PRECEDING space, rather
    than start-of-line OR a preceding space, skipped every column-one comment instead.

    Backslash escapes are honoured outside quotes and inside double quotes, and not inside
    single quotes: reading the escaped quote in `printf "%s" "a \\" #x"` as a closing quote
    made string data look like a comment.
    """
    out_start, quote, idx = None, None, 0
    while idx < len(line):
        ch = line[idx]
        if ch == "\\" and quote != "'" and idx + 1 < len(line):
            idx += 2
            continue
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (idx == 0 or line[idx - 1].isspace()):
            out_start = idx
            break
        idx += 1
    return line[out_start:] if out_start is not None else ""


def bad_placeholder(line):
    """The first placeholder on the line that is outside the house set, or None.

    Two defects shaped this. Stopping at the FIRST regex match meant a legitimate
    `foo.com.example.com` earlier on the line consumed the check and a real
    `yourdomain.com` later on it went unreported. And judging the match alone rejected
    `yourdomain.com.internal`, a `.internal` host that CONTRIBUTING rule 2 permits outright.
    Every match is therefore extended to the end of its hostname and judged whole.
    """
    for m in BAD_PLACEHOLDERS.finditer(line):
        host = m.group(0) + HOSTNAME_TAIL.match(line, m.end()).group(0).rstrip(".")
        if host.lower().endswith(HOUSE_SUFFIXES):
            continue
        return m
    return None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = []
    scanned = 0
    try:
        paths = sorted(walk_files(root, SKIP_DIRS, suffixes={".md", ".txt", ".html"}))
    except Exception as exc:
        print(f"  FAIL  could not walk the repository: {exc}")
        return 2

    for path in paths:
        if path.name in GENERATED:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            findings.append(f"{path.relative_to(root)}: unreadable ({exc})")
            continue
        fences = Fences()
        for lineno, line in enumerate(text.splitlines(), 1):
            if fences.feed(line):
                continue
            # A fenced block holds code, where `serialise` is an identifier and not prose,
            # and a block quotation holds someone else's words. Both are exempt from the
            # SPELLING check only. The placeholder check still reads them, because a fenced
            # command is the primary thing a reader copies, and exempting it there would
            # retire the check in the one place it matters.
            quoted = line.lstrip().startswith(">")
            prose = not (fences.inside or quoted)
            # Spelling ignores quoted spans; placeholders do not, since a placeholder
            # inside backticks is the normal case rather than a quotation.
            # Inside a fence, only a trailing comment is prose. `def serialise(value)` is
            # an identifier; `# ports are randomised at startup` is a sentence a reader
            # reads, and the comments in this corpus carry real explanation.
            # A block quotation is exempt outright. Handing it to the fence-comment reader
            # made the `#` of a quoted Markdown heading a comment delimiter.
            spell_target = line if prose else ("" if quoted else _fence_comment(line))
            m = ISE_RE.search(unquoted(spell_target))
            if m:
                findings.append(
                    f"{path.relative_to(root)}:{lineno}: British spelling '{m.group(0)}', "
                    f"use the Oxford -ize form"
                )
            p = None if path.name in NO_PLACEHOLDER_CHECK else bad_placeholder(line)
            if p:
                findings.append(
                    f"{path.relative_to(root)}:{lineno}: placeholder '{p.group(0)}' is outside the "
                    f"house set; use example.com, a .internal host, loopback, or RFC 1918"
                )

    if findings:
        for f in findings:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    {scanned} files use Oxford -ize spellings and house placeholders")
    return 0


if __name__ == "__main__":
    sys.exit(main())
