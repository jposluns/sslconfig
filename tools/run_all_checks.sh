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
for f in *.md; do
  not_a_guide "$f" && continue
  grep -qF " $f" scripts/build-llms-full.sh || { bad "$f is not listed in scripts/build-llms-full.sh"; wired=0; }
  grep -qF "main/$f" site/llms.txt || { bad "$f is not linked from site/llms.txt"; wired=0; }
  [ "$f" = README.md ] || grep -qE "^\| \[$f\]\($f\) \|" README.md || { bad "$f is not indexed in README.md"; wired=0; }
  # Strip single-line HTML comments first so a commented-out menu entry does not count as wired.
  sed -E 's/<!--([^-]|-[^-]|--[^>])*-->//g' site/index.html | grep -qE "<a href=\"https://github.com/jposluns/sslconfig/blob/main/$f\"" \
    || { bad "$f is not linked from the site/index.html menu"; wired=0; }
done
[ "$wired" = 1 ] && ok "every guide is listed in the build script, linked from llms.txt, indexed in README.md, and in the site menu"

echo "== local links resolve =="
# Heading slugs of a Markdown file, using the GitHub transformation: lowercase, drop everything but
# letters, digits, spaces and hyphens, then spaces to hyphens.
heading_slugs() {
  sed -n 's/^#\{1,\}[[:space:]]\{1,\}//p' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed 's/[^a-z0-9 -]//g; s/ /-/g'
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
pre_ids = set(re.findall(r'<pre\b[^>]*\bid="([^"]+)"', html))
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
# edited script cannot ship with a stale hash (the browser would then refuse to run it).
script_hashes=$(python3 - <<'PY'
import base64, hashlib, re
html = open("site/index.html", encoding="utf-8").read()
for body in re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S):
    print(base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode())
PY
)
csp_ok=1
[ -n "$script_hashes" ] || { bad "no inline <script> found in site/index.html"; csp_ok=0; }
# Only the effective header line counts: a hash left in a comment or another header proves nothing.
csp_lines=$(sed 's/^[[:space:]]*//' site/_headers | grep -v '^#' | grep -i '^Content-Security-Policy:')
[ -n "$csp_lines" ] || { bad "site/_headers has no Content-Security-Policy header line"; csp_ok=0; }
for h in $script_hashes; do
  printf '%s\n' "$csp_lines" | grep -qF "sha256-$h" \
    || { bad "the Content-Security-Policy line in site/_headers lacks the hash of an inline script in site/index.html (sha256-$h)"; csp_ok=0; }
done
[ "$csp_ok" = 1 ] && ok "every inline script hash in site/index.html is pinned in site/_headers"

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
