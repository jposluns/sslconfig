# Redis: TLS and authentication

Redis trusts its network by design, so the network boundary and credentials are your job. An exposed unauthenticated Redis leaks its data, and historic attack tooling has also used the CONFIG command against open instances to write files and take over hosts. Applies to Redis 6.0 and later (TLS and ACLs); the server must be built with TLS support, which mainstream distribution packages include (Redis refuses to start with TLS directives present if the build lacks it).

## 1. Keep it local unless remote access is deliberate

In `redis.conf`:

```
bind 127.0.0.1 -::1
protected-mode yes
```

`protected-mode` blocks non-loopback clients when no password/ACL is set; treat it as a backstop, not as the control.

## 2. Require a credential

Minimum (single shared password, sent by clients with `AUTH`):

```
requirepass REPLACE_WITH_LONG_RANDOM_PASSWORD
```

Better, per-service ACL users with least privilege (Redis 6 and later):

```
user app on >REPLACE_WITH_LONG_RANDOM_PASSWORD ~app:* +@read +@write
```

That grants the `app` user access to keys matching `app:*` with read and write command categories only. Generate passwords per [authentication.md](authentication.md). Disable the `default` user (`user default off`) only after every client authenticates as a named user, or you will lock services out.

MFA: Redis has no second-factor dialogue; `tls-auth-clients yes` (mutual TLS, below) is the second factor for clients, and human paths to the host go behind MFA per [mfa.md](mfa.md).

## 3. Enable TLS

Get a certificate ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)), then replace the plaintext port with a TLS listener:

```
port 0                     # no plaintext listener at all
tls-port 6379
tls-cert-file    /etc/redis/tls/server.crt
tls-key-file     /etc/redis/tls/server.key
tls-ca-cert-file /etc/redis/tls/ca.crt
tls-auth-clients no        # yes = require client certificates (mutual TLS)
```

Set `tls-auth-clients yes` for machine-to-machine deployments where clients can hold certificates; it is stronger than passwords alone.

## 4. Client side

```bash
redis-cli --tls --cacert /etc/redis/tls/ca.crt -h redis.example.com -p 6379
> AUTH app REPLACE_WITH_PASSWORD
> PING
```

Application clients take equivalent TLS and credential options; point them at the CA rather than disabling verification.

## 5. Verify

```bash
ss -tlnp | grep 6379                          # loopback only, unless remote access is deliberate
redis-cli -h redis.example.com ping           # plaintext attempt: fails once port 0 is set
redis-cli --tls --cacert ca.crt -h redis.example.com ping   # NOAUTH error until AUTH succeeds
```

## Common mistakes

- Commenting out `bind` (which listens everywhere) while `requirepass` is still empty.
- One `requirepass` value shared across environments and committed to the repository.
- TLS enabled but the plaintext `port` left open alongside it; set `port 0`.

## Sources (checked September 2026)

- Redis documentation (security, TLS, and ACL pages): https://redis.io/docs/latest/
- redis.conf self-documented example in the Redis source distribution: https://github.com/redis/redis
