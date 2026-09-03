# Traefik: automatic TLS and authentication middleware

Applies to Traefik v2 and v3. Traefik obtains and renews certificates itself through ACME resolvers, which suits container deployments.

## 1. Static configuration: entry points, redirect, ACME

`traefik.yml`:

```yaml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: admin@example.com
      storage: /letsencrypt/acme.json
      tlsChallenge: {}
```

`acme.json` must persist across restarts (volume-mount it) and be mode `600`. The TLS-ALPN challenge above needs port 443 reachable from the internet; use `httpChallenge` (port 80) or a `dnsChallenge` (wildcards, no inbound ports) where that fits better.

Raise the protocol floor with a TLS options block in the dynamic configuration:

```yaml
tls:
  options:
    default:
      minVersion: VersionTLS12
```

## 2. Route a service with TLS (Docker labels)

```yaml
services:
  app:
    image: yourapp
    labels:
      - traefik.enable=true
      - traefik.http.routers.app.rule=Host(`app.example.com`)
      - traefik.http.routers.app.entrypoints=websecure
      - traefik.http.routers.app.tls.certresolver=letsencrypt
      - traefik.http.services.app.loadbalancer.server.port=3000
```

Do not also publish the app's port with `ports:`; only Traefik publishes 80 and 443. See [docker.md](docker.md).

## 3. Require authentication

Application-level login is preferable ([authentication.md](authentication.md)). At the proxy, attach a basicAuth middleware with bcrypt entries from `htpasswd -nB admin`:

```yaml
    labels:
      - traefik.http.middlewares.app-auth.basicauth.users=admin:$$2y$$05$$REPLACE_WITH_HASH
      - traefik.http.routers.app.middlewares=app-auth
```

In Compose files every `$` in the hash must be doubled to `$$`. The file-provider equivalent, where no escaping is needed:

```yaml
http:
  middlewares:
    app-auth:
      basicAuth:
        users:
          - "admin:$2y$05$REPLACE_WITH_HASH"
```

basicAuth is single-factor. For human-facing sites, add MFA with the `forwardAuth` middleware pointed at [Authelia](https://www.authelia.com/) or [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy), or front the site with Cloudflare Access; options in [mfa.md](mfa.md).

## 4. Verify

```bash
curl -sI http://app.example.com/     # expect a redirect to https://
curl -sI https://app.example.com/    # expect 401 without credentials once auth is on
```

Check the Traefik log for ACME errors on first start; issuance failures otherwise surface as a self-signed "TRAEFIK DEFAULT CERT" in the browser.

## Common mistakes

- Enabling the Traefik dashboard (`api.insecure=true` or an unprotected `api@internal` router) on a public entry point; keep it off or behind the auth middleware.
- Forgetting to persist `acme.json`, which re-issues certificates on every restart and hits CA rate limits.
- Single `$` in Compose basicauth labels, which breaks the hash silently.

## Sources (checked September 2026)

- Traefik documentation: https://doc.traefik.io/traefik/ (HTTPS/ACME, routers, and basicAuth middleware sections)
