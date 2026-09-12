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
    CONTRIBUTING.md|CLAUDE.md|AGENTS.md|CHANGELOG.md|README.sources.md|TODO.md) return 0 ;;
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

echo "== README guide-index categories match the site menu and site/llms.txt =="
# The README's "## Guide index" section, the site's left-hand menu and site/llms.txt are three
# hand-maintained copies of the same category list; nothing else in this suite catches them
# drifting apart. They had drifted: llms.txt carried ten sections of its own against the
# README's twelve, and three independent reviews raised it before anything compared them.
# llms.txt is checked on its guide MEMBERSHIP too, not just its headings, because a guide
# filed under a different category in one file than the other is the same defect one level
# down. Its "Start here" and "Optional" sections are the llms.txt format's own and are exempt.
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

llms = open("site/llms.txt", encoding="utf-8").read()
llms = re.sub(r"<!--.*?-->", "", llms, flags=re.S)
exempt = {"Start here", "Optional"}
llms_blocks = re.split(r"^## ", llms, flags=re.M)[1:]
llms_cats, llms_members = [], {}
for block in llms_blocks:
    name = block.split("\n", 1)[0].strip()
    if name in exempt:
        continue
    llms_cats.append(name)
    llms_members[name] = re.findall(r"^- \[([a-z0-9.-]+)\]\(", block, re.M)

readme_members = {}
for block in re.split(r"^### ", section, flags=re.M)[1:]:
    name = block.split("\n", 1)[0].strip()
    readme_members[name] = [g[:-3] for g in
                            re.findall(r"^\|\s*\[([^\]]+\.md)\]\(", block, re.M)]

problems = []
if readme_cats != site_cats:
    problems.append(("site menu", site_cats))
if readme_cats != llms_cats:
    problems.append(("site/llms.txt", llms_cats))

if not problems:
    for name in readme_cats:
        if readme_members.get(name) != llms_members.get(name):
            print(f"category {name!r} lists different guides in README.md and site/llms.txt")
            print("  README:    " + repr(readme_members.get(name)))
            print("  llms.txt:  " + repr(llms_members.get(name)))
            sys.exit(1)
    sys.exit(0)

print("README guide-index categories: " + repr(readme_cats))
for label, other in problems:
    print(f"{label} categories: " + repr(other))
    for i, (a, b) in enumerate(zip(readme_cats, other)):
        if a != b:
            print(f"  first difference at position {i}: README={a!r} {label}={b!r}")
            break
    else:
        print(f"  one list is a prefix of the other; lengths differ "
              f"({len(readme_cats)} vs {len(other)})")
sys.exit(1)
PY
); then
  ok "README guide-index, the site menu and site/llms.txt carry the same categories"
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

echo "== site CSP pins every inline block by hash =="
# The CSP in site/_headers names the sha256 of each inline <script> and <style> in
# site/index.html, so an edited block cannot ship with a stale hash: the browser would then
# refuse to run the script, or refuse to apply the stylesheet and render the page unstyled.
# Both are silent in a diff and obvious to a visitor. This check used to live here as an
# embedded Python heredoc and covered only script-src, while style-src carried
# 'unsafe-inline', which permits any inline style including an injected one.
if csp=$(python3 tools/check_csp_hashes.py 2>&1); then
  printf '%s\n' "$csp"
  # A gate that exits 0 while printing findings would otherwise read as a pass.
  if grep -q '^  FAIL  ' <<< "$csp"; then
    bad "check_csp_hashes.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$csp"; then
  bad "check_csp_hashes.py crashed; the CSP hashes are unverified"
  printf '%s\n' "$csp" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$csp"; then
  printf '%s\n' "$csp"
  fail=1
else
  bad "check_csp_hashes.py exited non-zero without reporting a gate result"
  printf '%s\n' "$csp" | sed 's/^/          /'
fi

echo "== the CSP hash gate still catches what review found =="
# The gate's first version read the page with regular expressions and a reviewer demonstrated
# six ways that was wrong. It reads the page with html.parser now. One case is a FALSE ALARM
# the old version raised rather than a miss it had, and the file checks that the old approach
# really would have failed it, so the case cannot quietly stop meaning anything.
if csp_tests=$(python3 tools/test_csp_hashes.py 2>&1); then
  printf '%s\n' "$csp_tests"
  if grep -q '^  FAIL  ' <<< "$csp_tests"; then
    bad "test_csp_hashes.py printed findings but exited 0"
  fi
elif grep -qE '^Traceback \(most recent call last\):|^[A-Za-z_.]+Error: ' <<< "$csp_tests"; then
  bad "test_csp_hashes.py crashed; the CSP hash gate is unverified"
  printf '%s\n' "$csp_tests" | sed 's/^/          /'
elif grep -q '^  FAIL  ' <<< "$csp_tests"; then
  printf '%s\n' "$csp_tests"
  fail=1
else
  bad "test_csp_hashes.py exited non-zero without reporting a result"
  printf '%s\n' "$csp_tests" | sed 's/^/          /'
fi

echo "== the advisory citation sweep still imports =="
# NOT a gate on the citations themselves: report_citation_drift.py reaches the network and can
# never run in this suite. But it imports SOURCES_RE, headings and section_body from
# check_guide_shape.py, and renaming or reshaping any of those would leave every gate green and
# break the weekly run with a traceback nobody sees until Monday. Importing the module is
# offline, costs nothing, and is the cheapest thing that keeps the two in step.
# Calling sources_text exercises the borrowed signatures too: importing a name proves it still
# exists, and a reviewer showed that reshaping one of them keeps the import green and fails at
# the call, which is the same Monday-morning traceback one level down.
if imp=$(cd tools && python3 -c 'import report_citation_drift as r; r.sources_text("")' 2>&1); then
  ok "report_citation_drift.py still imports what it borrows from check_guide_shape.py"
else
  bad "report_citation_drift.py no longer imports; the weekly citation sweep would fail: $imp"
fi

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
