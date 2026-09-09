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

# Root-level Markdown that documents the repository rather than a service, and
# so is deliberately absent from llms-full.txt and llms.txt.
not_a_guide() {
  case "$1" in
    CONTRIBUTING.md) return 0 ;;
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
done
[ "$wired" = 1 ] && ok "every guide is listed in the build script and linked from llms.txt"

echo "== local links resolve =="
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
        if ! sed -n 's/^#\{1,\}[[:space:]]\{1,\}//p' "$path" \
             | tr '[:upper:]' '[:lower:]' \
             | sed 's/[^a-z0-9 -]//g; s/ /-/g' \
             | grep -qx -- "$anchor"; then
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

echo
if [ "$fail" = 0 ]; then
  echo "All gates passed."
else
  echo "One or more gates failed."
fi
exit "$fail"
