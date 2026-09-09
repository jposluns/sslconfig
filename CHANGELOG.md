# Changelog

sslconfig is published continuously and carries no version number: there is no release artifact to
version, and each guide is dated by its own "Sources (checked <month year>)" section. Entries here
are grouped by the date the change landed on `main`.

## 2026-09-09

### Added

- An offline gate suite, `tools/run_all_checks.sh`, run on every pull request and on every push to
  `main` as the check `gates`. Four checks to start: `site/llms-full.txt` matches a fresh build,
  every guide is listed in the build script and linked from `site/llms.txt`, every local link target
  and heading anchor resolves, and no private keys or provider tokens appear in tracked files. Every
  check is deterministic and offline, so nothing outside this repository can turn the build red.
  (#1)
- An AIQT Guardrails baseline, vendored and pinned to guardrails
  `8ab5b9ae37cdf4f8bcdb0a73934cb5a58b2aea87`. `CLAUDE.md` and a byte-identical `AGENTS.md` carry the
  AIQT priority ordering and the five rules. The pack's hooks are vendored under `.aiqt/` but are
  deliberately not activated. Three upstream gates joined the suite: `check_site`, `check_no_dashes`,
  and `check_newtab`. The pin and the local patches to re-apply on upgrade are recorded in
  `.aiqt/PIN`. (#2)

### Changed

- Every external link in `site/index.html` now opens in a new tab with `rel="noopener noreferrer"`.
  Fifty-five links changed; the four `sslconfig.ai` links are internal and were left alone. (#2)

### Fixed

- The weekly link check had failed since 2026-09-07 because lychee cannot resolve the root-relative
  `/favicon.svg` in `site/index.html` without a root directory. Passing `--root-dir` fixes it, and
  the sweep now reports 555 of 555 links good. (#1)

### Repository settings

- `main` is protected: a pull request is required, force-push and deletion are blocked, and the
  `gates` check must pass before a merge.
- Issues and pull requests were both disabled on the repository and are now enabled. Pull requests
  being disabled is why the API rejected every attempt to open one, reporting it misleadingly as a
  personal-access-token permission error.
