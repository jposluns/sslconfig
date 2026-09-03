# Streamlit: TLS and authentication

Streamlit apps have no access control unless you add it, and `streamlit run` listens on the network by default. Decide both layers before exposing an app.

## 1. TLS

Preferred: keep Streamlit on loopback and terminate TLS in a reverse proxy or tunnel ([caddy.md](caddy.md), [nginx.md](nginx.md), [cloudflare.md](cloudflare.md)):

```toml
# .streamlit/config.toml
[server]
address = "127.0.0.1"
```

Streamlit can serve HTTPS itself via `server.sslCertFile` and `server.sslKeyFile`, but its own documentation says not to use this in production ("It has not gone through security audits or performance tests") and to prefer a reverse proxy or load balancer. Treat the built-in TLS as a development convenience only:

```toml
[server]
sslCertFile = "/path/cert.pem"
sslKeyFile  = "/path/key.pem"
```

## 2. Native login (OIDC)

Recent Streamlit releases include `st.login()`, `st.logout()`, and `st.user` for OpenID Connect authentication against Google, Microsoft Entra ID, Okta, or any OIDC provider. Configuration lives in `.streamlit/secrets.toml`:

```toml
[auth]
redirect_uri = "https://app.example.com/oauth2callback"
cookie_secret = "REPLACE_WITH_LONG_RANDOM_STRING"
client_id = "<from your identity provider>"
client_secret = "<from your identity provider>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Gate the app at the top of the script:

```python
import streamlit as st

if not st.user.is_logged_in:
    st.login()
    st.stop()

st.write(f"Hello, {st.user.name}")
```

Notes from the Streamlit docs: this is authentication only (identity, not per-resource authorization), the identity cookie lasts 30 days and that period is not configurable, and `secrets.toml` holds the client secret, so it must never be committed. Confirm that your installed Streamlit version includes these functions; they are absent from older releases.

MFA: `st.login()` delegates authentication to the OIDC provider, so enforce MFA there (Google, Microsoft Entra ID, Okta, Keycloak, and authentik all support it). Without OIDC, front the app per section 3. Options in [mfa.md](mfa.md).

## 3. Alternatives when OIDC is not available

- Basic auth at a reverse proxy in front of a loopback-bound app ([nginx.md](nginx.md), [caddy.md](caddy.md)).
- Cloudflare Access in front of a tunnel ([cloudflare.md](cloudflare.md)), which adds SSO or one-time-PIN login without touching the app.

A password typed into a plain `st.text_input` and compared in the script is not authentication; it ships no session management, no hashing, and no rate limiting.

## 4. Verify

```bash
ss -tlnp | grep 8501                     # 127.0.0.1 when behind a proxy
curl -sI https://app.example.com/        # succeeds over TLS
# In a private browser window: the IdP login (or proxy auth) appears before the app.
```

## Sources (checked September 2026)

- config.toml reference (server.address, server.sslCertFile, server.sslKeyFile, and the production warning): https://docs.streamlit.io/develop/api-reference/configuration/config.toml
- Authentication concepts (st.login, st.logout, st.user, [auth] keys, stated limitations): https://docs.streamlit.io/develop/concepts/connections/authentication
