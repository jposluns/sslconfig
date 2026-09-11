# Self-hosted chat and agent UIs: AnythingLLM, LobeChat, Chainlit, OpenHands

These tools hold provider API keys and full conversation history, and several are wide open the moment they start. Bind every one to loopback, front it with TLS and a login ([caddy.md](caddy.md)/[nginx.md](nginx.md), [free-certificates.md](free-certificates.md)), and turn on the tool's own authentication as a second layer, never as a substitute for the network boundary. See also [open-webui.md](open-webui.md) for the Open WebUI case, [secrets.md](secrets.md) for the provider keys these apps store, and [fronting-auth.md](fronting-auth.md)/[mfa.md](mfa.md) for the identity layer in front.

## AnythingLLM

Security features apply to the Docker deployment. Single-user mode offers an optional "Password Protect Instance" toggle: once set, anyone with that one password can use the instance, change any setting, and read every chat, so treat it as a screen door, not a real access-control boundary. Multi-user mode is the documented preferred setup: it adds Admin (full access including logs and analytics), Manager (all workspaces, no LLM/embedder/vector-database settings), and Default (only explicitly assigned workspaces) roles, each requiring its own login. Multi-user mode cannot be reverted to single-user once enabled, so decide before turning it on.

```bash
docker run -d -p 127.0.0.1:3001:3001 mintplexlabs/anythingllm
```

Keep it on loopback regardless of which mode you choose, and put the proxy's own TLS and login in front.

## LobeChat

`KEY_VAULTS_SECRET` is the key that encrypts stored provider credentials (AES-GCM); generate it with `openssl rand -base64 32`, and once set, never change it, or previously encrypted data becomes unreadable. LobeHub's own basic-variables page describes it loosely as "a password to access the LobeHub service", but its own warning on the same entry says the key is used to encrypt sensitive data: treat it as the encryption key, not the deployment's login gate. Real per-user login comes from LobeChat's Better Auth service: `AUTH_SECRET` (required, generated the same way) signs sessions, `AUTH_SSO_PROVIDERS` lists enabled SSO providers (for example `google,github,microsoft`) alongside the matching provider credentials each one needs (for example `AUTH_GOOGLE_ID`/`AUTH_GOOGLE_SECRET`), and `AUTH_DISABLE_EMAIL_PASSWORD=1` forces SSO-only login, hiding the password form entirely. `AUTH_ALLOWED_EMAILS` restricts registration to specific addresses or domains, but it defaults to empty, which allows every email through, so set it explicitly rather than relying on federation alone to gate access.

```bash
docker run -d -p 127.0.0.1:3210:3210 \
  -e KEY_VAULTS_SECRET=REPLACE_WITH_LONG_RANDOM_VALUE \
  -e AUTH_SECRET=REPLACE_WITH_LONG_RANDOM_VALUE \
  -e AUTH_DISABLE_EMAIL_PASSWORD=1 \
  -e AUTH_SSO_PROVIDERS=google \
  -e AUTH_GOOGLE_ID=REPLACE_WITH_GOOGLE_OAUTH_CLIENT_ID \
  -e AUTH_GOOGLE_SECRET=REPLACE_WITH_GOOGLE_OAUTH_CLIENT_SECRET \
  -e AUTH_ALLOWED_EMAILS=admin@example.com,example.com \
  lobehub/lobe-chat
```

MFA: enforce it at whichever SSO provider you list in `AUTH_SSO_PROVIDERS`; LobeChat's own login has no second factor of its own.

## Chainlit

Chainlit applications are public by default: no login, no gate, anyone who reaches the port gets the chat. Set `CHAINLIT_AUTH_SECRET` (generate one with `chainlit create-secret`; changing it logs out every user) and implement at least one auth callback: password authentication, OAuth, or header-based authentication. A callback that returns `None` refuses the login. There is no built-in MFA; put it behind an identity provider that enforces a second factor, or an [Authelia](https://www.authelia.com/)-fronted proxy.

```python
import chainlit as cl

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    if username == "admin" and password == "REPLACE_WITH_LONG_RANDOM_VALUE":
        return cl.User(identifier="admin")
    return None
```

## OpenHands

OpenHands is built for a single user on their own workstation: the project's own FAQ states there is no built-in authentication, isolation, or scalability for shared use, and the open-source build authorizes API access with one shared key rather than per-user identity. It also executes agent-generated code against your workspace, with the isolation depending entirely on your deployment choice (a local process backend runs with your user's permissions; container backends can be weakened by broad mounts, privileged mode, or Docker-socket access). Do not expose it to anyone you would not hand a shell to. The project documents a Hardened Docker Installation guide for deployments that must sit on a shared network; multi-tenant use is an enterprise offering, not something the open-source build supports.

The documented quickstart itself runs `docker run ... -p 3000:3000 ... openhands/openhands`, which maps every interface, not loopback; change that to `-p 127.0.0.1:3000:3000` before anything else. Reach it only through an authenticated tunnel; there is no login screen to add in front of it, so identity has to come entirely from the proxy or tunnel layer.

## Verify

```bash
ss -tlnp | grep -E '3001|3210|3000'                    # each UI on 127.0.0.1 only
curl -s http://203.0.113.10:3210/                       # from another host: connection refused
curl -s https://chat.example.com/api/some-endpoint      # without a key/token: 401
curl -sI https://chat.example.com/                      # via the proxy: TLS, login required
# LobeChat SSO: attempt to register/sign in with a Google account that has never registered and is
#   NOT listed in AUTH_ALLOWED_EMAILS; expect rejection at registration, before any account or session
#   is created (AUTH_ALLOWED_EMAILS gates new registration; it does not revoke an already-registered
#   user's existing session)
```

## Common mistakes

- Leaving Chainlit unauthenticated because "it's just for testing"; public by default means public the moment it is reachable.
- Treating AnythingLLM's single instance password as equivalent to per-user accounts; it grants full admin to whoever has it.
- Running OpenHands with a shared, long-lived API key exposed on the same network as untrusted users.
- Rotating LobeChat's `KEY_VAULTS_SECRET` after data has been encrypted with it, which makes that data unreadable.

## Sources (checked September 2026)

- AnythingLLM security and access documentation: https://docs.anythingllm.com/features/security-and-access
- LobeHub environment variables (KEY_VAULTS_SECRET): https://lobehub.com/docs/self-hosting/environment-variables/basic
- LobeHub authentication service environment variables (Better Auth): https://lobehub.com/docs/self-hosting/environment-variables/auth
- Chainlit authentication overview: https://docs.chainlit.io/authentication/overview
- Chainlit password authentication (`@cl.password_auth_callback` signature and example): https://docs.chainlit.io/authentication/password
- OpenHands FAQs (single-user design, no built-in auth, sandboxing, hardened deployment): https://docs.openhands.dev/openhands/usage/faqs
- OpenHands local setup (default docker port mapping): https://docs.openhands.dev/openhands/usage/run-openhands/local-setup
