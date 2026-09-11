# Contributing

Suggestions and guides are welcome. Open a GitHub issue describing the tool or control, or send a pull request; reaching Jeff any other way also works.

## Scope

This repository covers deployment exposure: TLS, authentication, MFA, secret handling, and network exposure for services that AI-assisted projects commonly run. General application security (injection, deserialization, business logic) is out of scope; the guides point to OWASP resources for that.

## What a guide needs

1. **Verified syntax.** Every configuration line, flag, or variable name must come from the vendor's documentation, with that page linked in a "Sources (checked <month year>)" section. Version-dependent syntax carries a version note; anything time-sensitive (pricing, tiers, defaults that shift) is flagged with "at the time of writing" and a pointer to the source.
2. **The standard structure.** Short risk statement, numbered setup steps (bind privately, TLS, authentication, MFA where viable), a Verify section with runnable checks, and Sources. Catalogue guides that cover several tools in one file (for example `admin-uis.md`, `model-servers.md`, `devops-uis.md`) use one section per tool instead of numbered steps, and `common-mistakes.md` is a checklist that links to the fixes rather than carrying its own Verify and Sources. Match the tone of the existing guides: direct, generic placeholders (`example.com`, `203.0.113.10`), no screenshots. Subdomains of `example.com` (such as `app.example.com` or `db.example.com`) and hostnames under `.internal` are fine as placeholders, as are loopback and RFC 1918 addresses when the configuration needs them.
3. **Honesty over coverage.** Where a tool has no native control (no auth, no TLS, no MFA), the guide says so plainly and gives the fronting-layer pattern instead of inventing options.
4. **Working links.** A weekly workflow checks every link; run your additions through it mentally: cite canonical documentation pages, not blog posts. A vendor's own announcement or lifecycle notice (for example a Let's Encrypt or Kubernetes project post) counts as canonical documentation when it is the authoritative statement of a change.
5. **Verify steps must discriminate, and every line must be traced.** Before a guide ships, each configuration line is checked against the vendor page it cites, opened while authoring rather than recalled from memory, and each Verify step is run against the *exposed* state as well as the fixed one. A check that passes while the service is still reachable is worse than no check at all, because it certifies the exposure. `tools/check_guide_shape.py` enforces the structural half of this rule (that a Verify section exists, and that Sources is dated and cites something) and it cannot enforce the rest; tracing each line and proving each check discriminates stay with the author and the reviewer. `README.md` is held to the same contract, with its citations kept in `README.sources.md` so the front page stays readable.

## Licence

Everything here is dedicated to the public domain under [CC0 1.0](LICENSE). Submitting a contribution means dedicating it under the same terms.
