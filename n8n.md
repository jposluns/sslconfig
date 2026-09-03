# n8n: binding, TLS, and MFA

n8n includes user management (complete the owner setup on first run), but its network defaults deserve attention: `N8N_LISTEN_ADDRESS` defaults to `::`, which listens on **all interfaces**, on port `5678` over plain HTTP.

## 1. Bind privately

Behind a reverse proxy or tunnel (the recommended layout):

```
N8N_LISTEN_ADDRESS=127.0.0.1
N8N_PORT=5678
N8N_HOST=n8n.example.com
```

Publish only the proxy per [caddy.md](caddy.md)/[nginx.md](nginx.md) with a certificate from [free-certificates.md](free-certificates.md), or use [cloudflare.md](cloudflare.md)/[tailscale.md](tailscale.md). Webhook endpoints are meant to be reachable by external services; that is no reason for the editor UI to be.

## 2. Or terminate TLS in n8n itself

```
N8N_PROTOCOL=https        # default is http
N8N_SSL_KEY=/path/to/privkey.pem
N8N_SSL_CERT=/path/to/fullchain.pem
```

## 3. Accounts and MFA

- Finish the owner-account setup immediately after first start; an unclaimed n8n instance is open to whoever reaches it first.
- Individual users can enable two-factor authentication on their accounts (verify availability for your version and licence).
- Instance-wide enforcement exists under **Settings > Security** ("Enforce two-factor authentication"), or via `N8N_MFA_ENFORCED_ENABLED=true` with `N8N_SECURITY_POLICY_MANAGED_BY_ENV=true`; per the n8n docs this enforcement requires a Business or Enterprise licence on self-hosted instances, and it does not apply to SSO logins (enforce MFA at the identity provider for those; [mfa.md](mfa.md)).
- Credentials stored in n8n (API keys for the services your workflows touch) make the instance a secrets vault; treat access to it accordingly ([secrets.md](secrets.md)).

## 4. Verify

```bash
ss -tlnp | grep 5678                    # 127.0.0.1, not :: or 0.0.0.0
curl -sI https://n8n.example.com/       # TLS, and a login page rather than the editor
```

## Sources (checked September 2026)

- n8n deployment environment variables (N8N_LISTEN_ADDRESS, N8N_PROTOCOL, N8N_SSL_KEY, N8N_SSL_CERT, defaults): https://docs.n8n.io/deploy/host-n8n/configure-n8n/basic-configuration/use-environment-variables/deployment.md
- n8n security policies (MFA enforcement, licensing, SSO exception): https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/manage-security-policies.md
- n8n SSL setup: https://docs.n8n.io/deploy/host-n8n/configure-n8n/security/set-up-ssl.md
