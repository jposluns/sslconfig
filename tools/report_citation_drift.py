#!/usr/bin/env python3
"""Report cited URLs that answer from a different host or path than the one cited.

THIS IS NOT A GATE. It reaches the network, so it can never sit in the offline suite, where
nothing outside the repository is allowed to turn the build red. It runs in the weekly
advisory workflow beside the link sweep.

WHAT IT IS FOR. The link sweep accepts 301 and 302, so a citation that has moved passes it
forever while pointing at a redirect. Two pull requests, #16 and #17, were spent on exactly
that drift after it had accumulated across 82 citations. A redirect is not an error today
and is a broken link eventually, and the moment to fix it is while the redirect still says
where the page went.

WHY IT EXITS NON-ZERO ON A REAL MOVE. An earlier draft always returned 0 and printed its
report into the log of a scheduled run that is green by design. GitHub notifies on a failed
scheduled run and on nothing else, so that report would have reached nobody, which is the
same silence that let the original drift reach 82 citations in the first place. A host move
or a path move now reds the weekly run, the way a hard-broken link already does through the
sweep's own `fail: true`. This workflow is not a required status check and blocks no merge,
so a vendor outage still cannot stop a pull request; that is what the offline gate suite is
for. Everything softer than a move, including a host that refuses automated clients and a
URL that did not answer at all, is reported without failing, because a transient network is
not drift.

WHY HOST AND PATH, NOT DEPTH. An earlier attempt compared path depth, which missed
`docs.gunicorn.org/` becoming `gunicorn.org/`: same depth, different host, and the citation
now names a host the vendor no longer serves that page from. Host changes are the ones that
signal a documentation estate moving, and they are reported first for that reason.

WHERE THE SOURCES SECTION COMES FROM. The same matcher the shape gate uses, imported rather
than re-derived. This script used to look for the literal string "## Sources", which silently
skipped `mfa.md`, whose section is headed "Standards and sources (checked September 2026)".
That guide passes the shape gate and its six citations, including the one CONTRIBUTING flags
as time-sensitive, were never drift-checked at all. A reviewer found it. Two matchers for one
heading is one matcher too many.

WHAT IT DOES NOT DO. It does not edit anything, it does not decide whether a redirect
matters, and it makes no claim about whether the destination still supports the sentence the
citation is attached to. That last one is the important limit: a citation can resolve
perfectly and no longer say what the guide claims it says, and only a reader can catch that.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_guide_shape import SOURCES_RE  # noqa: E402  the one matcher for this heading

URL = re.compile(r"https?://[^\s<>\"'`)\],;]+")
HEADING = re.compile(r"^(#+)[ \t]*(.*)$")

# Reserved and documentation names, which never resolve and must never be curled. RFC 2606
# reserves example.com/net/org and the .test, .invalid, .example and .localhost TLDs;
# CONTRIBUTING permits ANY subdomain of example.com, so an earlier hardcoded set of three
# names would have curled a future db.example.com as weekly NXDOMAIN noise.
RESERVED = (".example.com", ".example.net", ".example.org",
            ".test", ".invalid", ".example", ".localhost", ".local", ".internal")
RESERVED_EXACT = {"example.com", "example.net", "example.org", "localhost"}

# A release download redirects to a signed, expiring asset URL on another host. That is how
# the hosting works, not drift. It is NOT enough to skip these on the cited URL's shape, which
# is what an earlier version did: a reviewer pointed out that renaming or transferring the
# repository produces a redirect through the new owner, which is exactly the drift this script
# exists to catch, and the shape rule would have suppressed it forever. So these are checked
# on their FIRST hop instead, which is the vendor's own answer before the asset host is
# reached. Checking the first hop also avoids downloading the asset every week.
INHERENT = (re.compile(r"^https://github\.com/[^/]+/[^/]+/releases/download/"),)


def skip_host(host: str) -> bool:
    return host in RESERVED_EXACT or host.endswith(RESERVED)


def sources_text(text: str) -> str:
    """Everything under the Sources heading, stopping at the next heading of the same level.

    The earlier version ran from the heading to end of file. `README.sources.md` already has a
    `## Verify` section after its Sources, so anything added there would have been swept in and
    reported as a citation.
    """
    lines = text.split("\n")
    start = level = None
    for n, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        depth, heading = len(m.group(1)), m.group(2).strip()
        if start is None:
            if SOURCES_RE.match(heading):
                start, level = n + 1, depth
        elif depth <= level:
            return "\n".join(lines[start:n])
    return "" if start is None else "\n".join(lines[start:])


def cited_urls(root: Path):
    """Every distinct URL in a Sources section, with the guides that cite it."""
    seen = {}
    for path in sorted(root.glob("*.md")):
        body = sources_text(path.read_text(encoding="utf-8"))
        for m in URL.finditer(body):
            u = m.group(0).rstrip(".,")
            if skip_host(urlsplit(u).hostname or ""):
                continue
            seen.setdefault(u, set()).add(path.name)
    return seen


def curl(url, timeout, *flags):
    """(stdout, None) or (None, why it did not answer)."""
    try:
        done = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "--max-time", str(timeout), *flags, url],
            capture_output=True, text=True, timeout=timeout + 10)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if done.returncode:
        return None, done.stderr.strip()[:120] or f"curl exit {done.returncode}"
    return done.stdout.strip(), None


def resolve(url, timeout):
    """(status, final_url) after following redirects, or (None, reason)."""
    out, why = curl(url, timeout, "-L", "-w", "%{http_code} %{url_effective}")
    if out is None:
        return None, why
    parts = out.split(None, 1)
    if len(parts) != 2:
        return None, "curl printed no destination"
    return parts[0], parts[1]


def first_hop(url, timeout):
    """Where the first redirect points, without following it, or '' when it does not redirect."""
    return curl(url, timeout, "-w", "%{redirect_url}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]

    urls = cited_urls(root)
    moved_host, moved_path, changed_query, slash_only = [], [], [], []
    refused, unreachable = [], []

    for url, guides in sorted(urls.items()):
        where = ", ".join(sorted(guides))
        cited = urlsplit(url)

        if any(p.match(url) for p in INHERENT):
            hop, why = first_hop(url, args.timeout)
            if hop is None:
                unreachable.append(f"{url}\n      cited by {where}\n      {why}")
            elif hop and urlsplit(hop).hostname == cited.hostname:
                # The vendor answered with a redirect of its own rather than handing over to
                # the asset host, so the repository itself moved.
                moved_path.append(f"{url}\n      -> {hop}\n      cited by {where}")
            continue

        status, final = resolve(url, args.timeout)
        if status is None:
            unreachable.append(f"{url}\n      cited by {where}\n      {final}")
            continue

        got = urlsplit(final)
        line = f"{url}\n      -> {final}\n      cited by {where}"
        if cited.hostname != got.hostname:
            moved_host.append(line)
        elif cited.path != got.path and cited.path.rstrip("/") != got.path.rstrip("/"):
            moved_path.append(line)
        elif cited.query != got.query or cited.scheme != got.scheme:
            # Session ids, locale parameters and http-to-https all land here. They are not
            # fixable by editing the citation, and an earlier version printed them under the
            # trailing-slash heading, which told the reader they were cosmetic. They are not.
            changed_query.append(line)
        elif cited.path != got.path:
            slash_only.append(f"{url}  (cited by {where})")
        elif not status.startswith("2"):
            # Answered from where it points, but not with a page. 403, 429 and 999 are the
            # bot-blocking codes the link sweep deliberately accepts; a host that returns one
            # is invisible to this check, and saying so is the difference between a summary
            # that is true and one that merely sounds finished.
            refused.append(f"{url}  (HTTP {status}, cited by {where})")

    out = [f"{len(urls)} cited URLs checked"]
    for title, rows in (
            ("moved to a different HOST, which is the signal that a documentation estate "
             "has moved", moved_host),
            ("moved to a different PATH on the same host", moved_path),
            ("answered at the same path with a different query string or scheme", changed_query),
            ("differ only by a trailing slash, which is cosmetic and listed last so it "
             "cannot crowd out the ones above", slash_only),
            ("answered from where they point, but not with a page, so drift at these hosts "
             "would not be visible here", refused),
            ("did not answer", unreachable)):
        if rows:
            out.append(f"\n{len(rows)} {title}:")
            out.extend(f"  - {r}" for r in rows)

    moves = len(moved_host) + len(moved_path)
    if not moves:
        out.append("\nno citation resolves at a different host or path; "
                   "this says nothing about whether a page still supports the claim it is "
                   "cited for, which only a reader can check")

    report = "\n".join(out)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        # The step log of a green scheduled run is a place nobody is routed to.
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Citation drift\n\n```\n{report}\n```\n")
    return 1 if moves else 0


if __name__ == "__main__":
    sys.exit(main())
