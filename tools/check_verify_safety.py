#!/usr/bin/env python3
"""Fail when a Verify block runs a command that disables TLS certificate verification.

WHAT THIS PROVES: no fenced command block inside a Verify section passes a flag that
turns off certificate validation. That is a rule this corpus states in three places and
broke in three Verify blocks before anything checked it:

  common-mistakes.md   lists disabling TLS verification as a recurring finding
  self-signed.md       says not to ship `curl -k` in committed code
  README.sources.md    spells out that -k disables curl's certificate verification

A Verify step is where it matters most. A probe that skips verification is satisfied by
an attacker-substituted certificate exactly as readily as by the right one, so the TLS
half of the check certifies nothing, and one of the three call sites this was written
against also sent credentials over the unverified connection.

WHAT THIS DOES NOT PROVE: that a Verify step is otherwise correct, that it discriminates
against the exposed state, that the certificate it does verify is the right one, or that
any other insecure flag is absent. It is a single pattern check, not a review.

PROSE IS NOT SCANNED. A guide that warns against `curl -k` names the flag, and naming it
is the point. Only fenced code blocks inside a Verify section are read.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _walk import walk_files  # noqa: E402  fail-closed tree walk

SKIP_DIRS = {".git", "node_modules", "__pycache__", "site", "tools", "scripts", ".github", ".aiqt"}

# Files that document the repository rather than a service.
NOT_A_GUIDE = {
    "CONTRIBUTING.md", "CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "README.sources.md",
}

VERIFY_RE = re.compile(r"^#{1,4}\s*(?:[0-9]+[.)]\s*)?(?:Verif\w*|Quick checks)\b", re.I)
HEADING_RE = re.compile(r"^#{1,4}\s")
FENCE_RE = re.compile(r"^\s*```")

# Each pattern is a way to switch certificate validation off. The name is what the
# failure message reports, so it has to say which tool the reader is looking at.
PATTERNS = (
    ("curl -k / --insecure", re.compile(r"(?:^|\s)curl\b[^|;&]*?(?:\s-[a-zA-Z]*k[a-zA-Z]*\b|\s--insecure\b)")),
    ("wget --no-check-certificate", re.compile(r"(?:^|\s)wget\b[^|;&]*?--no-check-certificate\b")),
    ("python requests verify=False", re.compile(r"verify\s*=\s*False\b")),
    ("node rejectUnauthorized: false", re.compile(r"rejectUnauthorized\s*:\s*false\b")),
    ("NODE_TLS_REJECT_UNAUTHORIZED=0", re.compile(r"NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*0\b")),
    ("openssl s_client without verification", re.compile(r"s_client\b[^|;&]*?-verify_return_error\s*0\b")),
)


def verify_code_lines(text):
    """Yield (line_number, line) for lines inside a fenced block inside a Verify section."""
    in_verify = False
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            if VERIFY_RE.match(line):
                in_verify = True
                continue
            if HEADING_RE.match(line):
                in_verify = False
            continue
        if in_verify:
            yield i, line


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    findings = []
    scanned = 0
    try:
        paths = sorted(walk_files(root, SKIP_DIRS, suffixes={".md"}))
    except Exception as exc:  # a tree we cannot read is a failure, never a pass
        print(f"  FAIL  could not walk the repository: {exc}")
        return 2

    for path in paths:
        if path.parent != root or path.name in NOT_A_GUIDE:
            continue
        scanned += 1
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            findings.append(f"{path.name}: unreadable ({exc})")
            continue
        for lineno, line in verify_code_lines(text):
            # A comment on the line is prose about the command, not the command.
            code = line.split("#", 1)[0]
            for label, pattern in PATTERNS:
                if pattern.search(code):
                    findings.append(
                        f"{path.name}:{lineno}: {label} inside a Verify block: {code.strip()[:80]}"
                    )
                    break

    if findings:
        for f in findings:
            print(f"  FAIL  {f}")
        return 1
    print(f"  ok    no Verify block in {scanned} guides disables TLS certificate verification")
    return 0


if __name__ == "__main__":
    sys.exit(main())
