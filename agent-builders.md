# Agent and workflow builders: Dify, Flowise, Langflow, LibreChat

Each of these tools stores your provider API keys (OpenAI, Anthropic, and the rest) and exposes both an editor UI and callable APIs, so an open instance is a secrets vault plus free compute for whoever finds it. All four ship with login of some kind; the exposure comes from skipping the first-run setup, leaving default secrets in place, and publishing the container port on every interface over plain HTTP. None of them offers a native second factor that this guide can rely on, so MFA comes from an OIDC provider (where the tool supports OIDC) or from the fronting layer ([mfa.md](mfa.md)).

## 1. Bind privately

Publish the container on loopback and let a proxy or tunnel be the only public listener ([docker.md](docker.md)):

```yaml
ports:
  - "127.0.0.1:3000:3000"    # Flowise (PORT defaults to 3000)
  - "127.0.0.1:7860:7860"    # Langflow (LANGFLOW_PORT defaults to 7860)
  - "127.0.0.1:3080:3080"    # LibreChat (PORT defaults to 3080)
```

Dify is different: its Compose file publishes nginx on `EXPOSE_NGINX_PORT=80` and `EXPOSE_NGINX_SSL_PORT=443` from `docker/.env`, plus the plugin daemon's `EXPOSE_PLUGIN_DEBUGGING_PORT=5003` (optional vector store profiles publish more). Do not hide a published port with the host firewall: Docker's NAT rules divert the traffic before it reaches the chains UFW uses, so a UFW deny on a published port does nothing ([docker.md](docker.md)). The plugin daemon's debugging port is only needed for remote plugin debugging, so leave it unpublished: do not enable the debugging feature, or remove that port mapping in a Compose override. Leave the backend services unpublished on the Compose network, and make Dify's nginx the only service with a public port: either as the TLS edge (section 2) or on loopback (`EXPOSE_NGINX_PORT=127.0.0.1:8080`) behind your own proxy.

## 2. TLS

Flowise and LibreChat document no TLS of their own; their deployment guides put nginx with certbot in front (`proxy_pass http://localhost:3000` and `http://localhost:3080` respectively). Use [caddy.md](caddy.md) or [nginx.md](nginx.md) with a certificate from [free-certificates.md](free-certificates.md), or [cloudflare.md](cloudflare.md) / [tailscale.md](tailscale.md) with no public port at all. Set `NUMBER_OF_PROXIES` (Flowise) and `TRUST_PROXY` (LibreChat, default `1`) to the number of proxy hops so rate limiting sees client addresses.

Langflow can terminate TLS itself with `LANGFLOW_SSL_CERT_FILE` and `LANGFLOW_SSL_KEY_FILE`; a fronting proxy remains the simpler place to add login and MFA.

Dify's bundled nginx can terminate TLS. In `docker/.env`, per the certbot README in the Dify repository: set `NGINX_ENABLE_CERTBOT_CHALLENGE=true`, `CERTBOT_DOMAIN`, `CERTBOT_EMAIL`, `NGINX_SSL_CERT_FILENAME=fullchain.pem`, `NGINX_SSL_CERT_KEY_FILENAME=privkey.pem`; run `docker compose --profile certbot up --force-recreate -d` and `docker compose exec -it certbot /bin/sh /update-cert.sh`; then set `NGINX_HTTPS_ENABLED=true` (default `false`) and recreate nginx with `docker compose --profile certbot up -d --no-deps --force-recreate nginx`. `NGINX_SSL_PROTOCOLS` defaults to `TLSv1.2 TLSv1.3`. Set `CONSOLE_API_URL`, `CONSOLE_WEB_URL`, and `APP_WEB_URL` to the public `https://` URLs; per the Dify reference, `CONSOLE_API_URL` decides whether cookies are marked HTTPS-only.

## 3. Dify

```bash
cd dify/docker && cp .env.example .env
# edit .env now: INIT_PASSWORD, SECRET_KEY, the EXPOSE_* bindings (section 1), the public URLs (section 2)
docker compose up -d
```

- `INIT_PASSWORD=REPLACE_WITH_LONG_RANDOM_VALUE` goes into `.env` before the first `up`. It is empty by default; when set, the `/install` page demands it before anyone can create the admin account. Once the stack is up, open `https://dify.example.com/install` yourself, immediately.
- Set `SECRET_KEY` from `openssl rand -base64 42`. It signs session cookies and JWTs and encrypts stored OAuth credentials (left empty, Dify auto-generates one in its storage directory, per `.env.example`).
- App API keys are created inside each app and sent as `Authorization: Bearer <key>` to the service API. They are not console accounts, so tightening console login does nothing for a leaked key. Dify's guidance: call the API from your backend only; a key in frontend code can be extracted.

## 4. Flowise

- From v3.0.1 onwards Flowise uses email-and-password accounts with JWTs in HTTP-only cookies. `FLOWISE_USERNAME` / `FLOWISE_PASSWORD` are documented as deprecated; the docs use them only to migrate an older instance into a new admin account. Register the admin account before exposing the instance.
- Set random values for `JWT_AUTH_TOKEN_SECRET`, `JWT_REFRESH_TOKEN_SECRET`, `EXPRESS_SESSION_SECRET` (default `flowise`), and `TOKEN_HASH_SECRET`; set `APP_URL` to the public URL (default `http://localhost:3000`). `FLOWISE_SECRETKEY_OVERWRITE` sets the key that encrypts stored credentials; without it the key lives in a file under `SECRETKEY_PATH`.
- Prediction endpoints: a chatflow with no API key assigned is public to anyone who knows the chatflow ID. Create keys under **API Keys** (a `DefaultKey` is pre-created), assign one per chatflow, and clients send `Authorization: Bearer <key>`; the prediction API answers `401` without it.

## 5. Langflow

```
LANGFLOW_AUTO_LOGIN=false
LANGFLOW_SUPERUSER=REPLACE_WITH_ADMIN_USERNAME
LANGFLOW_SUPERUSER_PASSWORD=REPLACE_WITH_LONG_RANDOM_VALUE
LANGFLOW_SECRET_KEY=REPLACE_WITH_LONG_RANDOM_VALUE
```

- `LANGFLOW_AUTO_LOGIN` defaults to `True` in the application (the official Docker images set it to `false`), which means no login at all; set it to `false` explicitly. The password is then required and cannot be the legacy default `langflow`; the username defaults to `langflow`.
- Generate the key with `python3 -c "from secrets import token_urlsafe; print(f'LANGFLOW_SECRET_KEY={token_urlsafe(32)}')"`. An auto-generated key is documented as unsuitable for production.
- `LANGFLOW_NEW_USER_IS_ACTIVE` defaults to `False`: new accounts wait for the superuser to activate them. Keep it.
- With auto-login off, API calls (`POST /api/v1/run/<flow-id>`) need a Langflow API key in the `x-api-key` header, created under **Settings > Langflow API Keys** or with `langflow api-key`. `LANGFLOW_SKIP_AUTH_AUTO_LOGIN` (default `false`) only applies when auto-login is on and is slated for removal; leave it alone.
- `LANGFLOW_HOST` defaults to `localhost`; that is the right value behind a proxy on the same host. Version note: checked against the 1.12.x docs.

## 6. LibreChat

- The first registered account becomes the admin. Register it, then set `ALLOW_REGISTRATION=false` so nobody else can create an email account. For SSO-only operation, also set `ALLOW_EMAIL_LOGIN=false` and enable `ALLOW_SOCIAL_REGISTRATION=true` deliberately, with the provider's allowlist deciding who may exist.
- `ALLOW_SOCIAL_LOGIN=true` enables the OAuth2 providers (Apple, Discord, Facebook, GitHub, Google) and OIDC through `OPENID_ISSUER`, `OPENID_CLIENT_ID`, `OPENID_CLIENT_SECRET`, `OPENID_SESSION_SECRET`, `OPENID_SCOPE="openid profile email"`, `OPENID_CALLBACK_URL=/oauth/openid/callback`, optionally `OPENID_REQUIRED_ROLE`. The docs cover Keycloak, Authentik, Authelia, Auth0, Cognito, and Entra; with OIDC in place, set `ALLOW_EMAIL_LOGIN=false` and enforce MFA at the provider ([identity-providers.md](identity-providers.md), [oidc-integration.md](oidc-integration.md)).
- `CREDS_KEY` is a 32-byte key (64 hexadecimal characters) and `CREDS_IV` a 16-byte IV (32 hexadecimal characters); `JWT_SECRET` and `JWT_REFRESH_SECRET` are unique random values of at least 32 bytes each. The docs point to the Credentials Generator. Never keep the `.env.example` values.
- Set `DOMAIN_CLIENT` and `DOMAIN_SERVER` to the public `https://` URL. TLS comes from the fronting proxy (section 2).
- The v0.7.7 changelog lists two-factor authentication with backup codes and QR enrolment, but the authentication documentation we checked does not describe it, so do not count on it as the enforced control; MFA at the OIDC provider is the documented path.

## 7. MFA and stored secrets

None of the four documents instance-wide MFA enforcement. Where OIDC exists (LibreChat), enforce MFA at the provider; for Dify, Flowise, and Langflow put the editor behind Cloudflare Access or an identity layer per [mfa.md](mfa.md). Every provider key pasted into these tools is a secret held by the tool; rotate any key that lived on an instance that was ever open ([secrets.md](secrets.md)).

## Verify

```bash
ss -tlnp | grep -E ':(3000|7860|3080|80|443) '        # app ports on 127.0.0.1; 80/443 public only where Dify's own nginx is the TLS edge
curl -sI https://builder.example.com/                  # TLS; login page or redirect, not the editor
curl -s -o /dev/null -w '%{http_code}\n' -X POST 'https://flowise.example.com/api/v1/prediction/REPLACE_WITH_CHATFLOW_ID'   # 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST 'https://langflow.example.com/api/v1/run/REPLACE_WITH_FLOW_ID'            # 401
curl -s -o /dev/null -w '%{http_code}\n' https://dify.example.com/v1/parameters                              # 401
```

## Common mistakes

- Starting Dify without `INIT_PASSWORD` on a reachable host: the first visitor to `/install` owns the instance.
- Running Langflow with the default `LANGFLOW_AUTO_LOGIN=True`, which is no login.
- A Flowise chatflow with no API key assigned: the prediction API is public to anyone with the ID.
- Leaving LibreChat registration open after the admin exists, or shipping the example `JWT_SECRET`.

## Sources (checked September 2026)

- Dify Docker Compose deployment (setup at `/install`): https://docs.dify.ai/en/self-host/deploy/quick-start/docker-compose
- Dify environment variables (`SECRET_KEY`, `INIT_PASSWORD`, `CONSOLE_API_URL`, `CONSOLE_WEB_URL`, `APP_WEB_URL`): https://docs.dify.ai/en/self-host/deploy/configuration/environments
- Dify `docker/.env.example` (`EXPOSE_NGINX_PORT`, `NGINX_HTTPS_ENABLED`, certificate variables): https://github.com/langgenius/dify/blob/main/docker/.env.example ; `docker-compose.yaml` (which services publish ports): https://github.com/langgenius/dify/blob/main/docker/docker-compose.yaml
- Docker packet filtering and firewalls (published ports bypass UFW): https://docs.docker.com/engine/network/packet-filtering-firewalls/
- Dify certbot README (HTTPS steps): https://github.com/langgenius/dify/blob/main/docker/certbot/README.md
- Dify API keys (Bearer, backend-only): https://docs.dify.ai/en/api-reference/guides/get-started
- Flowise app-level authentication (v3.0.1 accounts, deprecated username/password, JWT secrets): https://docs.flowiseai.com/configuration/authorization/app-level
- Flowise chatflow-level API keys: https://docs.flowiseai.com/configuration/authorization/chatflow-level
- Flowise environment variables (`PORT`, `NUMBER_OF_PROXIES`, `FLOWISE_SECRETKEY_OVERWRITE`): https://docs.flowiseai.com/configuration/environment-variables
- Flowise prediction API (401 without key): https://docs.flowiseai.com/api-reference/prediction
- Flowise deployment with nginx and certbot: https://docs.flowiseai.com/configuration/deployment/digital-ocean
- Langflow API keys and authentication: https://docs.langflow.org/api-keys-and-authentication
- Langflow environment variables (`LANGFLOW_HOST`, `LANGFLOW_PORT`, SSL files): https://docs.langflow.org/environment-variables
- Langflow production best practices (`LANGFLOW_SECRET_KEY` preflight): https://docs.langflow.org/deployment-prod-best-practices
- LibreChat `.env` reference: https://www.librechat.ai/docs/configuration/dotenv
- LibreChat authentication system: https://www.librechat.ai/docs/configuration/authentication
- LibreChat OAuth2 and OIDC overview: https://www.librechat.ai/docs/configuration/authentication/OAuth2-OIDC
- LibreChat Keycloak setup (`OPENID_*` variables): https://www.librechat.ai/docs/configuration/authentication/OAuth2-OIDC/keycloak
- LibreChat Docker install (port 3080, first account is admin): https://www.librechat.ai/docs/local/docker
- LibreChat nginx and TLS: https://www.librechat.ai/docs/remote/nginx
- LibreChat v0.7.7 changelog (two-factor authentication): https://www.librechat.ai/changelog/v0.7.7
