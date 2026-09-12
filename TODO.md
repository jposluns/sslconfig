# TODO

Forward-looking backlog for secureconfig. Item numbers are permanent and never reused. An item
leaves this file only when it is done or explicitly declined, and in either case the CHANGELOG or
a decision record says which.

This file is not a guide. It carries no configuration and is excluded from the guide-shape and
site-wiring gates for that reason; see `not_a_guide()` in `tools/run_all_checks.sh`.

## Needs a decision

### 1. Coverage gaps: the ranked list no longer exists

A 2026-09-11 cross-family audit produced eighteen ranked coverage-gap proposals. Five of them
are named in the working notes and all five have shipped:

| Proposal | Shipped as |
| --- | --- |
| Exposure index mapping port to owning guide | #19 |
| Proxy resource limits (request size, rate, concurrency, timeouts) | #20 |
| Kubernetes control-plane exposure (API server, kubelet 10250, etcd 2379) | #23 |
| Self-hosted identity providers (Keycloak, authentik) | #24 |
| PostgreSQL connection poolers (PgBouncer, pgpool-II) | #30 |

**The other thirteen were never written down.** The notes reference "eighteen ranked proposals"
and name only the top of the list, so the remainder is not recoverable from the record. Deciding
whether to continue means first restoring the list, which is a fresh coverage audit rather than a
lookup. That audit is the decision: run it, or stop adding guides and spend the effort on the 85
that exist.

### 2. Package the corpus as an Agent Plugin

Whether to publish this corpus as a plugin per the Agent Plugins specification, so an assistant
loads the rules when a task matches instead of being told to fetch `llms.txt`. Sketch: one skill,
with the decision guide and the non-negotiables in `SKILL.md` and the guides as `references/`.

The unresolved part is currency, not packaging. Guides carry a "Sources (checked <month year>)"
date and a weekly sweep watches their citations; a packaged plugin freezes at install. Either the
skill points at canonical URLs for anything time-sensitive, or the plugin needs a release cadence,
and that is a maintenance commitment rather than a build step.

### 3. Complete the `(#N)` pull-request references in `CHANGELOG.md`

The convention is applied inconsistently: pull requests 3, 4, 5 and 7 are referenced nowhere.
Completing it means mapping each historical bullet to the pull request that shipped it, which is
archaeology against the git history rather than a mechanical pass.

## Ready to do

### 4. Menu group labels are not headings

`site/index.html` uses `<p class="sidenav-h">` for the thirteen menu group labels, so heading
navigation does not see them. WCAG 2.2 lists "H69: Providing heading elements at the beginning of
each section of content" as a sufficient technique for bypassing repeated blocks, and this is the
half of that technique the page is missing.

A skip link was also proposed and is **not** needed, recorded here so it is not proposed again:
SC 2.4.1 governs content "repeated on multiple web pages" and this is a single page, and the
listed sufficient technique "ARIA11: Using ARIA landmarks" is already satisfied by
`<nav aria-label="Guides and page contents">` followed by `<main>`.

## Blocked upstream

### 5. Activate the AIQT hooks

`.claude/settings.json` is classifier-gated and hook activation was deferred pending the
guardrails versioning work. `tools/gen_aiqt_settings.py` merges rather than overwrites, so it is
safe to run once upstream confirms the intended adoption path.

### 6. Re-pin `.aiqt/` to a tag when guardrails publishes one

Currently pinned to a `main` commit, because the only tag is far behind and predates the commits
this repository depends on. Bump `.aiqt/PIN` and re-apply the recorded local patches on upgrade.

## Process

### 7. Dispatch cross-family QA against a throwaway copy

Reviews are dispatched against a git worktree pinned to the branch under review. That stopped
reviewers reading a checkout that switched underneath them, and it does not stop the orchestrator
committing into the worktree while a review is reading it, which happened repeatedly on
2026-09-12. Copy the worktree to a scratch directory per review and point the reviewer at the
copy, so the snapshot is frozen without anyone having to wait.
