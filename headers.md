# Security headers for your application

TLS protects the transport; these response headers protect the page. Set them at the proxy (`add_header` in [nginx.md](nginx.md), `Header` in [apache.md](apache.md), `header` in Caddy), in app middleware (helmet for Express per [nodejs.md](nodejs.md), Django's security settings per [python.md](python.md)), or in a `_headers` file on static hosts.

## The set worth shipping

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
X-Frame-Options: DENY
```

Notes that keep these correct rather than decorative:

- **HSTS** only after HTTPS provably works everywhere on the domain; `includeSubDomains` commits every subdomain to HTTPS. Leave the `preload` token off unless you have read what preload-list inclusion means; it is effectively irreversible.
- **CSP** is the one that needs tailoring. Start from `default-src 'self'`, add the sources your app actually uses, and prefer nonces or hashes over `'unsafe-inline'` for scripts. Roll out with `Content-Security-Policy-Report-Only` first on an existing app so you see what would break before enforcing.
- **frame-ancestors** in CSP supersedes `X-Frame-Options`; sending both keeps older scanners content and costs nothing.
- Headers belong on every response, including error pages; setting them only on `200 /` is a common proxy misconfiguration (nginx `add_header` inheritance per [nginx.md](nginx.md)).

## Verify

```bash
curl -sI https://example.com/ | grep -iE 'strict-transport|content-security|x-content-type|referrer-policy|permissions-policy|x-frame'
```

Then scan with https://securityheaders.com/ from outside. A CSP that enforces without console errors on every page of the app is the finish line.

## Sources (checked September 2026)

- MDN HTTP headers reference: https://developer.mozilla.org/en-US/docs/Web/HTTP
- Security header scanner: https://securityheaders.com/
