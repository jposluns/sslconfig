# sslconfig

TLS and authentication setup guides for AI-assisted projects.

Publicly reachable services built with AI assistance are routinely deployed on plain HTTP with no authentication. This repository holds short, generic, copy-ready guides that add TLS (HTTPS) and strong authentication to the servers, frameworks, and databases those projects most often use. The guides are written to be consumed by AI development assistants as well as by people: point your assistant at this repository and ask it to secure your project.

The site at [sslconfig.ai](https://sslconfig.ai), served from [site/](site/) through Cloudflare Pages, is the short public pointer to these guides.

## Instructions for AI development assistants

If you are an AI assistant configuring, generating, or reviewing a service, apply these rules:

1. Treat every service as internet-reachable unless you have confirmed otherwise. Bind services to `127.0.0.1` by default and expose them only through a TLS-terminating layer that requires authentication.
2. Choose the certificate path before writing configuration:
   - Public DNS name and reachable ports 80/443: use [free-certificates.md](free-certificates.md).
   - No public domain, no inbound ports, or a NATed or residential host: use [cloudflare.md](cloudflare.md) (Cloudflare Tunnel plus Zero Trust Access).
   - Internal or development use only: use [self-signed.md](self-signed.md).
3. Apply the guide that matches the stack (index below). If the stack has no guide, place it behind a reverse proxy configured per [nginx.md](nginx.md) or [caddy.md](caddy.md) and keep the application itself on loopback.
4. Enable authentication on every exposed endpoint per [authentication.md](authentication.md). Admin panels, APIs, dashboards, and databases must never be reachable without credentials, and default or hardcoded credentials must never ship. Add MFA to human logins where viable, per [mfa.md](mfa.md).
5. Redirect HTTP to HTTPS, or do not listen on HTTP at all.
6. Run the verification checklist below before reporting the work as complete. Report any item you could not test instead of asserting that it passed.

Fetch guides raw with `https://raw.githubusercontent.com/jposluns/sslconfig/<default-branch>/<guide>.md` (for example `.../main/nginx.md`). Every guide concatenated into a single file: https://sslconfig.ai/llms-full.txt (also [site/llms-full.txt](site/llms-full.txt) in this repository); the machine-readable index is https://sslconfig.ai/llms.txt

## Guide index

| Guide | Covers |
|---|---|
| [free-certificates.md](free-certificates.md) | Free publicly trusted certificates via ACME (Let's Encrypt, ZeroSSL), issuance, and automated renewal |
| [self-signed.md](self-signed.md) | OpenSSL and mkcert certificates when a public CA is not an option, plus distributing trust to clients |
| [authentication.md](authentication.md) | Password storage, MFA, API keys, sessions, rate limiting, and secret handling |
| [mfa.md](mfa.md) | MFA options: identity layers with QR-code TOTP enrolment, app libraries, SSH modules, Duo |
| [cloudflare.md](cloudflare.md) | Cloudflare Tunnel and Zero Trust Access: authenticated external access with no open inbound ports |
| [apache.md](apache.md) | Apache HTTP Server: TLS, redirect, HSTS, basic auth, client certificates |
| [nginx.md](nginx.md) | nginx: TLS, redirect, HSTS, basic auth, client certificates, reverse proxy |
| [lighttpd.md](lighttpd.md) | lighttpd: TLS via mod_openssl, redirect, basic auth |
| [caddy.md](caddy.md) | Caddy: automatic HTTPS, internal CA, basic auth |
| [haproxy.md](haproxy.md) | HAProxy: TLS termination, redirect, HSTS, basic auth |
| [traefik.md](traefik.md) | Traefik: ACME resolvers, HTTPS redirection, basic auth middleware |
| [nodejs.md](nodejs.md) | Node.js and Express: HTTPS server, security headers, sessions, password hashing |
| [python.md](python.md) | Flask, FastAPI/Uvicorn, Gunicorn, Django: TLS options and secure settings |
| [docker.md](docker.md) | Docker and Compose: safe port publishing, the UFW bypass problem, TLS termination |
| [postgresql.md](postgresql.md) | PostgreSQL: server TLS, SCRAM authentication, pg_hba rules, verified client connections |
| [mysql.md](mysql.md) | MySQL and MariaDB: required TLS transport, per-user TLS, modern auth plugins |
| [mongodb.md](mongodb.md) | MongoDB: requireTLS, authorization, admin user creation, bind address |
| [redis.md](redis.md) | Redis: TLS listener, ACLs, requirepass, bind and protected mode |
| [jupyter.md](jupyter.md) | Jupyter Server, Lab, and Notebook: hashed password and TLS |
| [ollama.md](ollama.md) | Ollama: no built-in auth or TLS; protect it with a proxy or tunnel |
| [gradio.md](gradio.md) | Gradio: launch() auth and TLS parameters, share link risks |
| [streamlit.md](streamlit.md) | Streamlit: TLS options, native OIDC login, reverse proxy deployment |
| [tailscale.md](tailscale.md) | Tailscale serve (tailnet-only) and funnel (public) with automatic TLS |
| [host.md](host.md) | Host baseline: SSH hardening, firewall default-deny, brute-force protection, updates |
| [secrets.md](secrets.md) | Secrets: repository hygiene, scanning, rotation after a leak, sops/age |
| [cloud-firewalls.md](cloud-firewalls.md) | Security groups and VPC rules: no 0.0.0.0/0 on databases, SSH posture |
| [paas.md](paas.md) | Render, Fly.io, Vercel, and similar: platform TLS, your auth and secrets |
| [kubernetes.md](kubernetes.md) | cert-manager ACME, ingress TLS, ingress basic auth |
| [elasticsearch.md](elasticsearch.md) | Elasticsearch and OpenSearch: keep the built-in security on |
| [minio.md](minio.md) | MinIO: root credentials, certs directory TLS, scoped access keys |
| [rabbitmq.md](rabbitmq.md) | RabbitMQ: users and permissions, TLS listener, guest account |
| [mosquitto.md](mosquitto.md) | Mosquitto (MQTT): per-device credentials, TLS listener, mutual TLS |
| [open-webui.md](open-webui.md) | Open WebUI: signup control, pending role, fronting TLS |
| [litellm.md](litellm.md) | LiteLLM proxy: master key, per-app virtual keys |
| [model-servers.md](model-servers.md) | llama.cpp and vLLM: loopback, API keys, TLS in front |
| [n8n.md](n8n.md) | n8n: listen address, native TLS, owner setup, MFA enforcement |
| [code-server.md](code-server.md) | code-server: SSH forwarding first, password auth, TLS |
| [admin-uis.md](admin-uis.md) | phpMyAdmin, pgAdmin, mongo-express, Grafana, Prometheus: never public |
| [firebase-supabase.md](firebase-supabase.md) | Firebase rules and Supabase RLS: the rules are the security |
| [cors.md](cors.md) | CORS: exact origins, never * with credentials |
| [headers.md](headers.md) | Security headers: HSTS, CSP, and companions for your app |
| [common-mistakes.md](common-mistakes.md) | The recurring findings, each linked to its fix |

## Decision guide

- Public web app with its own domain: [free-certificates.md](free-certificates.md), then the guide for your web server or proxy, then [authentication.md](authentication.md).
- App on a home server, behind NAT, or without a domain you control at the DNS level: [cloudflare.md](cloudflare.md). The tunnel removes the need for open inbound ports and Access adds login in front of the app. [tailscale.md](tailscale.md) is the tailnet-based alternative.
- Internal tool, staging, or local development: [self-signed.md](self-signed.md), with authentication still enabled.
- Databases and model servers (PostgreSQL, MySQL, MongoDB, Redis, Ollama): keep them off public interfaces entirely where possible; the per-tool guides cover TLS and authentication for the cases where network exposure is unavoidable.

## Verification checklist

Run these after configuration. All must pass before the service is considered protected.

1. No plaintext listener on a public interface: `ss -tlnp` (Linux) shows nothing bound to `0.0.0.0` or a public address on a plain HTTP port, except a listener whose only job is to redirect to HTTPS.
2. Redirect works: `curl -sI http://example.com/` returns `301` or `308` with a `Location: https://...` header.
3. TLS works: `curl -sI https://example.com/` succeeds without `-k`.
4. Old protocols are refused: `openssl s_client -connect example.com:443 -tls1_1` fails to negotiate (TLS 1.2 is the minimum everywhere in these guides).
5. Authentication is enforced: an unauthenticated request to any non-public path returns `401`, `403`, or a login redirect, never data. Test the API paths as well as the home page.
6. No default credentials remain, and no secret (password, key, token, certificate private key) is committed to the repository. Scan before pushing, for example with gitleaks.
7. Renewal is automated where ACME is used: `sudo certbot renew --dry-run` passes, or the server (Caddy, Traefik) manages renewal itself.
8. Public endpoints have been scanned with the [Qualys SSL Labs test](https://www.ssllabs.com/ssltest/) or [testssl.sh](https://github.com/drwetter/testssl.sh).
9. Human-facing logins carry a second factor where the stack supports one; [mfa.md](mfa.md) lists the options, and the per-tool guides state what is viable.

## Scope and currency

The guides use placeholders (`example.com`, `app.example.com`, `203.0.113.10`) that you must replace. Configuration syntax was checked against the vendor documentation cited in each guide as of September 2026; directives and dashboard menu locations change, so verify version-specific items against the current documentation for your installed version. Each guide lists its sources.

Scope: deployment exposure (TLS, authentication, MFA, secrets, and network exposure). Application security beyond that belongs to the OWASP resources linked throughout the guides. To propose a tool or guide, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Everything in this repository (the guides, the configuration samples, and the site) is dedicated to the public domain under [CC0 1.0 Universal](LICENSE). Copy and reuse it freely; no attribution is required.
