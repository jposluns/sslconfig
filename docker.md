# Docker and Compose: exposure, TLS, and authentication

Containers are where accidental exposure happens most. Two Docker behaviours cause it:

1. `ports: - "3000:3000"` (or `-p 3000:3000`) publishes on `0.0.0.0`, every interface.
2. On Linux, Docker programs iptables/nftables directly, so published ports are reachable **even when UFW or firewalld says the port is blocked**. A `ufw deny 3000` rule does not protect a published container port.

## 1. Publish nothing except the TLS proxy

Bind anything that must be reachable from the host to loopback, and give everything else no `ports:` entry at all; containers on the same Compose network reach each other by service name without published ports.

```yaml
services:
  app:
    build: .
    # no ports: entry; only the proxy is published
  db:
    image: postgres:17
    # no ports: entry; the app reaches it at db:5432 on the internal network
```

Where a host-published port is genuinely needed for local access:

```yaml
    ports:
      - "127.0.0.1:3000:3000"
```

## 2. Terminate TLS in one proxy container

Caddy is the least configuration ([caddy.md](caddy.md)); nginx ([nginx.md](nginx.md)) and Traefik ([traefik.md](traefik.md)) work the same way. A complete pattern:

```yaml
services:
  app:
    build: .

  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config

volumes:
  caddy_data:
  caddy_config:
```

`Caddyfile`:

```caddyfile
app.example.com {
    reverse_proxy app:3000
}
```

Caddy obtains and renews the certificate automatically ([free-certificates.md](free-certificates.md) explains the ACME requirements). Hosts without a public domain or inbound ports should use [cloudflare.md](cloudflare.md); run the `cloudflared` connector as a container and point it at `http://app:3000`.

## 3. Authentication and secrets

- The proxy is the natural place for a first authentication gate (basic auth per the proxy guides, or Cloudflare Access); the application still needs its own login for anything multi-user ([authentication.md](authentication.md)).
- Pass secrets at runtime through environment files or Docker/Compose secrets. Never bake them into the image: `ENV API_KEY=...` in a Dockerfile ships the key to every registry the image touches, and `docker history` shows build arguments.
- Keep `.env` in `.gitignore`, and run containers as a non-root user (`USER` in the Dockerfile) so a compromised app is not root in the container.
- Databases in containers still need their own TLS and authentication when anything outside the Compose network connects: see [postgresql.md](postgresql.md), [mysql.md](mysql.md), [mongodb.md](mongodb.md), and [redis.md](redis.md).

## 4. Verify

```bash
docker compose ps                     # only the proxy shows 0.0.0.0 port bindings
ss -tlnp                              # host view: nothing else on public interfaces
curl -sI http://app.example.com/      # expect a redirect to https://
curl -s  https://app.example.com/api  # expect 401/403 without credentials
```

Test from a second machine on a different network where possible; the UFW bypass means testing the firewall from the host itself proves nothing about published ports.

## Sources (checked September 2026)

- Docker packet filtering and firewalls: https://docs.docker.com/engine/network/packet-filtering-firewalls/
- Compose networking: https://docs.docker.com/compose/how-tos/networking/
