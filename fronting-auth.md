# Fronting auth: putting login and MFA in front of an app that has none (oauth2-proxy, Authelia, Pomerium)

Many self-hosted apps (internal tools, dashboards, webhook receivers) ship with no login at all. The fix is the same shape every time: the app binds to loopback, a proxy in front does authentication and MFA, and it passes the app a verified identity, which the app must not accept from anywhere else. This guide is what [mfa.md](mfa.md), [nginx.md](nginx.md), [traefik.md](traefik.md), and [caddy.md](caddy.md) point at.

## 1. The pattern

1. **Bind the app to loopback**, `127.0.0.1`, never `0.0.0.0` or `::`. If the app also answers directly, the login page in front of it is decorative.
2. **A proxy authenticates first**: oauth2-proxy, Authelia, or Pomerium checks the session before the request reaches the app; an unauthenticated request never gets there.
3. **The proxy passes identity in a header** (`X-Auth-Request-User`, `Remote-User`, and similar); the app reads the header instead of running its own login.
4. **The app must reject a client-supplied identity header.** Network isolation, only the proxy can reach the app, is the baseline; without it, anyone who reaches the app's port can set `X-Auth-Request-User: admin` directly. The managed-cloud version of this same bypass risk is in [cloud-identity-proxies.md](cloud-identity-proxies.md).

## 2. oauth2-proxy: auth in front of an OIDC/OAuth2 provider

Core flags (env vars use the `OAUTH2_PROXY_` prefix): `--provider` (`oidc`, `google`, `github`, and others), `--client-id`/`--client-secret` from the IdP, `--email-domain` (a domain, or `*` for any authenticated user), `--upstream` (the app address, or `static://202` when a forward-auth proxy handles the actual proxying), and `--cookie-secret`, which must be exactly 16, 24, or 32 bytes, optionally base64-encoded: `openssl rand -base64 32 | tr -- '+/' '-_'`.

nginx uses `auth_request`:

```nginx
location / {
    auth_request /oauth2/auth;
    error_page 401 = @oauth2_signin;
    auth_request_set $user $upstream_http_x_auth_request_user;
    proxy_set_header X-User $user;
    proxy_pass http://127.0.0.1:3000;
}
location @oauth2_signin {
    return 302 /oauth2/sign_in?rd=$scheme://$host$request_uri;
}
```

Traefik uses a `forwardAuth` middleware at oauth2-proxy's `/oauth2/auth`, with `--upstream=static://202` and `--reverse-proxy=true` set on oauth2-proxy:

```yaml
http:
  middlewares:
    oauth-auth:
      forwardAuth:
        address: "http://oauth2-proxy:4180/oauth2/auth"
        trustForwardHeader: true
        authResponseHeaders: [X-Auth-Request-Access-Token, Authorization]
```

## 3. Authelia: a portal that does the second factor

Authelia is a login portal with built-in TOTP and WebAuthn, sitting behind the proxy rather than replacing it. Per its support page, nginx, Traefik, Caddy (2.5.1+), HAProxy (via a Lua module), Envoy, Skipper, NGINX Proxy Manager, and SWAG are supported; Apache and IIS are documented as having no compatible module and are not supported.

nginx calls a dedicated `auth-request` endpoint (its `auth_request` module cannot forward the method and body the way the others' forward-auth middlewares do):

```nginx
auth_request /internal/authelia/authz;      # proxies to http://authelia:9091/api/authz/auth-request
auth_request_set $redirection_url $upstream_http_location;
error_page 401 =302 $redirection_url;
```

Traefik and Caddy call `/api/authz/forward-auth` instead:

```yaml
- traefik.http.middlewares.authelia.forwardauth.address=http://authelia:9091/api/authz/forward-auth
- traefik.http.middlewares.authelia.forwardauth.authResponseHeaders=Remote-User,Remote-Groups,Remote-Email,Remote-Name
```

```caddyfile
forward_auth authelia:9091 {
    uri /api/authz/forward-auth
    copy_headers Remote-User Remote-Groups Remote-Email Remote-Name
}
```

Authelia needs its own random session secret and access-control rules (which paths need `one_factor` vs `two_factor`); its second factor is TOTP, WebAuthn/passkeys, or Duo mobile push.

## 4. Pomerium: the proxy is the access layer

Pomerium is an identity-aware proxy rather than a sidecar to nginx: it terminates the connection, authenticates the user, and enforces policy in one process. An IdP goes under `idp_provider`, `idp_provider_url`, `idp_client_id`, and `idp_client_secret`; each app is a route carrying its own `policy` (which users, domains, or claims may reach it), rather than a shared middleware bolted onto an existing proxy. Choose Pomerium over the two above when you want routing, TLS, and access control in one process instead of an auth check layered in front of nginx, Traefik, or Caddy.

## 5. MFA and identity source

oauth2-proxy's MFA is whatever its OIDC/OAuth provider enforces; Pomerium's is whatever its `idp_provider` enforces; only Authelia enforces a second factor itself. See [mfa.md](mfa.md) (enrolment is not enforcement) and [identity-providers.md](identity-providers.md) for which hosted providers' tiers include MFA.

## Verify

```bash
ss -tlnp | grep 3000                          # app on 127.0.0.1 only
curl -sI http://203.0.113.10:3000/            # from another host: connection refused
curl -sI https://app.example.com/             # no session: redirected to the sign-in page
curl -sI -H 'X-Auth-Request-User: admin' https://app.example.com/    # forged header dropped en route
```

After a real login, confirm the app-side log shows the identity header the proxy set. A forged header sent straight at the app's own bound address must never be treated as authentication; that is why the app must be unreachable except through the proxy.

## Common mistakes

- The app also listens on a public interface next to the proxy, so a direct request skips authentication entirely.
- The app trusts `X-Auth-Request-User` or `Remote-User` from any caller, not only from the proxy.
- oauth2-proxy's `--cookie-secret` reused across environments or committed to the repository.
- Deploying Authelia behind Apache or IIS, which it does not support.

## Sources (checked September 2026)

- oauth2-proxy configuration overview (flags, cookie-secret length): https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview
- oauth2-proxy nginx integration: https://oauth2-proxy.github.io/oauth2-proxy/configuration/integrations/nginx/
- oauth2-proxy Traefik integration: https://oauth2-proxy.github.io/oauth2-proxy/configuration/integrations/traefik/
- Authelia proxy integration introduction: https://www.authelia.com/integration/proxies/introduction/
- Authelia proxy support matrix (Apache and IIS unsupported): https://www.authelia.com/integration/proxies/support/
- Authelia nginx integration: https://www.authelia.com/integration/proxies/nginx/
- Authelia Traefik integration: https://www.authelia.com/integration/proxies/traefik/
- Authelia Caddy integration: https://www.authelia.com/integration/proxies/caddy/
- Authelia second-factor introduction: https://www.authelia.com/configuration/second-factor/introduction/
- Pomerium identity provider settings: https://www.pomerium.com/docs/reference/identity-provider-settings
- Pomerium documentation: https://www.pomerium.com/docs
