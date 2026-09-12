#!/usr/bin/env python3
"""Report cited URLs that answer from a different host or path than the one cited.

THIS IS NOT A GATE. It reaches the network, so it can never sit in the offline suite, where
nothing outside the repository is allowed to turn the build red. It runs in the weekly
advisory workflow beside the link sweep, and it reports rather than fails.

WHAT IT IS FOR. The link sweep accepts 301 and 302, so a citation that has moved passes it
forever while pointing at a redirect. Two pull requests, #16 and #17, were spent on exactly
that drift after it had accumulated across 82 citations. A redirect is not an error today
and is a broken link eventually, and the moment to fix it is while the redirect still says
where the page went.

WHY HOST AND PATH, NOT DEPTH. An earlier attempt compared path depth, which missed
`docs.gunicorn.org/` becoming `gunicorn.org/`: same depth, different host, and the citation
now names a host the vendor no longer serves that page from. Host changes are the ones that
signal a documentation estate moving, and they are reported first for that reason.

WHAT IT DOES NOT DO. It does not edit anything, it does not decide whether a redirect
matters, and it makes no claim about whether the destination still supports the sentence the
citation is attached to. That last one is the important limit: a citation can resolve
perfectly and no longer say what the guide claims it says, and only a reader can catch that.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

URL = re.compile(r"https?://[^\s<>\"'`)\],;]+")
SKIP_HOSTS = {"example.com", "example.net", "example.org", "app.example.com"}
# A release download always redirects to a signed, expiring asset URL on another host. That
# is how the hosting works, not drift, and reporting it every week would train a reader to
# skim this output, which is the failure mode an advisory report cannot afford.
INHERENT = (re.compile(r"^https://github\.com/[^/]+/[^/]+/releases/download/"),)


def cited_urls(root: Path):
    """Every distinct URL in a Sources section, with the guides that cite it."""
    seen = {}
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        i = text.find("## Sources")
        if i == -1:
            continue
        for m in URL.finditer(text[i:]):
            u = m.group(0).rstrip(".,")
            host = urlsplit(u).hostname or ""
            if host in SKIP_HOSTS or host.endswith(".internal"):
                continue
            seen.setdefault(u, set()).add(path.name)
    return seen


def resolve(url, timeout):
    """(status, final_url) after following redirects, or (None, reason)."""
    try:
        done = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-L", "--max-time", str(timeout),
             "-w", "%{http_code} %{url_effective}", url],
            capture_output=True, text=True, timeout=timeout + 10)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if done.returncode:
        return None, done.stderr.strip()[:120] or f"curl exit {done.returncode}"
    parts = done.stdout.split(None, 1)
    if len(parts) != 2:
        return None, "curl printed no destination"
    return parts[0], parts[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=20)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]

    urls = cited_urls(root)
    moved_host, moved_path, slash_only, unreachable = [], [], [], []
    for url, guides in sorted(urls.items()):
        status, final = resolve(url, args.timeout)
        where = ", ".join(sorted(guides))
        if status is None:
            unreachable.append(f"{url}\n      cited by {where}\n      {final}")
            continue
        if final == url:
            continue
        if any(p.match(url) for p in INHERENT):
            continue
        a, b = urlsplit(url), urlsplit(final)
        line = f"{url}\n      -> {final}\n      cited by {where}"
        if a.hostname != b.hostname:
            moved_host.append(line)
        elif a.path.rstrip("/") == b.path.rstrip("/"):
            slash_only.append(f"{url}  (cited by {where})")
        elif a.path != b.path:
            moved_path.append(line)

    print(f"{len(urls)} cited URLs checked")
    for title, rows in (("moved to a different HOST, which is the signal that a "
                         "documentation estate has moved", moved_host),
                        ("moved to a different PATH on the same host", moved_path),
                        ("differ only by a trailing slash, which is cosmetic and listed "
                         "last so it cannot crowd out the two above", slash_only),
                        ("did not answer", unreachable)):
        if rows:
            print(f"\n{len(rows)} {title}:")
            for r in rows:
                print(f"  - {r}")
    if not (moved_host or moved_path or slash_only or unreachable):
        print("no citation resolves anywhere other than where it points")
    # Always zero. This reports; it does not judge, and the workflow it runs in is advisory.
    return 0


if __name__ == "__main__":
    sys.exit(main())
