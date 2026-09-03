# Cloudflare Tunnel and Zero Trust Access

This is the recommended path when the host cannot or should not accept inbound connections: home labs, NATed machines, cloud VMs you want to keep closed, and any project without its own TLS setup. `cloudflared` opens an outbound-only tunnel to Cloudflare's edge, the edge serves your hostname over HTTPS with a Cloudflare-managed certificate, and Cloudflare Access places authentication (SSO or emailed one-time PIN) in front of the app without any application changes. No inbound firewall ports are opened at all.

## 1. Prerequisites

- A domain added to Cloudflare (the free plan is sufficient), with Cloudflare as its DNS.
- A Zero Trust organization on the account. At the time of writing the free tier covers up to 50 users; verify current limits at https://www.cloudflare.com/plans/zero-trust-services/
- `cloudflared` installed on the host that can reach the service (packages for Linux, macOS, and Windows: https://github.com/cloudflare/cloudflared).

## 2. Create the tunnel (dashboard-managed, recommended)

Per the Cloudflare docs as of June 2026 (menu locations change; the sources below are authoritative):

1. In the Cloudflare dashboard go to **Networking > Tunnels** and create a tunnel (connector type `cloudflared`).
2. Copy the installation command the dashboard shows for your OS and run it on the host. It embeds a tunnel token and installs `cloudflared` as a service (`cloudflared service install <TOKEN>` on Linux).
3. Add a route: **Routes > Add route > Published application**, choose the subdomain (for example `app.example.com`), and set the service URL to the local service, for example `http://localhost:3000`.

The app is now reachable at `https://app.example.com` over TLS terminated at Cloudflare's edge. Traffic between `cloudflared` and Cloudflare travels inside the encrypted tunnel; the `http://localhost:3000` hop stays on the host itself.

## 3. CLI alternative (locally-managed tunnel)

```bash
cloudflared tunnel login
cloudflared tunnel create myapp
cloudflared tunnel route dns myapp app.example.com
```

`~/.cloudflared/config.yml`:

```yaml
tunnel: <TUNNEL-UUID>
credentials-file: /home/user/.cloudflared/<TUNNEL-UUID>.json
ingress:
  - hostname: app.example.com
    service: http://localhost:3000
  - service: http_status:404
```

Run with `cloudflared tunnel run myapp`, or install it as a service with `sudo cloudflared service install`. The credentials JSON and the tunnel token are secrets: they let anyone publish services on your hostname, so keep them out of repositories.

## 4. Add authentication with Access

A tunnel publishes the app; Access is what makes it authenticated. In the Zero Trust dashboard:

1. Go to the **Access > Applications** section and add a **self-hosted** application for `app.example.com`.
2. Create an **Allow** policy. Sensible starting rules: `Emails` listing specific addresses, or `Emails ending in` your domain.
3. Choose login methods. The built-in **One-time PIN** (a code emailed to the allowed address) works with zero identity-provider setup; connect Google, GitHub, Microsoft Entra ID, or another IdP for SSO and MFA.

Every request to the hostname now hits a Cloudflare login page first; only identities matching the policy reach the app.

MFA: the emailed one-time PIN proves control of a mailbox only. For anything sensitive, connect an identity provider and enforce MFA there; Access then inherits it. Broader options: [mfa.md](mfa.md).

For APIs and machine clients, create a **service token** in the Zero Trust dashboard (Access service authentication section), add a **Service Auth** policy to the application, and send the token with each request:

```bash
curl -H "CF-Access-Client-Id: <id>" \
     -H "CF-Access-Client-Secret: <secret>" \
     https://app.example.com/api
```

## 5. Close the side doors

- Bind the application to `127.0.0.1` so the tunnel is the only path to it. If the app also listens publicly, Access is decorative.
- Do not use quick tunnels (`cloudflared tunnel --url http://localhost:3000`, the random `trycloudflare.com` URLs) for anything real: they are unauthenticated and intended for short-lived testing.
- If the origin must sit on a different machine from `cloudflared`, run TLS on that hop too (`service: https://...`; see [self-signed.md](self-signed.md)).
- Related but distinct: for a directly-exposed origin behind Cloudflare's proxy (no tunnel), install a free **Cloudflare origin certificate** on the server and set the zone's TLS mode to **Full (strict)**. Origin certificates are trusted only by Cloudflare's edge, never by browsers directly.

## 6. Verify

- A private-browsing visit to `https://app.example.com` shows the Access login page, not the app.
- `curl -sI https://app.example.com/` returns a redirect to the Access login, not application content.
- With a service token, the same request returns application content.
- `ss -tlnp` on the host shows the app bound to `127.0.0.1` only, and your firewall shows no inbound rule added for it.

## Sources (checked September 2026)

- Cloudflare Zero Trust documentation: https://developers.cloudflare.com/cloudflare-one/
- Create a remotely-managed tunnel: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/
- cloudflared releases: https://github.com/cloudflare/cloudflared
