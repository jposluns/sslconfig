# Tailscale: serve and funnel

Tailscale gives the same no-open-inbound-ports posture as [cloudflare.md](cloudflare.md), built on WireGuard with device identity as the access control. Two commands matter, and they differ in exactly one thing: who can reach the service.

## 1. tailscale serve: tailnet-only (authenticated by membership)

```bash
tailscale serve --bg localhost:3000
```

- Reachable only by devices in your tailnet, so access is authenticated by device identity and your tailnet ACLs.
- HTTPS uses an automatically provisioned TLS certificate for the machine's tailnet name.
- `--bg` keeps it running in the background; without it, the share stops with the session.

This is the right default for admin panels, dashboards, Jupyter, and internal tools: no certificate work, no public exposure at all.

## 2. tailscale funnel: public internet (bring your own auth)

```bash
tailscale funnel 3000
```

- Publishes the service to the entire internet at your `*.ts.net` hostname, TLS included.
- Funnel itself adds **no per-request authentication**; the relay does not even decrypt your traffic. Anything funneled needs application-level login per [authentication.md](authentication.md) and, for human logins, [mfa.md](mfa.md), exactly as if it sat behind any public proxy.
- Prerequisites per the docs: HTTPS certificates enabled for the tailnet, a `funnel` node attribute in the tailnet policy file, and MagicDNS.

## 3. Choosing between them

Serve for anything private (most things). Funnel or [cloudflare.md](cloudflare.md) for genuinely public services; Cloudflare Access adds managed login in front, which funnel does not, so prefer Access when the public service is for a defined set of people. Command syntax changed in Tailscale v1.52; on older clients consult `tailscale serve --help`.

## 4. Verify

```bash
tailscale serve status
curl -sI https://<machine>.<tailnet>.ts.net/     # from a tailnet device: works
# From a non-tailnet network: serve URL unreachable; funnel URL reachable, so its app login must gate it.
```

## Sources (checked September 2026)

- Tailscale serve: https://tailscale.com/kb/1242/tailscale-serve
- Tailscale funnel: https://tailscale.com/kb/1223/funnel
