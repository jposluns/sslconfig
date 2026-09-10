#!/usr/bin/env bash
# Whole-corpus gate suite for sslconfig.
#
# Every gate here is deterministic and offline: nothing reaches the network, so
# a vendor outage or a rate limit can never block a pull request. External link
# rot is caught separately by the weekly lychee sweep, which stays advisory for
# that reason.
#
# Usage: tools/run_all_checks.sh   (runs from any directory)
set -uo pipefail

cd "$(dirname "$0")/.." || exit 2

fail=0
ok()  { printf '  ok    %s\n' "$1"; }
bad() { printf '  FAIL  %s\n' "$1"; fail=1; }

# Root-level Markdown that documents the repository or governs the assistants working in it,
# rather than a service, and so is deliberately absent from llms-full.txt and llms.txt.
not_a_guide() {
  case "$1" in
    CONTRIBUTING.md|CLAUDE.md|AGENTS.md|CHANGELOG.md) return 0 ;;
    *) return 1 ;;
  esac
}

echo "== llms-full.txt is current =="
orig=$(mktemp)
cp site/llms-full.txt "$orig"
trap 'cp "$orig" site/llms-full.txt 2>/dev/null; rm -f "$orig"' EXIT
if bash scripts/build-llms-full.sh >/dev/null 2>&1; then
  if diff -q "$orig" site/llms-full.txt >/dev/null 2>&1; then
    ok "matches a fresh build"
  else
    bad "site/llms-full.txt is stale; run scripts/build-llms-full.sh and commit the result"
  fi
else
  bad "scripts/build-llms-full.sh exited non-zero"
fi
cp "$orig" site/llms-full.txt

echo "== every guide is wired into the site =="
wired=1
# Strip HTML comments across the whole file (re.S, not a line-at-a-time sed) so a menu link or
# README row commented out across multiple lines does not count as wired.
menu_html=$(python3 - <<'PY'
import re
html = open("site/index.html", encoding="utf-8").read()
print(re.sub(r"<!--.*?-->", "", html, flags=re.S))
PY
)
readme_stripped=$(python3 - <<'PY'
import re
text = open("README.md", encoding="utf-8").read()
print(re.sub(r"<!--.*?-->", "", text, flags=re.S))
PY
)
for f in *.md; do
  not_a_guide "$f" && continue
  grep -qF " $f" scripts/build-llms-full.sh || { bad "$f is not listed in scripts/build-llms-full.sh"; wired=0; }
  grep -qF "main/$f" site/llms.txt || { bad "$f is not linked from site/llms.txt"; wired=0; }
  [ "$f" = README.md ] || grep -qE "^\| \[$f\]\($f\) \|" <<< "$readme_stripped" || { bad "$f is not indexed in README.md"; wired=0; }
  grep -qE "<a href=\"https://github.com/jposluns/sslconfig/blob/main/$f\"" <<< "$menu_html" \
    || { bad "$f is not linked from the site/index.html menu"; wired=0; }
done
[ "$wired" = 1 ] && ok "every guide is listed in the build script, linked from llms.txt, indexed in README.md, and in the site menu"

echo "== local links resolve =="
# Heading slugs of a Markdown file, using the GitHub transformation: lowercase, drop everything but
# letters, digits, spaces and hyphens, then spaces to hyphens.
heading_slugs() {
  # Strip HTML comments and fenced code blocks first so a "# heading-looking" line inside a
  # ```code``` fence (or a commented-out heading) is never mistaken for a real Markdown heading.
  python3 - "$1" <<'PY'
import re, sys

text = open(sys.argv[1], encoding="utf-8").read()
text = re.sub(r"<!--.*?-->", "", text, flags=re.S)

in_fence = False
for line in text.splitlines():
    if line.strip().startswith("```"):
        in_fence = not in_fence
        continue
    if in_fence:
        continue
    m = re.match(r"#{1,}[ \t]+(.*)$", line)
    if not m:
        continue
    slug = m.group(1).lower()
    slug = re.sub(r"[^a-z0-9 -]", "", slug)
    slug = slug.replace(" ", "-")
    print(slug)
PY
}
links=1
while IFS= read -r target; do
  [ -n "$target" ] || continue
  path=${target%%#*}
  [ -n "$path" ] || continue
  if [ ! -e "$path" ]; then
    bad "broken link target: $target"
    links=0
    continue
  fi
  case "$target" in
    *"#"*)
      anchor=${target#*#}
      if [ -n "$anchor" ] && [ "${path##*.}" = "md" ]; then
        if ! heading_slugs "$path" | grep -qx -- "$anchor"; then
          bad "missing anchor #$anchor in $path"
          links=0
        fi
      fi
      ;;
  esac
done < <(grep -hoE '\]\([^)]+\)' ./*.md \
         | sed 's/^](//; s/)$//' \
         | grep -vE '^(https?:|mailto:|#)' \
         | sort -u)

# Same-document anchors: ](#heading) must name a heading in the file that contains it.
for f in *.md; do
  while IFS= read -r anchor; do
    [ -n "$anchor" ] || continue
    if ! heading_slugs "$f" | grep -qx -- "$anchor"; then
      bad "missing anchor #$anchor in $f"
      links=0
    fi
  done < <(grep -oE '\]\(#[^)]+\)' "$f" | sed 's/^](#//; s/)$//' | sort -u)
done

while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  case "$ref" in
    /*) target="site$ref" ;;
    *)  target="site/$ref" ;;
  esac
  if [ ! -e "${target%%#*}" ]; then
    bad "site/index.html references a missing file: $ref"
    links=0
  fi
done < <(grep -oE '(href|src)="[^"]*"' site/index.html \
         | sed 's/^[a-z]*="//; s/"$//' \
         | grep -vE '^(https?:|mailto:|#|data:)' \
         | sort -u)

[ "$links" = 1 ] && ok "every local link target and heading anchor resolves"

echo "== site copy buttons =="
# Every copy button names the <pre> it copies from; a dangling data-copy is a silently dead button.
if missing_copy=$(python3 - <<'PY'
import re, sys
html = open("site/index.html", encoding="utf-8").read()
# Strip HTML comments first so a <pre id="..."> inside a comment cannot satisfy the check.
html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
pre_ids = set()
for attrs in re.findall(r'<pre\b([^>]*)>', html):
    # Require a preceding boundary so this matches a real id="..." attribute, not data-id="...".
    m = re.search(r'(?:^|\s)id="([^"]+)"', attrs)
    if m:
        pre_ids.add(m.group(1))
missing = [c for c in re.findall(r'\bdata-copy="([^"]+)"', html) if c not in pre_ids]
for c in missing:
    print(c)
sys.exit(1 if missing else 0)
PY
); then
  ok "every data-copy button in site/index.html targets a <pre id> that exists"
elif [ -n "$missing_copy" ]; then
  for id in $missing_copy; do
    bad "site/index.html has data-copy=\"$id\" but no <pre id=\"$id\">"
  done
else
  bad "the site copy-button check itself failed to run"
fi

echo "== no committed secrets =="
# Deliberately narrow: only material that is a credential wherever it appears.
# A guide that must show sample key output will trip this; allowlist it here
# rather than widening the guides' exposure.
secret_re='BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}'
if hits=$(grep -rnIE "$secret_re" --exclude-dir=.git . 2>/dev/null) && [ -n "$hits" ]; then
  bad "possible credential material in tracked files:"
  printf '%s\n' "$hits" | sed 's/^/          /'
else
  ok "no private keys or provider tokens found"
fi

echo "== site CSP script hash =="
# The CSP in site/_headers pins the inline script by sha256. Recompute it from site/index.html so an
# edited script cannot ship with a stale hash (the browser would then refuse to run it). Only the
# script-src directive of the header block that applies to / (or /*) counts, and only a real inline
# <script> (no src= attribute) is hashed.
csp_ok=1
while IFS= read -r line; do
  case "$line" in
    NO_SCRIPT) bad "no inline <script> found in site/index.html"; csp_ok=0 ;;
    NO_BLOCK) bad "site/_headers has no path block for / or /*"; csp_ok=0 ;;
    NO_CSP) bad "the applicable site/_headers block has no Content-Security-Policy header line"; csp_ok=0 ;;
    NO_SCRIPT_SRC) bad "the Content-Security-Policy in site/_headers has no script-src directive"; csp_ok=0 ;;
    MISSING:*) bad "the script-src directive in site/_headers lacks the hash of an inline script in site/index.html (sha256-${line#MISSING:})"; csp_ok=0 ;;
  esac
done < <(python3 - <<'PY'
import re, base64, hashlib

html = open("site/index.html", encoding="utf-8").read()
html = re.sub(r"<!--.*?-->", "", html, flags=re.S)

hashes = []
for attrs, body in re.findall(r"<script(\s[^>]*)?>(.*?)</script>", html, re.S):
    if attrs and re.search(r"\bsrc\s*=", attrs):
        continue
    hashes.append(base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode())

if not hashes:
    print("NO_SCRIPT")
else:
    headers_text = open("site/_headers", encoding="utf-8").read()
    blocks = {}
    path = None
    lines = []
    for raw in headers_text.splitlines():
        if not raw.strip():
            continue
        if not raw[0].isspace():
            if path is not None:
                blocks[path] = lines
            path = raw.strip()
            lines = []
        else:
            lines.append(raw.strip())
    if path is not None:
        blocks[path] = lines

    block = blocks.get("/*")
    if block is None:
        block = blocks.get("/")

    if block is None:
        print("NO_BLOCK")
    else:
        csp_value = None
        for line in block:
            m = re.match(r"content-security-policy:\s*(.*)$", line, re.I)
            if m:
                csp_value = m.group(1)
                break
        if csp_value is None:
            print("NO_CSP")
        else:
            script_src = None
            for directive in csp_value.split(";"):
                directive = directive.strip()
                if re.match(r"script-src\b", directive, re.I):
                    script_src = directive
                    break
            if script_src is None:
                print("NO_SCRIPT_SRC")
            else:
                tokens = script_src.split()[1:]
                for h in hashes:
                    if "'sha256-" + h + "'" not in tokens:
                        print("MISSING:" + h)
PY
)
[ "$csp_ok" = 1 ] && ok "every inline script hash in site/index.html is pinned in the site/_headers script-src directive"

echo "== AIQT baseline =="
# The vendored gates derive the repo root from their own location, so they operate on this tree.
# AIQT_SITE_HOST retargets the upstream helper, which hardcodes aiqt.ai; see .aiqt/PIN.
export AIQT_SITE_HOST=sslconfig.ai
for gate in check_site check_no_dashes check_newtab; do
  if out=$(python3 "tools/${gate}.py" 2>&1); then
    ok "${gate}"
  else
    bad "${gate}"
    printf '%s\n' "$out" | sed 's/^/          /'
  fi
done
if cmp -s CLAUDE.md AGENTS.md; then
  ok "CLAUDE.md and AGENTS.md are identical"
else
  bad "CLAUDE.md and AGENTS.md have diverged; they are one adapter in two files"
fi
python3 tools/gen_aiqt_settings.py --check || fail=1

echo
if [ "$fail" = 0 ]; then
  echo "All gates passed."
else
  echo "One or more gates failed."
fi
exit "$fail"
