#!/usr/bin/env python3
"""Fail on British -ise spellings in prose, and on placeholders outside the house set.

WHAT THIS PROVES: two conventions this repository states and did not enforce.

Spelling. CONTRIBUTING and the project's writing standard settle on Oxford English with
-ize. A corpus-wide conversion missed `randomised`, because the word list used for that
conversion was itself incomplete, and the same word was then written into a new guide
hours later. A word list in a gate is checked by the gate; a word list in someone's head
is not.

Placeholders. CONTRIBUTING rule 2 fixes the placeholder set: example.com and its
subdomains, hosts under .internal, loopback, and RFC 1918 addresses. `yourdomain.com` is
a real registered domain and reached the corpus anyway.

QUOTED TEXT IS EXEMPT FROM THE SPELLING CHECK ONLY. The changelog entry recording the
spelling conversion has to quote the old spelling to say what changed, and a guide
quoting a vendor must not have the quotation silently edited, so a spelling match inside
`backticks` or "double quotes" is skipped.

The placeholder check does NOT take that exemption, because a placeholder's natural home
is a command inside backticks. Applying the carve-out to both is how the first draft of
this gate missed `./pocketbase serve yourdomain.com`, which is the defect it was written
to catch.

WHAT THIS DOES NOT PROVE: that the prose is otherwise correct, that -ize was applied to
words outside this list, or that a placeholder outside this list is safe. Both checks are
closed lists, and a closed list only catches what it names.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk

SKIP_DIRS = {".git", "node_modules", "__pycache__", "tools", "scripts", ".github", ".aiqt"}

# Generated. Its content comes from the guides, so a finding here is a duplicate of one
# there, and reporting both would send a reader to the file they must not hand-edit.
GENERATED = {"llms-full.txt"}

# British -ise forms whose Oxford counterpart is -ize. Deliberately a closed list: a
# regex for "any -ise word" would flag exercise, advertise, comprise and the rest.
ISE_STEMS = (
    "authoris", "organis", "recognis", "randomis", "normalis", "synchronis",
    "initialis", "customis", "minimis", "maximis", "categoris", "prioritis",
    "standardis", "summaris", "utilis", "analys" + "e",  # analyse, not analysis
)
ISE_RE = re.compile(r"\b(" + "|".join(ISE_STEMS) + r")(e|es|ed|ing|ation|ations|er|ers)?\b", re.I)

# Placeholders that are not in the house set. Each is a domain someone may actually own.
BAD_PLACEHOLDERS = re.compile(
    r"\b(yourdomain\.com|yoursite\.com|mydomain\.com|mysite\.com|yourcompany\.com|"
    r"yourserver\.com|example\.org|test\.com)\b", re.I
)

QUOTED_RE = re.compile(r"`[^`]*`|\"[^\"]*\"")


def unquoted(line):
    """The line with backticked and double-quoted spans blanked out, so matches inside a
    quotation are not found. Length is preserved so column positions stay meaningful."""
    return QUOTED_RE.sub(lambda m: " " * len(m.group(0)), line)


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
        for lineno, line in enumerate(text.splitlines(), 1):
            # Spelling ignores quoted spans; placeholders do not, since a placeholder
            # inside backticks is the normal case rather than a quotation.
            m = ISE_RE.search(unquoted(line))
            if m:
                findings.append(
                    f"{path.relative_to(root)}:{lineno}: British spelling '{m.group(0)}', "
                    f"use the Oxford -ize form"
                )
            p = BAD_PLACEHOLDERS.search(line)
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
