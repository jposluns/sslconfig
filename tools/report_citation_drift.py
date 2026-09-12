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

WHERE THE SOURCES SECTION COMES FROM. The shape gate's own heading walk, imported whole. It
used to be the literal string "## Sources", which silently skipped `mfa.md`, whose section is
headed "Standards and sources (checked September 2026)": that guide passes the shape gate and
its six citations, including the one CONTRIBUTING flags as time-sensitive, were never
drift-checked at all. The first fix shared the regular expression and kept a raw-line heading
parser here, which was not enough. The shape gate walks the document through `scan()`, which
knows about fenced blocks, HTML comments, setext headings and indentation, and a reviewer
built seven documents that gate accepts where the two parsers disagreed about which lines are
in the section: a `#` inside a fenced block truncating it, a setext-styled Sources heading
missed entirely, a Sources heading inside a fenced example picked up, a second Sources section
silently dropped. Each one quietly changes which citations get checked, which is the mfa.md
defect one level down. So this shares the walk now, not just the expression, and it reports
every Sources section rather than the first.

WHAT IT DOES NOT DO. It does not edit anything, it does not decide whether a redirect
matters, and it makes no claim about whether the destination still supports the sentence the
citation is attached to. That last one is the important limit: a citation can resolve
perfectly and no longer say what the guide claims it says, and only a reader can catch that.

TWO MORE LIMITS, STATED. A citation whose new home does not answer lands in "did not answer"
and does not red the run, even though a move to a dead host is the strongest drift signal
there is. That is the price of not redding on a transient network, and the rows are still
printed. And a host that always answers with a cross-host redirect, a consent interstitial or
a regional front door, would red every week forever; `EXPECTED` is the way to acknowledge one,
because a report that is always red is a report nobody reads, and this whole change exists to
create a channel someone will actually look at.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The heading walk as well as the expression. See WHERE THE SOURCES SECTION COMES FROM.
from check_guide_shape import (  # noqa: E402
    SOURCES_RE, headings, section_body)

# Case-insensitive, because the shape gate's own URL expression is and an `HTTPS://` citation
# would otherwise pass that gate and be silently skipped here.
URL = re.compile(r"https?://[^\s<>\"'`)\],;]+", re.I)
DEFAULT_PORT = {"http": 80, "https": 443}

# Reserved and documentation names, which never resolve and must never be curled. RFC 2606
# reserves example.com/net/org and the .test, .invalid, .example and .localhost TLDs;
# CONTRIBUTING permits ANY subdomain of example.com, so an earlier hardcoded set of three
# names would have curled a future db.example.com as weekly NXDOMAIN noise.
RESERVED = (".example.com", ".example.net", ".example.org",
            ".test", ".invalid", ".example", ".localhost", ".local", ".internal")
RESERVED_EXACT = {"example.com", "example.net", "example.org", "localhost",
                  "test", "invalid", "example"}
# RFC 5737 documentation addresses, which this corpus uses as house placeholders.
RESERVED_PREFIX = ("192.0.2.", "198.51.100.", "203.0.113.", "2001:db8:")

# A cross-host redirect that is the vendor's own canonical answer rather than drift. This list
# is the only way to acknowledge one: without it a consent interstitial or a vendor that always
# redirects would red the weekly run forever, and a report that is always red is a report
# nobody reads. Each entry is (cited prefix, destination prefix) and both must match.
#
# End both prefixes at a `/` boundary. They are matched with `startswith`, so `https://a.com`
# would also swallow `https://a.com.evil.example/`, and `https://a.com/x` would swallow
# `https://a.com/x-private/`. The report names this list when it reds, so a maintainer looking
# at a false positive is told where the acknowledgement goes.
EXPECTED = ()

# A release download redirects to a signed, expiring asset URL on another host. That is how
# the hosting works, not drift. It is NOT enough to skip these on the cited URL's shape, which
# is what an earlier version did: a reviewer pointed out that renaming or transferring the
# repository produces a redirect through the new owner, which is exactly the drift this script
# exists to catch, and the shape rule would have suppressed it forever. So these are checked
# on their FIRST hop instead, which is the vendor's own answer before the asset host is
# reached. Checking the first hop also avoids downloading the asset every week.
INHERENT = (re.compile(r"^https://github\.com/[^/]+/[^/]+/releases/download/"),)


def skip_host(host: str) -> bool:
    return (host in RESERVED_EXACT or host.endswith(RESERVED)
            or host.startswith(RESERVED_PREFIX))


def expected(url: str, final: str) -> bool:
    return any(url.startswith(a) and final.startswith(b) for a, b in EXPECTED)


def port_of(parts) -> int:
    return parts.port or DEFAULT_PORT.get(parts.scheme, 0)


def sources_text(text: str) -> str:
    """The body of every Sources section, via the shape gate's heading walk.

    `section_body` already stops at the next heading of equal or higher rank, which is what
    keeps `README.sources.md`'s later Verify section out. Every matching section is collected
    rather than the first, because a guide with two of them had its second silently dropped.
    """
    heads = headings(text)
    return "\n".join(section_body(text, heads, body_start, level)
                      for _i, level, title, body_start in heads
                      if SOURCES_RE.match(title))


def cited_urls(root: Path):
    """Every distinct URL in a Sources section, with the guides that cite it.

    Returns (urls, malformed). A URL that urlsplit refuses is collected rather than raised: the
    expression excludes `]`, so an IPv6 citation extracts as `https://[2001:db8::1` and
    `.hostname` raised ValueError, crashing the whole sweep before a single URL was checked.
    A malformed citation is worth reporting; it is not worth losing the run over.
    """
    seen, malformed = {}, {}
    for path in sorted(root.glob("*.md")):
        body = sources_text(path.read_text(encoding="utf-8"))
        for m in URL.finditer(body):
            u = m.group(0).rstrip(".,")
            try:
                host = urlsplit(u).hostname or ""
            except ValueError as exc:
                malformed.setdefault(u, set()).add(f"{path.name} ({exc})")
                continue
            if skip_host(host):
                continue
            seen.setdefault(u, set()).add(path.name)
    return seen, malformed


def curl(url, timeout, *flags):
    """(stdout, None) or (None, why it did not answer)."""
    try:
        done = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "--connect-timeout", "10",
             "--max-time", str(timeout), *flags, url],
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
    """(status, first redirect target) without following it, or (None, reason).

    The target is empty when the answer is not a redirect. Reporting the status too closed a
    hole: a release URL answering 404 or a Location-less 3xx produced an empty target, the loop
    skipped it, and it appeared in no bucket at all while still counting as checked.
    """
    out, why = curl(url, timeout, "-w", "%{http_code} %{redirect_url}")
    if out is None:
        return None, why
    parts = out.split(None, 1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]

    urls, malformed = cited_urls(root)
    moved_host, moved_path, changed_query, slash_only = [], [], [], []
    refused, unreachable = [], []

    total = len(urls)
    for n, (url, guides) in enumerate(sorted(urls.items()), 1):
        if n % 25 == 0 or n == total:
            # A job killed by its own timeout prints nothing otherwise, because the report is
            # assembled only after the last URL. This goes to stderr so it cannot reach the
            # report or the step summary.
            print(f"  ...{n}/{total} checked", file=sys.stderr, flush=True)
        where = ", ".join(sorted(guides))
        cited = urlsplit(url)

        if any(p.match(url) for p in INHERENT):
            status, hop = first_hop(url, args.timeout)
            if status is None:
                unreachable.append(f"{url}\n      cited by {where}\n      {hop}")
            elif hop and expected(url, hop):
                pass
            elif hop and urlsplit(hop).hostname == cited.hostname:
                # The vendor answered with a redirect of its own rather than handing over to
                # the asset host, so the repository itself moved.
                moved_path.append(f"{url}\n      -> {hop}\n      cited by {where}")
            elif not hop and not status.startswith("2"):
                refused.append(f"{url}  (HTTP {status}, cited by {where})")
            continue

        status, final = resolve(url, args.timeout)
        if status is None:
            unreachable.append(f"{url}\n      cited by {where}\n      {final}")
            continue

        got = urlsplit(final)
        line = f"{url}\n      -> {final}\n      cited by {where}"
        if expected(url, final):
            continue
        if cited.hostname != got.hostname:
            moved_host.append(line)
        elif cited.scheme != got.scheme:
            # An http citation upgrading to https on the same host is not an estate move, and
            # reporting it as one red the run over nearly every vendor. The scheme test has to
            # come before the port test, because the port defaults follow the scheme and 80
            # against 443 otherwise reads as a move.
            changed_query.append(line)
        elif port_of(cited) != port_of(got):
            # `.hostname` drops the port, so a redirect to another port on the same host was
            # compared as identical and counted clean.
            moved_host.append(line)
        elif cited.path != got.path and cited.path.rstrip("/") != got.path.rstrip("/"):
            moved_path.append(line)
        elif cited.query != got.query:
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
    if malformed:
        out.append(f"\n{len(malformed)} citation(s) this script could not parse, which is a "
                   f"defect in the citation rather than drift:")
        out.extend(f"  - {u}  ({', '.join(sorted(g))})" for u, g in sorted(malformed.items()))
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
    if moves:
        out.append("\nThis step exits non-zero on a host or path move, which is what puts it in "
                   "front of a person. If one of the moves above is a vendor's permanent "
                   "answer rather than drift, add it to EXPECTED in this script rather than "
                   "letting the run stay red.")
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
