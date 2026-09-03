# code-server: browser VS Code without giving away the machine

code-server runs a terminal in the browser, so exposure equals remote code execution. Its own documentation is blunt: never expose it directly to the internet without authentication and encryption.

## 1. Prefer no exposure at all

The code-server docs recommend SSH port forwarding first, which needs no additional setup:

```bash
ssh -L 8080:127.0.0.1:8080 user@host    # then open http://localhost:8080 locally
```

[tailscale.md](tailscale.md) (serve, tailnet-only) and [cloudflare.md](cloudflare.md) (tunnel plus Access with MFA) are the equivalents when SSH is unavailable.

## 2. If it must be reachable: config.yaml

`~/.config/code-server/config.yaml`:

```yaml
bind-addr: 127.0.0.1:8080     # keep loopback behind a proxy or tunnel
auth: password                # default; the generated password lives in this file
cert: /path/to/fullchain.pem  # only when code-server terminates TLS itself
cert-key: /path/to/privkey.pem
```

Password attempts are rate-limited (2 per minute plus 12 per hour). Replace the generated password with your own long random value, and treat the config file as a secret ([secrets.md](secrets.md)). For public access, the docs' supported pattern is a reverse proxy with a real certificate: [caddy.md](caddy.md) or [nginx.md](nginx.md) with [free-certificates.md](free-certificates.md), with MFA added at that layer ([mfa.md](mfa.md)) since the built-in login is a single factor.

## 3. Verify

```bash
ss -tlnp | grep 8080                    # loopback only
curl -sI https://code.example.com/      # TLS, login page, never the editor
```

An unauthenticated editor in a private browser window means whoever finds the URL owns the host.

## Sources (checked September 2026)

- code-server deployment guide (config.yaml keys, password auth and rate limits, exposure recommendations): https://coder.com/docs/code-server/guide
- code-server repository: https://github.com/coder/code-server
