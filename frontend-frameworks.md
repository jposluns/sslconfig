# Full-stack JS frameworks: SvelteKit, Nuxt, Vite

SvelteKit, Nuxt, and Vite-based apps built by AI assistants inherit the same traps as [nextjs.md](nextjs.md): a server bind that defaults wide open, a proxy that has to be explicitly trusted before secure cookies and correct origins work, and a public-env prefix that ships anything given it straight to the browser. Each framework also has more than one server entry point (endpoints, server routes, load functions), and a check placed in only one of them leaves the others open, exactly as with Next.js layouts versus Server Actions.

## SvelteKit (`adapter-node`)

The built server "will accept connections on `0.0.0.0` using port 3000" by default; override with `HOST` and `PORT`:

```bash
HOST=127.0.0.1 PORT=3000 node build
```

Behind a reverse proxy, set `ORIGIN` (for example `ORIGIN=https://app.example.com`) so SvelteKit computes the correct origin for redirects and cookies. `PROTOCOL_HEADER` and `HOST_HEADER` (for example `x-forwarded-proto` and `x-forwarded-host`) let it read the real scheme and host from the proxy; the docs caution to set these only behind a trusted reverse proxy, since an untrusted client could otherwise spoof them. `ADDRESS_HEADER` and `XFF_DEPTH` do the same for the client's real IP.

CSRF: `csrf.checkOrigin` (default `true`, deprecated in the current reference) checks the `Origin` header for a POST, PUT, PATCH, or DELETE form submission whose `Content-Type` is `application/x-www-form-urlencoded`, `multipart/form-data`, or `text/plain`, rejecting a mismatch with "Cross-site POST form submissions are forbidden." It does not inspect a JSON body or any other content type reaching a `+server.js` endpoint or form action, so those still need their own origin or session check. The docs point to `csrf.trustedOrigins` instead: an allowlist (default empty) of specific origins permitted to submit forms cross site; only `'*'` trusts every origin, and the docs call that generally not recommended.

Public env: only variables prefixed `PUBLIC_` (`env.publicPrefix`) are "statically injected into your bundle at build time" and reachable from `$env/static/public`; anything else throws if imported from client code. Keep secrets in modules SvelteKit treats as server-only, either `$env/static/private` / `$env/dynamic/private`, a `.server.js` filename, or anything under `$lib/server/` ([secrets.md](secrets.md)); SvelteKit statically traces import chains and fails the build if client code imports one, even through a dynamic `import()`.

None of this gates a request for you by default: a `+layout.server.js` guard does not protect a sibling `+page.server.js` load function, a form action, or a `+server.js` endpoint reached directly, so each needs its own session check, the same pattern as the Next.js Data Access Layer in [nextjs.md](nextjs.md). The `handle` hook in `hooks.server.js` can enforce access, since it runs on every request and may return a `Response` before `resolve` renders the route, but only when it actually checks the session and blocks; using it just to redirect an unauthenticated page navigation, or just to attach identity onto `event.locals` for other handlers to read, still leaves a directly reached `+server.js` endpoint or form action open. Inside `handle`, `event.url`, `route`, and `params` can reflect the calling page rather than the resource actually being requested, so do not rely on them alone to decide what is being authorized; checking the session there is necessary but not sufficient, since a session check alone does not authorize access to the specific resource, so also enforce that check at the point each resource is served. Wire real authentication with an identity provider or library per [oidc-integration.md](oidc-integration.md), not a client-side redirect alone.

## Nuxt (Nitro server routes)

Files under `server/api/`, `server/routes/`, and `server/middleware/` are auto-registered Nitro handlers exported with `defineEventHandler()`, and a handler in `server/middleware/` runs before every other server route. Nuxt ships no built-in authentication. A middleware handler can enforce access if it throws (for example `createError` with a 401 or 403) or otherwise ends the request there; one that only attaches `event.context.auth` for other handlers to read has not enforced anything, and every handler that reads it still has to check it itself:

```ts
// server/api/admin.ts: the route checks for itself; the middleware only sets event.context.auth
export default defineEventHandler((event) => {
  if (!event.context.auth?.user) {
    event.node.res.statusCode = 401
    return { message: 'Not authenticated' }
  }
})
```

`runtimeConfig` splits the same way as Next's env prefix: keys directly on `runtimeConfig` are "only available within server-side"; keys under `runtimeConfig.public` are "also exposed to the client-side." Environment variables override both, using an uppercase `NUXT_` prefix with underscores between key segments: private keys just need `NUXT_` (for example `NUXT_API_SECRET`), public keys need `NUXT_PUBLIC_` (for example `NUXT_PUBLIC_API_BASE`). The docs warn not to "expose runtime config keys to the client-side by either rendering them or passing them to `useState`" even when they are private on the server.

## Vite (dev and preview servers)

Both are development tooling, not a production server: the `vite preview` docs say plainly "do not use this as a production server as it's not designed for it." Deploy the built `dist/` behind a real server, CDN, or your platform's hosting per [paas.md](paas.md) instead.

`server.host` defaults to `'localhost'`; setting it to `true` or `0.0.0.0` makes the dev server listen on all addresses, including the LAN, which is fine for testing from a phone on a trusted network but should not be left on elsewhere. `server.allowedHosts` defaults to `[]`, which still auto-permits localhost, `.localhost`, and IP addresses; setting it to `true` disables the check entirely, and the docs warn this "allows any website to send requests to your dev server and download your source code and content" (DNS rebinding). Prefer an explicit hostname allowlist over `true`.

## Verify

```bash
curl -si https://app.example.com/api/private | head -1   # 401 with no session cookie, on all three frameworks
ls build dist .output 2>/dev/null                          # confirm which output directory your build actually produced
grep -rlF "REPLACE_WITH_YOUR_ACTUAL_SECRET_VALUE" build dist .output; echo "exit: $?"
                                                            # search the built client output for the literal secret value with a
                                                            # fixed-string match; exit 1 is the goal, exit 2 means a listed
                                                            # directory did not exist, and grep's own errors are left visible
curl -si https://app.example.com/ -H "Host: evil.example.com" | head -1   # a spoofed Host is not trusted
```

A clean grep result here is evidence, not proof: it means the literal value did not match in the directories searched, not that the secret cannot be present in some other form. A bundler could split, encode, or otherwise transform it, so check the exit code and confirm the directory actually exists rather than reading silence alone as clean.

Behind a reverse proxy, confirm cookies still carry `Secure` and redirects use an `https://` `Location` once `ORIGIN` (SvelteKit) is set; without it, SvelteKit often builds an `http://` URL even though the browser connection is TLS. `NUXT_PUBLIC_...` is the public runtime-config prefix, exposed straight to the client bundle; it is not a trusted-proxy or secure-cookie setting and does nothing for this check. Nuxt's own trusted-proxy and origin handling come from its deployment preset and hosting platform rather than one documented app-level variable, so verify the equivalent behavior against whichever adapter you deploy with.

## Common mistakes

- Treating a SvelteKit `handle` hook that only redirects an unauthenticated page navigation, or a Nuxt `server/middleware/` that only attaches `event.context.auth`, as if it already enforced access, while the `+server.js` endpoint, form action, or `server/api/` route trusts that it happened and skips its own check.
- Leaving `server.allowedHosts` at `true`, or `server.host` wide open, past a local demo.
- Naming a secret `PUBLIC_...` or `NUXT_PUBLIC_...` out of habit from a genuinely public value.

## Sources (checked September 2026)

- SvelteKit adapter-node: https://svelte.dev/docs/kit/adapter-node
- SvelteKit server-only modules: https://svelte.dev/docs/kit/server-only-modules
- SvelteKit `$env/static/public`: https://svelte.dev/docs/kit/$env-static-public
- SvelteKit configuration (`csrf.checkOrigin`, `env.publicPrefix`): https://svelte.dev/docs/kit/configuration
- Nuxt runtime config: https://nuxt.com/docs/4.x/guide/going-further/runtime-config
- Nuxt server directory structure: https://nuxt.com/docs/4.x/directory-structure/server
- Vite server options (`server.host`, `server.allowedHosts`): https://vite.dev/config/server-options
- Vite CLI (`vite preview`): https://vite.dev/guide/cli
