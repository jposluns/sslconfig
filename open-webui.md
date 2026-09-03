# Open WebUI: signup control, TLS, and MFA

Open WebUI has account-based authentication built in; the risks are open signup on an exposed instance and running it on plain HTTP. It provides no TLS of its own, so encryption comes from a fronting layer.

## 1. Control who can register

Environment variables (defaults per the Open WebUI reference):

```
ENABLE_SIGNUP=false          # default true; disable once your accounts exist
DEFAULT_USER_ROLE=pending    # the default; new accounts wait for admin approval
                             # other values: user, admin
```

With signup left on, keep `DEFAULT_USER_ROLE=pending` so a stranger who registers gets no access until approved. An admin account can also be created at startup by setting `WEBUI_ADMIN_EMAIL` together with `WEBUI_ADMIN_PASSWORD` (supply the password via the environment, not a compose file in git; see [secrets.md](secrets.md)).

For SSO, the reference documents OAuth/OIDC settings plus `ENABLE_PASSWORD_AUTH=false` to turn off password login once SSO works; enforcing MFA then happens at the identity provider ([mfa.md](mfa.md)).

## 2. Bind privately and add TLS in front

```bash
docker run -d -p 127.0.0.1:3000:8080 ghcr.io/open-webui/open-webui:main
```

Publish it through [caddy.md](caddy.md)/[nginx.md](nginx.md) with a certificate from [free-certificates.md](free-certificates.md), or through a tunnel with login in front ([cloudflare.md](cloudflare.md), [tailscale.md](tailscale.md)). Never expose port 8080 directly: login forms over plain HTTP send passwords in cleartext.

## 3. Verify

```bash
ss -tlnp | grep 3000                      # loopback only
curl -sI https://chat.example.com/        # serves over TLS
# In a private browser window: login page appears; registering a new account
# yields a pending/unapproved user, not access.
```

## Sources (checked September 2026)

- Open WebUI environment configuration reference: https://docs.openwebui.com/reference/env-configuration
- Open WebUI repository: https://github.com/open-webui/open-webui
