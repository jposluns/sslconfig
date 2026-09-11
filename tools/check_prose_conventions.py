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

EXEMPTIONS, each with a reason. Spelling skips `backticks`, "double quotes", URLs, fenced
code and block quotations, because a quotation must not be silently edited, a URL path
cannot be respelled without breaking the link, and `def serialise(value)` is an identifier.
Single quotes are NOT an exemption: an apostrophe pair spanning contractions blanked the
prose between them, so "Don't authorise this with the admin's key" passed. A comment inside
a fence IS read, because it is a sentence a reader reads. The placeholder check skips CHANGELOG.md, because an
entry recording a placeholder replacement has to name the old value, and a changelog line
is not something a reader pastes into a server.

NOT ON THE LIST, deliberately: `analyse` and `paralyse`. Oxford English keeps those. They
are not -ize verbs, and an earlier version of this file wrongly flagged `analyse`.

WHAT THIS DOES NOT PROVE: that the prose is otherwise correct, that -ize was applied to
words outside this list, or that a placeholder outside this list is safe. Both checks are
closed lists, and a closed list only catches what it names. The first version of this file
also listed example.org as a bad placeholder, which is wrong: RFC 2606 reserves
example.com, example.net and example.org alike.
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
    "sanitis", "virtualis", "containeris", "paramateris", "parameteris",
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

# Single quotes are NOT treated as a quotation delimiter: an apostrophe pair spanning a
# contraction ("Don't ... admin's") blanked the prose between them and hid a real finding.
QUOTED_RE = re.compile(r"`[^`]*`|\"[^\"]*\"")
# A cited URL may contain a British spelling in its path, and respelling it breaks the
# link. UK government and vendor documentation routinely does this.
URL_RE = re.compile(r"https?://\S+")


def unquoted(line):
    """The line with backticked and double-quoted spans blanked out, so matches inside a
    quotation are not found. Length is preserved so column positions stay meaningful."""
    blanked = URL_RE.sub(lambda m: " " * len(m.group(0)), line)
    return QUOTED_RE.sub(lambda m: " " * len(m.group(0)), blanked)


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
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            # A fenced block holds code, where `serialise` is an identifier and not prose,
            # and a block quotation holds someone else's words. Both are exempt from the
            # SPELLING check only. The placeholder check still reads them, because a fenced
            # command is the primary thing a reader copies, and exempting it there would
            # retire the check in the one place it matters.
            prose = not (in_fence or line.lstrip().startswith(">"))
            # Spelling ignores quoted spans; placeholders do not, since a placeholder
            # inside backticks is the normal case rather than a quotation.
            # Inside a fence, only a trailing comment is prose. `def serialise(value)` is
            # an identifier; `# ports are randomised at startup` is a sentence a reader
            # reads, and the comments in this corpus carry real explanation.
            spell_target = line if prose else (
                "#" + line.split("#", 1)[1] if "#" in line else "")
            m = ISE_RE.search(unquoted(spell_target))
            if m:
                findings.append(
                    f"{path.relative_to(root)}:{lineno}: British spelling '{m.group(0)}', "
                    f"use the Oxford -ize form"
                )
            p = None if path.name in NO_PLACEHOLDER_CHECK else BAD_PLACEHOLDERS.search(line)
            # A host UNDER example.com is a house placeholder whatever its left label, so
            # `yourdomain.com.example.com` is fine and must not match on the substring.
            if p and line[p.end():p.end() + 12].startswith(".example.com"):
                p = None
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
