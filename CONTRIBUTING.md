# Contributing

Suggestions and guides are welcome. Open a GitHub issue describing the tool or control, or send a pull request; reaching Jeff any other way also works.

## Scope

This repository covers deployment exposure: TLS, authentication, MFA, secret handling, and network exposure for services that AI-assisted projects commonly run. General application security (injection, deserialization, business logic) is out of scope; the guides point to OWASP resources for that.

## What a guide needs

1. **Verified syntax.** Every configuration line, flag, or variable name must come from the vendor's documentation, with that page linked in a "Sources (checked <month year>)" section. Version-dependent syntax carries a version note; anything time-sensitive (pricing, tiers, defaults that shift) is flagged with "at the time of writing" and a pointer to the source.
2. **The standard structure.** Short risk statement, numbered setup steps (bind privately, TLS, authentication, MFA where viable), a Verify section with runnable checks, and Sources. Match the tone of the existing guides: direct, generic placeholders (`example.com`, `203.0.113.10`), no screenshots.
3. **Honesty over coverage.** Where a tool has no native control (no auth, no TLS, no MFA), the guide says so plainly and gives the fronting-layer pattern instead of inventing options.
4. **Working links.** A weekly workflow checks every link; run your additions through it mentally: cite canonical documentation pages, not blog posts.

## Licence

Everything here is dedicated to the public domain under [CC0 1.0](LICENSE). Submitting a contribution means dedicating it under the same terms.
