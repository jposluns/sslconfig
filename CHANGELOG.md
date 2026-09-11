# Changelog

secureconfig is published continuously and carries no version number: there is no release artifact to
version, and each guide is dated by its own "Sources (checked <month year>)" section. Entries here
are grouped by the date the change landed on `main`.

## 2026-09-11

### Changed

- The project was renamed from `sslconfig` to `secureconfig`. The GitHub repository is now
  `jposluns/secureconfig` and the site is served at `secureconfig.ai`; GitHub redirects the old
  repository path. Every
  absolute repository and site URL in `site/index.html`, `site/llms.txt`, `site/robots.txt`,
  `README.md` and `scripts/build-llms-full.sh` was updated, along with the `AIQT_SITE_HOST` gate
  variable in `tools/run_all_checks.sh` and the patch notes in `.aiqt/PIN`; `site/llms-full.txt` was
  regenerated. Earlier entries in this changelog keep the old name: they record what shipped under
  it. (#8)

- The `sslconfig.ai` domain was retired. Its DNS record was removed on 2026-09-11, so the old
  hostname no longer resolves and `secureconfig.ai` is now the only site hostname. GitHub continues
  to redirect the old `jposluns/sslconfig` repository path, but there is no redirect for the old
  domain: URLs in the wild that point at `sslconfig.ai` fail to resolve rather than forwarding. (#9)

- Three items in the README verification checklist were rewritten so that they discriminate. Each
  could previously be recorded as verified while the exposure it exists to catch was still standing.
  Item 4 now asks the reader to establish whether a failed `openssl s_client -tls1_1` came from the
  server or from a local client that never offered TLS 1.1, since the two are indistinguishable from
  the error alone. Item 7 now requires confirming that something is scheduled to invoke
  `certbot renew`, because a passing dry run proves the command works and nothing about whether it
  will ever be run. Item 10 no longer accepts a Shodan or Censys lookup in place of a live probe from
  a second host, because those services report what they last observed rather than what is listening
  now. (#10)

- The "Jump to" line was removed from the top of `site/index.html`. The left-hand menu and the
  in-page anchors it pointed at are unchanged. (#9)

- The README and the site front page (`site/index.html`) were realigned with the current corpus.
  One canonical description now appears in the README title, the site tagline, and both the meta and
  Open Graph descriptions. The AI-assistant rules, the decision guide, and the verification checklist
  were rewritten to cover identity and the allowlist, machine credentials, secrets, egress and
  metadata, exposed files, and the AI stack, and the README and site rule lists were reconciled. The
  flat guide index and the site menu were regrouped into the same twelve categories. No guide content
  changed. (#6)

### Added

- A gate, `tools/check_guide_shape.py`, requiring every guide to carry a Verify section with a
  non-empty body and a `Sources (checked <month year>)` heading whose date names a real month, is not
  in the future, and cites at least one absolute URL with a hostname. It is deterministic and offline
  like the rest of the suite, and monotonic in time: its only date comparison can turn a failing guide
  into a passing one as the clock advances, never the reverse, so no build can go red from the
  calendar alone. The gate covers only the structural floor of `CONTRIBUTING.md` rule 5: it cannot
  prove that a Verify body holds a runnable command, that a Verify step fails while the service is
  still exposed, or that a cited page contains the line it is cited for, and it says so rather than
  implying wider coverage. `common-mistakes.md` is the one documented exemption. (#9)
- `README.sources.md`, holding the citations for the README verification checklist. The checklist
  names tools, status codes and services without citing them inline, so the sources now sit in a
  companion file and the front page stays readable. `README.md` is held to the same Verify and Sources
  contract as any guide, resolving its Sources through that file. Nothing mechanically ties a numbered
  check to its citation, so that correspondence is kept by reading. (#9)
- A fifth copy-ready prompt on the site that audits the AI and agent stack. (#6)
- A gate in `tools/run_all_checks.sh` that fails if the README guide-index category headings and the
  site menu category headings drift apart. (#6)

## 2026-09-10 (gap guides)

### Added

- Nineteen guides from a three-family forward-looking gap review: `fronting-auth.md` (oauth2-proxy,
  Authelia, Pomerium wiring, which six existing guides already referenced), `web-exposure.md`,
  `egress-metadata.md`, `realtime-webhooks.md`, `container-hardening.md`, `deployment-lifecycle.md`,
  `image-gen-uis.md`, `chat-uis.md`, `llm-observability.md`, `workflow-orchestrators.md`,
  `gpu-clouds.md`, `nats.md`, `search-engines.md`, `bi-dashboards.md`, `pocketbase.md`,
  `frontend-frameworks.md`, `sqlite.md`, `tunnels.md`, and `surrealdb.md`. Each cites vendor pages
  fetched in September 2026; unconfirmable details were left out.
- Sections folded into existing guides: a shared-cache disclosure section in `headers.md`, a
  fail-closed rule in `cloud-identity-proxies.md`, CAA records in `free-certificates.md`, an
  expensive-endpoint limit note and an offboarding rule in `authentication.md`, an offboarding check
  in `mfa.md`, Dozzle, Docker Registry, Filebrowser, and Node-RED in `devops-uis.md`, Hugging Face
  Spaces in `paas.md`, a Redpanda note in `kafka.md`, and a Valkey note in `redis.md`.
- README gained an outside-in verification checklist item, a fronting-auth pointer in the
  authentication rule and decision guide, and index rows for every new guide; the site menu,
  `site/llms.txt`, the build script, and `.aiqt/gensrc.json` were updated to match.

## 2026-09-10

### Added

- Twenty-one guides: `identity-providers.md`, `oidc-integration.md`, `cloud-identity-proxies.md`,
  `machine-auth.md`, `nextjs.md`, `go.md`, `dotnet.md`, `java.md`, `php.md`, `ruby.md`, `kafka.md`,
  `clickhouse.md`, `neo4j.md`, `memcached.md`, `object-storage.md`, `vector-databases.md`,
  `mcp-servers.md`, `ray.md`, `mlflow.md`, `agent-builders.md`, and `devops-uis.md`. Configuration
  syntax in each was checked against vendor documentation fetched in September 2026, and each
  guide's Sources section lists the pages. A three-family review (Claude, Codex, Gemini) of the
  whole branch then found and corrected further defects, listed under Fixed; details that no page
  confirmed were left out.
- `authentication.md` rules 11 to 15: federated login is not authorisation, OIDC and OAuth hygiene,
  MFA enforced where access is granted, control-plane MFA, and authentication on every transport;
  plus a negative-test quick check.
- `mfa.md`: a phishing-resistant factor for administrators, enrolment is not enforcement, a pointer
  to hosted providers, and a section on passkeys and hardware keys.
- `common-mistakes.md` items 15 to 19, including federated login treated as authorisation and MCP
  servers bound to all interfaces.
- `model-servers.md` now covers Text Generation Inference, SGLang, Triton, and LM Studio.
- README: an AI-assistant rule on federated login and a decision-guide entry for team and customer
  login. Site: menu entries for every new guide, the same rule, and a fourth copy-ready prompt,
  "Add single sign-on and MFA".
- The wiring gate now also fails when a guide is missing from `README.md` or the site menu.

### Changed

- `kubernetes.md` rewritten on the Gateway API (Envoy Gateway, cert-manager Gateway support,
  SecurityPolicy for basic auth and OIDC) because the Kubernetes project retired ingress-nginx in
  March 2026 with no further releases or security patches. The guide tells readers how to detect
  ingress-nginx and that migration is required.
- `free-certificates.md` carries Let's Encrypt's announced lifetime schedule (64-day certificates
  from 2027-02-10, 45-day from 2028-02-16, an industry cap of 47 days from 2029-03-15) and notes
  that Let's Encrypt ended OCSP on 2025-08-06, so no stapling directives for its certificates.
- `paas.md` distinguishes platform deployment protection (Vercel) from application user
  authentication instead of saying the platform authenticates nobody.
- `redis.md` describes mutual TLS as a possession factor for machine clients, not MFA for a person.
- `linkcheck.yml` documents why 403, 429, and 999 are accepted: a green sweep proves every URL
  answered, not that every page was readable.

### Fixed

- `tools/check_site.py` reads the site host from `AIQT_SITE_HOST`, so absolute `sslconfig.ai`
  self-links in `site/index.html` are resolved rather than skipped as external. Recorded as a local
  patch in `.aiqt/PIN`.
- `CLAUDE.md` and `AGENTS.md` now describe the wiring gate's real coverage, and `.aiqt/gensrc.json`
  lists every source of `site/llms-full.txt`.
- Pre-existing guide defects found by the review: Redis inline comments that its parser rejects;
  PostgreSQL `listen_addresses` needing a restart rather than a reload; MongoDB client examples
  lacking the certificate the server configuration demanded; Caddy `/admin/*` not matching
  `/admin`; lighttpd `mod_redirect` not loaded; SSH MFA advice that conflicted with
  `KbdInteractiveAuthentication no`; Open WebUI's persisted `ENABLE_SIGNUP`; the Streamlit login
  example admitting any Google account; the multi-port `nc` check in `cloud-firewalls.md`; and
  several inline comments inside properties and INI values in the new guides.
- A gate that recomputes the sha256 of every inline script in `site/index.html` and requires it in
  the effective CSP line of `site/_headers`; the wiring gate now matches real index rows and menu
  links rather than any text; same-page anchors are validated.

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
