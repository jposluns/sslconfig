# WebSockets, server-sent events, and webhooks: authenticating the non-page endpoints

Streaming an LLM response commonly rides a WebSocket or an SSE stream, and integrations commonly call back through a webhook. All three are transports, not authentication mechanisms, and each is routinely shipped wide open. [authentication.md](authentication.md) rule 15 already says each transport needs its own check; this guide is that check for these three.

## 1. WebSocket authentication

The browser `WebSocket()` constructor takes only a URL and an optional `protocols` list; it has no argument for request headers, so a page cannot attach `Authorization: Bearer ...` to the handshake (per MDN's WebSocket API reference). Two verified patterns fill the gap:

- **Cookie plus Origin check.** The handshake is still an HTTP request, so a session cookie the server already set is sent automatically. That alone is not enough: any page on any origin can open a WebSocket to your endpoint and ride the visitor's cookie, which is cross-site WebSocket hijacking (CSWSH). OWASP's WebSocket Security Cheat Sheet is explicit: validate the `Origin` header on every handshake against an allowlist, not a denylist, since wildcard or substring matching is error-prone. Reject the upgrade server-side before any application logic runs if `Origin` is missing or not on the list.
- **A token in the first message after the socket opens.** OWASP recommends token-based authentication as the stronger option for exactly this case: pass a short-lived token as a message right after the socket opens, verify it before treating the connection as authenticated, and rotate tokens on long-lived connections. Keep the token out of the URL query string and out of `Sec-WebSocket-Protocol` (the `protocols` argument, meant for subprotocol negotiation, not credentials); both are more likely than a message payload to end up in access logs or proxy logs.

Do both where you can: Origin validation stops the hijack, and a token means a stolen cookie alone is not a working credential against the socket.

## 2. Server-sent events (SSE)

An `EventSource` is a plain HTTP GET (confirmed on MDN); it carries cookies the same way any GET does, and `withCredentials: true` sends them cross-origin too. `EventSource` cannot set an `Authorization` header either, so a token-in-header scheme does not reach it. That leaves the same obligations as any authenticated GET: the server must still require the session cookie, and because the browser will happily fire that GET from a page on another origin, checking Origin (and treating the endpoint like a CSRF-relevant one) applies here as much as it does to a WebSocket. If a client needs a header-based token, use `fetch()` with a `ReadableStream` reader instead of `EventSource`.

## 3. Webhooks: verify the sender, not just the shape of the payload

A webhook has no session and no browser to enforce Origin, so the check is a signature over the raw request body:

- **GitHub** signs deliveries with `X-Hub-Signature-256`: an HMAC-SHA256 hex digest of the payload using your webhook's secret, prefixed `sha256=`. Recompute it yourself and compare with a constant-time function (`crypto.timingSafeEqual` in Node.js, `secure_compare` in Ruby); a plain `==` leaks timing.
- **Stripe** signs events with `Stripe-Signature`, formatted `t=<timestamp>,v1=<signature>`. The signed payload is the timestamp concatenated with `.` and the raw body, HMAC-SHA256 with the endpoint's `whsec_...` secret. Verify with an official library where one exists; reject if the timestamp is older than your tolerance (Stripe's libraries default to 5 minutes, and Stripe warns never to set the tolerance to 0, which disables the recency check entirely).

Apply the shared lesson everywhere: use a distinct secret per endpoint (rotating one does not break every integration at once), and reject a request whose signature does not match before your handler touches it. Replay handling itself is provider specific, not a single universal timestamp check. GitHub's signed payload carries no timestamp, and `X-GitHub-Delivery` is not part of what the signature covers: `X-Hub-Signature-256` is computed over the raw body alone (per GitHub's guidance on validating webhook deliveries), so a captured signed request replayed with a different or reused delivery id still produces a valid signature. Tracking `X-GitHub-Delivery` and refusing a delivery id you have already handled only catches GitHub's own retries of the same delivery; it is not replay protection. For genuine replay protection, make handling idempotent against data the authenticated payload itself carries (an event id or resource state field), or store a digest of the verified body with a retention window and refuse to reprocess a digest already seen, or lean on a provider whose signature already covers a timestamp. Stripe signs a timestamp as part of the signed payload, so reject a request whose timestamp is older than your tolerance window, and never set that tolerance to zero, which disables the recency check entirely. Both providers require the exact raw bytes; a framework that parses and re-serializes JSON before your verification code runs will break the check, so verify signatures against the body as received. Where a webhook route must be exempt from a site-wide CSRF filter, scope that exemption to that one route and method only, never to a whole controller or prefix.

## 4. Bound the expensive endpoints too

Inference, upload, and job-submission endpoints are usually the ones behind these transports, and an authenticated caller can still exhaust them. Two layers need separate limits. At the proxy in front of the app: a maximum request or body size, a connection concurrency cap per client, and a request timeout matched to realistic response time bound the HTTP connection itself; this repository's nginx, Caddy, and Traefik guides do not yet carry those specific directives, so set them directly from each proxy's own documentation. After a WebSocket upgrade, a single accepted connection can still carry unlimited messages or job submissions, which the connection-level limits above do not touch; OWASP's WebSocket Security Cheat Sheet calls for message-level authorization (checking that each individual message is allowed, not only the handshake) and message-level rate limiting (capping messages per connection per time window) as the separate control that applies once the socket is open. [authentication.md](authentication.md) covers the identity side these limits key off.

## Verify

```bash
# Handshake-time auth (a cookie or Origin gate at the proxy or app): rejected before the upgrade completes
curl -i --http1.1 -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Sec-WebSocket-Version: 13" \
  https://app.example.com/ws                       # expect 401/403, not 101

# Post-connect auth (first-message token): the handshake itself succeeds, so this is
# not a curl-only test. Open the socket with a WebSocket client and send no token:
# expect a 101 upgrade, then no protected data and a close once the grace period for
# the first message elapses, proving the server withholds data until the token lands.

# Cross-origin handshake: rejected on Origin even with a valid cookie
curl -i --http1.1 -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Origin: https://evil.example" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Sec-WebSocket-Version: 13" \
  -b "session=REPLACE_WITH_VALID_SESSION_COOKIE" https://app.example.com/ws   # expect 403

curl -i https://app.example.com/events              # SSE without a session: 401/403, not text/event-stream

curl -i -X POST https://app.example.com/webhooks/provider \
  -H "X-Hub-Signature-256: sha256=0000000000000000000000000000000000000000000000000000000000000000" \
  -d '{"test":true}'                                 # expect 401, wrong signature rejected
```

## Common mistakes

- Treating the page login as coverage for the WebSocket or SSE endpoint it opens; each needs its own check.
- Comparing webhook signatures with `==` instead of a constant-time comparison.
- Letting a framework's body parser touch the request before webhook signature verification runs, which breaks the raw-body check.

## Sources (checked September 2026)

- MDN: WebSocket API, `WebSocket()` constructor (no header support, `protocols` argument): https://developer.mozilla.org/en-US/docs/Web/API/WebSocket/WebSocket
- MDN: Using server-sent events (`EventSource`, plain GET, `withCredentials`): https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
- OWASP WebSocket Security Cheat Sheet (Origin allowlisting, token-based authentication): https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html
- GitHub: Validating webhook deliveries (`X-Hub-Signature-256`, constant-time comparison): https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- Stripe: Verify webhook signatures (`Stripe-Signature`, timestamp tolerance, official libraries): https://docs.stripe.com/webhooks#verify-official-libraries
