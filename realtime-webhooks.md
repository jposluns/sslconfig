# WebSockets, server-sent events, and webhooks: authenticating the non-page endpoints

Streaming an LLM response commonly rides a WebSocket or an SSE stream, and integrations commonly call back through a webhook. All three are transports, not authentication mechanisms, and each is routinely shipped wide open. [authentication.md](authentication.md) rule 15 already says each transport needs its own check; this guide is that check for these three.

## 1. WebSocket authentication

The browser `WebSocket()` constructor takes only a URL and an optional `protocols` list; it has no argument for request headers, so a page cannot attach `Authorization: Bearer ...` to the handshake (per MDN's WebSocket API reference). Two verified patterns fill the gap:

- **Cookie plus Origin check.** The handshake is still an HTTP request, so a session cookie the server already set is sent automatically. That alone is not enough: any page on any origin can open a WebSocket to your endpoint and ride the visitor's cookie, which is cross-site WebSocket hijacking (CSWSH). OWASP's WebSocket Security Cheat Sheet is explicit: validate the `Origin` header on every handshake against an allowlist, not a denylist, since wildcard or substring matching is error-prone. Reject the upgrade server-side before any application logic runs if `Origin` is missing or not on the list.
- **A token in the subprotocol or the first message.** `Sec-WebSocket-Protocol` (the `protocols` argument) is meant for subprotocol negotiation, but OWASP recommends token-based authentication as the stronger option for exactly this case: pass a short-lived token as a subprotocol value or as the first message after the socket opens, verify it before treating the connection as authenticated, and rotate tokens on long-lived connections.

Do both where you can: Origin validation stops the hijack, and a token means a stolen cookie alone is not a working credential against the socket.

## 2. Server-sent events (SSE)

An `EventSource` is a plain HTTP GET (confirmed on MDN); it carries cookies the same way any GET does, and `withCredentials: true` sends them cross-origin too. `EventSource` cannot set an `Authorization` header either, so a token-in-header scheme does not reach it. That leaves the same obligations as any authenticated GET: the server must still require the session cookie, and because the browser will happily fire that GET from a page on another origin, checking Origin (and treating the endpoint like a CSRF-relevant one) applies here as much as it does to a WebSocket. If a client needs a header-based token, use `fetch()` with a `ReadableStream` reader instead of `EventSource`.

## 3. Webhooks: verify the sender, not just the shape of the payload

A webhook has no session and no browser to enforce Origin, so the check is a signature over the raw request body:

- **GitHub** signs deliveries with `X-Hub-Signature-256`: an HMAC-SHA256 hex digest of the payload using your webhook's secret, prefixed `sha256=`. Recompute it yourself and compare with a constant-time function (`crypto.timingSafeEqual` in Node.js, `secure_compare` in Ruby); a plain `==` leaks timing.
- **Stripe** signs events with `Stripe-Signature`, formatted `t=<timestamp>,v1=<signature>`. The signed payload is the timestamp concatenated with `.` and the raw body, HMAC-SHA256 with the endpoint's `whsec_...` secret. Verify with an official library where one exists; reject if the timestamp is older than your tolerance (Stripe's libraries default to 5 minutes, and Stripe warns never to set the tolerance to 0, which disables the recency check entirely).

Apply both lessons everywhere: use a distinct secret per endpoint (rotating one does not break every integration at once), and reject a request whose signature does not match or whose timestamp is stale, before your handler touches it. Both providers require the exact raw bytes; a framework that parses and re-serializes JSON before your verification code runs will break the check, so verify signatures against the body as received. Where a webhook route must be exempt from a site-wide CSRF filter, scope that exemption to that one route and method only, never to a whole controller or prefix.

## 4. Bound the expensive endpoints too

Inference, upload, and job-submission endpoints are usually the ones behind these transports, and an authenticated caller can still exhaust them. Enforce, at the proxy in front of the app rather than only in application code: a maximum request/body size, a concurrency cap per client, a request timeout matched to realistic response time, and a per-client rate limit. [authentication.md](authentication.md) covers the identity side these limits key off; the proxy guides (nginx, Caddy, Traefik) carry the directives for each.

## Verify

```bash
# No session, no token: refused before any data streams
curl -i --http1.1 -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Sec-WebSocket-Version: 13" \
  https://app.example.com/ws                       # expect 401/403, not 101

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
