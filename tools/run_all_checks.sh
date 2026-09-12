#!/usr/bin/env bash
# Whole-corpus gate suite for secureconfig.
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
# README.sources.md is here too: it holds the citations for the README verification checklist,
# kept out of the README so the front page stays readable. Consequence worth knowing: it is
# therefore NOT carried in llms-full.txt, so an assistant reading only that file sees the
# checklist without its sources.
not_a_guide() {
  case "$1" in
    CONTRIBUTING.md|CLAUDE.md|AGENTS.md|CHANGELOG.md|README.sources.md) return 0 ;;
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
# An unchecked restore could leave a half-written bundle for every later gate to read.
cp "$orig" site/llms-full.txt || { bad "could not restore site/llms-full.txt from $orig"; exit 1; }

echo "== the generated-file record matches how they are generated =="
# CLAUDE.md names .aiqt/gensrc.json as the record of which sources produce site/llms-full.txt.
# Adding a guide touches five wiring surfaces and four of them were gated; this was the fifth,
# so a guide added to the build script and forgotten in the manifest left the record wrong and
# nothing said so. The check above proves the bundle is current. This one proves the manifest
# still agrees with what the build script reports as its inputs.
if gensrc=$(python3 tools/check_gensrc.py 2>&1); then
  printf '%s\n' "$gensrc"
  # A gate that exits 0 while printing findings would otherwise read as a pass.
  if grep -q '^  FAIL  ' <<< "$gensrc"; then
    bad "check_gensrc.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$gensrc"; then
  bad "check_gensrc.py crashed; the generated-file record is unverified"
  printf '%s\n' "$gensrc" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$gensrc"; then
  printf '%s\n' "$gensrc"
  fail=1
else
  bad "check_gensrc.py exited non-zero without reporting a gate result"
  printf '%s\n' "$gensrc" | sed 's/^/          /'
fi

echo "== the generated-file record gate still catches what review found =="
# The first version of the gate above was naive in both directions, and the two are not
# equally bad: missing a source is a silent pass, while inventing one is a fabricated
# finding against a correct repository, which teaches a maintainer to distrust the suite.
# Each case here is a fixture a reviewer ran against it. They build throwaway repositories
# and invoke the real gate, so what is under test is the shipped entry point.
if gensrc_tests=$(python3 tools/test_gensrc_gate.py 2>&1); then
  printf '%s\n' "$gensrc_tests"
  # A gate that exits 0 while printing findings would otherwise read as a pass.
  if grep -q '^  FAIL  ' <<< "$gensrc_tests"; then
    bad "test_gensrc_gate.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$gensrc_tests"; then
  bad "test_gensrc_gate.py crashed; the record gate is unverified"
  printf '%s\n' "$gensrc_tests" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$gensrc_tests"; then
  printf '%s\n' "$gensrc_tests"
  fail=1
else
  bad "test_gensrc_gate.py exited non-zero without reporting a result"
  printf '%s\n' "$gensrc_tests" | sed 's/^/          /'
fi

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
  grep -qE "<a href=\"https://github.com/jposluns/secureconfig/blob/main/$f\"" <<< "$menu_html" \
    || { bad "$f is not linked from the site/index.html menu"; wired=0; }
done
[ "$wired" = 1 ] && ok "every guide is listed in the build script, linked from llms.txt, indexed in README.md, and in the site menu"

echo "== README guide-index categories match the site menu =="
# The README's "## Guide index" section and the site's left-hand menu are two hand-maintained
# copies of the same category list; nothing else in this suite catches them drifting apart.
if cat_diff=$(python3 - <<'PY'
import re, sys

readme = open("README.md", encoding="utf-8").read()
readme = re.sub(r"<!--.*?-->", "", readme, flags=re.S)
m = re.search(r"^## Guide index[ \t]*$", readme, re.M)
if not m:
    print("README.md has no '## Guide index' section")
    sys.exit(1)
rest = readme[m.end():]
m2 = re.search(r"^## ", rest, re.M)
section = rest[:m2.start()] if m2 else rest
readme_cats = re.findall(r"^### (.+?)[ \t]*$", section, re.M)

html = open("site/index.html", encoding="utf-8").read()
html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
excluded = {"On this page", "Reference"}
site_cats = [c for c in re.findall(r'<p class="sidenav-h">([^<]*)</p>', html) if c not in excluded]

if readme_cats == site_cats:
    sys.exit(0)

print("README guide-index categories: " + repr(readme_cats))
print("site menu categories:          " + repr(site_cats))
for i, (a, b) in enumerate(zip(readme_cats, site_cats)):
    if a != b:
        print(f"first difference at position {i}: README={a!r} site={b!r}")
        break
else:
    print("one list is a prefix of the other; lengths differ "
          f"({len(readme_cats)} vs {len(site_cats)})")
sys.exit(1)
PY
); then
  ok "README guide-index categories match the site menu categories"
else
  bad "README guide-index categories do not match the site menu categories"
  printf '%s\n' "$cat_diff" | sed 's/^/          /'
fi

echo "== every guide has a Verify section and dated Sources =="
# The structural half of the CONTRIBUTING rule that a guide must hand the reader runnable checks and
# dated, cited sources. What a reader copies from here faces the internet, so a guide that ships with
# no Verify step at all is a defect, not an omission. The gate deliberately does NOT claim to prove
# that a Verify step DISCRIMINATES (fails while the service is still exposed) or that a config line
# appears on the page it cites; both stay authoring obligations enforced by review.
if guide_shape=$(python3 tools/check_guide_shape.py 2>&1); then
  printf '%s\n' "$guide_shape"
  # A gate that exits 0 while printing findings would otherwise read as a pass.
  # Aligned with the two gates below; not new behaviour for this gate.
  if grep -q '^  FAIL  ' <<< "$guide_shape"; then
    bad "check_guide_shape.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$guide_shape"; then
  # A crash, INCLUDING one that printed some FAIL lines before dying. The gate did not
  # finish, so its findings are incomplete and must never read as a complete verdict.
  bad "check_guide_shape.py crashed; its findings are incomplete"
  printf '%s\n' "$guide_shape" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$guide_shape"; then
  # The gate reported its own findings, already in this suite's FAIL format.
  printf '%s\n' "$guide_shape"
  fail=1
else
  # Exited non-zero saying nothing useful: a kill, or an empty failure.
  bad "check_guide_shape.py exited non-zero without reporting a gate result"
  printf '%s\n' "$guide_shape" | sed 's/^/          /'
fi

echo "== no code block disables TLS verification =="
# Three Verify blocks passed curl -k before anything checked, while three other files in this corpus
# told the reader not to. A probe that skips certificate verification is satisfied by a substituted
# certificate as readily as by the right one, so the TLS half of such a check certifies nothing. This
# gate reads only fenced code blocks, never prose, so a guide may still NAME the flag in a sentence to
# warn against it.
if verify_safety=$(python3 tools/check_verify_safety.py 2>&1); then
  printf '%s\n' "$verify_safety"
  # A gate that exits 0 while printing findings would otherwise read as a pass.
  if grep -q '^  FAIL  ' <<< "$verify_safety"; then
    bad "check_verify_safety.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$verify_safety"; then
  bad "check_verify_safety.py crashed; its findings are incomplete"
  printf '%s\n' "$verify_safety" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$verify_safety"; then
  printf '%s\n' "$verify_safety"
  fail=1
else
  bad "check_verify_safety.py exited non-zero without reporting a gate result"
  printf '%s\n' "$verify_safety" | sed 's/^/          /'
fi

echo "== prose conventions: Oxford -ize and house placeholders =="
# A corpus-wide -ize conversion missed a word because its word list was incomplete, and the same word
# was written into a new guide hours later. A placeholder outside the house set reached the corpus and
# stayed. Both are closed lists, so this catches what it names and nothing else. Quoted and backticked
# spans are exempt from the SPELLING check only, so a changelog entry can quote the old spelling.
if prose_conv=$(python3 tools/check_prose_conventions.py 2>&1); then
  printf '%s\n' "$prose_conv"
  # A gate that exits 0 while printing findings would otherwise read as a pass.
  if grep -q '^  FAIL  ' <<< "$prose_conv"; then
    bad "check_prose_conventions.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$prose_conv"; then
  bad "check_prose_conventions.py crashed; its findings are incomplete"
  printf '%s\n' "$prose_conv" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$prose_conv"; then
  printf '%s\n' "$prose_conv"
  fail=1
else
  bad "check_prose_conventions.py exited non-zero without reporting a gate result"
  printf '%s\n' "$prose_conv" | sed 's/^/          /'
fi

echo "== every fenced bash block is shell =="
# Nothing in this suite checked whether the shell in a Verify block parses, and a reader
# pastes these into a terminal. What it catches is five real defects this corpus was
# carrying. What it does NOT catch is stated in its own docstring and in CONTRIBUTING rule 6:
# `head -c 11m`, and an angle-bracket placeholder, whose check was deleted after five rules
# for it were each beaten by legal shell. It now also proves shellcheck actually ran, rather
# than trusting an exit code that a silenced binary also returns.
if shellblocks=$(python3 tools/check_shell_blocks.py 2>&1); then
  printf '%s\n' "$shellblocks"
  # A gate that exits 0 while printing findings would otherwise read as a pass. A SKIP line
  # is not a finding: shellcheck may not be installed, which the gate says plainly.
  if grep -q '^  FAIL  ' <<< "$shellblocks"; then
    bad "check_shell_blocks.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$shellblocks"; then
  bad "check_shell_blocks.py crashed; the bash blocks are unchecked"
  printf '%s\n' "$shellblocks" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$shellblocks"; then
  printf '%s\n' "$shellblocks"
  fail=1
else
  bad "check_shell_blocks.py exited non-zero without reporting a gate result"
  printf '%s\n' "$shellblocks" | sed 's/^/          /'
fi

echo "== the shell-block gate still catches what it claims =="
# Two of these cases assert what the gate does NOT catch, which are the very defects that
# prompted it. They are recorded so the file cannot quietly start claiming that coverage.
if shellblock_tests=$(python3 tools/test_shell_blocks.py 2>&1); then
  printf '%s\n' "$shellblock_tests"
  if grep -q '^  FAIL  ' <<< "$shellblock_tests"; then
    bad "test_shell_blocks.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$shellblock_tests"; then
  bad "test_shell_blocks.py crashed; the shell-block gate is unverified"
  printf '%s\n' "$shellblock_tests" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$shellblock_tests"; then
  printf '%s\n' "$shellblock_tests"
  fail=1
else
  bad "test_shell_blocks.py exited non-zero without reporting a result"
  printf '%s\n' "$shellblock_tests" | sed 's/^/          /'
fi

echo "== the convention gates still catch what review found =="
# The two gates above were broken repeatedly across rounds of cross-family review, and
# several of those rounds broke something an earlier round had fixed. Each case in this
# file is an input a reviewer actually ran, recorded so that a future change lands on a
# named prior finding instead of silently reopening it. It checks the gates, not the corpus.
if gate_tests=$(python3 tools/test_convention_gates.py 2>&1); then
  printf '%s\n' "$gate_tests"
  # A gate that exits 0 while printing findings would otherwise read as a pass.
  if grep -q '^  FAIL  ' <<< "$gate_tests"; then
    bad "test_convention_gates.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$gate_tests"; then
  bad "test_convention_gates.py crashed; the gates are unverified"
  printf '%s\n' "$gate_tests" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$gate_tests"; then
  printf '%s\n' "$gate_tests"
  fail=1
else
  bad "test_convention_gates.py exited non-zero without reporting a result"
  printf '%s\n' "$gate_tests" | sed 's/^/          /'
fi

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
export AIQT_SITE_HOST=secureconfig.ai
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
