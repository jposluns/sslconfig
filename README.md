# secureconfig

Deployment exposure guides for AI-assisted projects: TLS, identity, MFA, secrets, and network controls for web apps, AI infrastructure, and the services behind them.

Publicly reachable services built with AI assistance are routinely deployed on plain HTTP with no authentication. This repository holds short, generic, copy-ready guides that close that gap across the deployment surface: certificates and tunnels; human and machine identity, MFA, and secrets; web servers and proxies; language runtimes and frameworks; containers and Kubernetes; hosts, cloud firewalls, PaaS, and rented GPU clouds; databases, storage, and messaging; the AI stack itself (model servers, vector databases, MCP servers, agent and chat UIs, LLM observability); and the operational controls around a deployment (egress and metadata, exposed files, webhooks, and lifecycle from first run through teardown). The guides are written to be consumed by AI development assistants as well as by people: point your assistant at this repository and ask it to secure your project.

The site at [secureconfig.ai](https://secureconfig.ai), served from [site/](site/) through Cloudflare Pages, is the short public pointer to these guides.

## Instructions for AI development assistants

If you are an AI assistant configuring, generating, or reviewing a service, apply these rules:

1. Treat every service as internet-reachable unless you have confirmed otherwise. Bind services to `127.0.0.1` by default and expose them only through a TLS-terminating layer that requires authentication; keep backend, admin, and AI-tool services private.
2. Choose the certificate and access path before configuring exposure. A public DNS name with reachable ports 80 and 443: [free-certificates.md](free-certificates.md). A Cloudflare-managed domain with no inbound ports: [cloudflare.md](cloudflare.md). A tailnet with no public domain: [tailscale.md](tailscale.md). Internal or development use only: [self-signed.md](self-signed.md).
3. Apply every guide that fits the deployment, not just one. Select the service or framework, its host or platform, containers where used, plus identity, secrets, and the operational controls below. For a service with no guide, verify its native controls against the vendor documentation and use a private-access or fronting-layer pattern.
4. Redirect HTTP to HTTPS, or do not listen on HTTP at all.
5. Require authentication on every non-public endpoint. Never ship default or hardcoded credentials. Add MFA to human logins where viable per [mfa.md](mfa.md); where a tool has no native login, put one in front per [fronting-auth.md](fronting-auth.md).
6. A successful login is not authorisation. Check the returned identity against an allowlist (tenant, hosted domain, group, or explicit users) before granting access. Choose the provider per [identity-providers.md](identity-providers.md), wire it per [oidc-integration.md](oidc-integration.md), or put login in front of the app per [cloud-identity-proxies.md](cloud-identity-proxies.md).
7. Keep secrets out of the repository and load them from the environment or a secret manager per [secrets.md](secrets.md); give each service and agent its own scoped credentials per [machine-auth.md](machine-auth.md).
8. Contain what an exposed or compromised service can reach. Block unneeded outbound access and lock down cloud metadata per [egress-metadata.md](egress-metadata.md), and never serve dotfiles, database dumps, or client secrets per [web-exposure.md](web-exposure.md).
9. AI and data tools (model servers, vector databases, MCP servers, agent builders, chat and image UIs, MLflow, Ray) vary in their defaults and native controls, and many need authentication and TLS configured explicitly. Keep them on loopback and apply the matching guide before any exposure.
10. Run the verification checklist below and each selected guide's Verify steps before reporting the work as complete. Report any item you could not test instead of asserting that it passed.

Fetch guides raw with `https://raw.githubusercontent.com/jposluns/secureconfig/<default-branch>/<guide>.md` (for example `.../main/nginx.md`). Every guide concatenated into a single file: https://secureconfig.ai/llms-full.txt (also [site/llms-full.txt](site/llms-full.txt) in this repository); the machine-readable index is https://secureconfig.ai/llms.txt

## Decision guide

Choose every route that applies; a deployment usually needs both service-specific guides and shared controls.

- Public web app with its own domain: [free-certificates.md](free-certificates.md), then the guide for your web server or proxy, then [authentication.md](authentication.md).
- App on a home server or behind NAT, with a domain you can put on Cloudflare: [cloudflare.md](cloudflare.md). The tunnel removes the need for open inbound ports and Access adds login in front of the app. With no domain at all: [tailscale.md](tailscale.md) (Serve for tailnet-only access, Funnel only with the app's own login), or [self-signed.md](self-signed.md) for internal use.
- Internal tool, staging, or local development: [self-signed.md](self-signed.md), with authentication still enabled.
- Human login or SSO: [identity-providers.md](identity-providers.md), [oidc-integration.md](oidc-integration.md) for app integration; [cloud-identity-proxies.md](cloud-identity-proxies.md) or [fronting-auth.md](fronting-auth.md) for login in front; [mfa.md](mfa.md) for the second factor, with an explicit access policy.
- Service-to-service or agent access: [machine-auth.md](machine-auth.md), [secrets.md](secrets.md).
- AI or agent deployment: the matching model-server, MCP, agent-builder, vector-database, UI, or observability guide, plus [gpu-clouds.md](gpu-clouds.md) where applicable and [egress-metadata.md](egress-metadata.md) for outbound and metadata.
- Containers and clusters: [docker.md](docker.md), [container-hardening.md](container-hardening.md), [kubernetes.md](kubernetes.md), then the host, cloud, PaaS, or GPU guide.
- Databases, caches, queues, and model servers: keep them off public interfaces entirely where possible; the per-tool guides cover TLS and authentication for the cases where network exposure is unavoidable.
- Databases, storage, and messaging: the service guide, plus [object-storage.md](object-storage.md), [firebase-supabase.md](firebase-supabase.md), or [pocketbase.md](pocketbase.md) where access depends on storage or data rules.
- Web application exposure: [web-exposure.md](web-exposure.md), [headers.md](headers.md), [cors.md](cors.md), [realtime-webhooks.md](realtime-webhooks.md).
- First deployment, preview, or teardown: [deployment-lifecycle.md](deployment-lifecycle.md), then [common-mistakes.md](common-mistakes.md).

## Guide index

### Certificates and tunnels

| Guide | Covers |
|---|---|
| [free-certificates.md](free-certificates.md) | Free publicly trusted certificates via ACME (Let's Encrypt, ZeroSSL), issuance, and automated renewal |
| [self-signed.md](self-signed.md) | OpenSSL and mkcert certificates when a public CA is not an option, plus distributing trust to clients |
| [cloudflare.md](cloudflare.md) | Cloudflare Tunnel and Zero Trust Access: authenticated external access with no open inbound ports |
| [tailscale.md](tailscale.md) | Tailscale serve (tailnet-only) and funnel (public) with automatic TLS |
| [tunnels.md](tunnels.md) | frp and WireGuard, self-hosted tunnels when there is no public IP |

### Identity, authentication, and secrets

| Guide | Covers |
|---|---|
| [authentication.md](authentication.md) | Password storage, MFA, API keys, sessions, rate limiting, and secret handling |
| [identity-providers.md](identity-providers.md) | Hosted identity and MFA: Entra ID, Google, Okta, Entra External ID, Firebase and Identity Platform, Auth0, Cognito, Clerk, WorkOS, Supabase Auth, Duo; free tiers and who each fits |
| [oidc-integration.md](oidc-integration.md) | OIDC login wiring for Google, Microsoft Entra, GitHub, and Okta: PKCE, redirect URIs, token validation, and the allowlist check |
| [cloud-identity-proxies.md](cloud-identity-proxies.md) | Login in front of the app with no code change: AWS ALB, Google IAP, Azure App Service, Cloudflare Access, ngrok, Vercel |
| [fronting-auth.md](fronting-auth.md) | oauth2-proxy, Authelia, Pomerium: login and MFA in front of an app that has none |
| [mfa.md](mfa.md) | MFA options: identity layers with QR-code TOTP enrolment, app libraries, SSH modules, Duo |
| [machine-auth.md](machine-auth.md) | Machine identity: API keys, client credentials, mutual TLS, workload identity federation, secret managers |
| [secrets.md](secrets.md) | Secrets: repository hygiene, scanning, rotation after a leak, sops/age |

### Web servers and proxies

| Guide | Covers |
|---|---|
| [apache.md](apache.md) | Apache HTTP Server: TLS, redirect, HSTS, basic auth, client certificates |
| [nginx.md](nginx.md) | nginx: TLS, redirect, HSTS, basic auth, client certificates, reverse proxy |
| [lighttpd.md](lighttpd.md) | lighttpd: TLS via mod_openssl, redirect, basic auth |
| [caddy.md](caddy.md) | Caddy: automatic HTTPS, internal CA, basic auth |
| [haproxy.md](haproxy.md) | HAProxy: TLS termination, redirect, HSTS, basic auth |
| [traefik.md](traefik.md) | Traefik: ACME resolvers, HTTPS redirection, basic auth middleware |

### Languages and frameworks

| Guide | Covers |
|---|---|
| [nodejs.md](nodejs.md) | Node.js and Express: HTTPS server, security headers, sessions, password hashing |
| [python.md](python.md) | Flask, FastAPI/Uvicorn, Gunicorn, Django: TLS options and secure settings |
| [nextjs.md](nextjs.md) | Next.js: sessions, Route Handlers, Server Actions, Auth.js and Better Auth, Vercel |
| [go.md](go.md) | Go net/http: TLS, proxy layout, bcrypt, cookies, client TLS discipline |
| [dotnet.md](dotnet.md) | ASP.NET Core and Kestrel: HTTPS, HSTS, forwarded headers, Identity, cookies |
| [java.md](java.md) | Spring Boot: server.ssl, forwarded headers, Spring Security, session cookies |
| [php.md](php.md) | PHP and Laravel: password_hash, session cookies, trusted proxies, forced HTTPS |
| [ruby.md](ruby.md) | Rails and Puma: force_ssl, trusted proxies, has_secure_password, credentials |
| [frontend-frameworks.md](frontend-frameworks.md) | SvelteKit, Nuxt, Vite: server-route auth, sessions, public-env prefixes |

### Containers and Kubernetes

| Guide | Covers |
|---|---|
| [docker.md](docker.md) | Docker and Compose: safe port publishing, the UFW bypass problem, TLS termination |
| [kubernetes.md](kubernetes.md) | Gateway API with a maintained controller, cert-manager TLS, entry-point authentication; ingress-nginx is retired |
| [container-hardening.md](container-hardening.md) | Non-root, dropped capabilities, read-only root, network segmentation |

### Hosts and cloud platforms

| Guide | Covers |
|---|---|
| [host.md](host.md) | Host baseline: SSH hardening, firewall default-deny, brute-force protection, updates |
| [cloud-firewalls.md](cloud-firewalls.md) | Security groups and VPC rules: no 0.0.0.0/0 on databases, SSH posture |
| [paas.md](paas.md) | Render, Fly.io, Vercel, and similar: platform TLS, your auth and secrets |
| [gpu-clouds.md](gpu-clouds.md) | RunPod, Vast.ai, Lambda, Modal: exposed ports and differing firewall and auth defaults per platform |

### Databases, storage, and messaging

| Guide | Covers |
|---|---|
| [postgresql.md](postgresql.md) | PostgreSQL: server TLS, SCRAM authentication, pg_hba rules, verified client connections |
| [mysql.md](mysql.md) | MySQL and MariaDB: required TLS transport, per-user TLS, modern auth plugins |
| [mongodb.md](mongodb.md) | MongoDB: requireTLS, authorization, admin user creation, bind address |
| [redis.md](redis.md) | Redis: TLS listener, ACLs, requirepass, bind and protected mode |
| [sqlite.md](sqlite.md) | SQLite in deployment, the file is the exposure; Turso tokens; Litestream |
| [surrealdb.md](surrealdb.md) | SurrealDB, root credentials, bind address, access levels, TLS |
| [elasticsearch.md](elasticsearch.md) | Elasticsearch and OpenSearch: keep the built-in security on |
| [clickhouse.md](clickhouse.md) | ClickHouse: user passwords, secure ports, network restrictions |
| [neo4j.md](neo4j.md) | Neo4j: initial password, Bolt and HTTPS TLS, auth stays on |
| [memcached.md](memcached.md) | Memcached: no auth by default; loopback, SASL and TLS where built in |
| [search-engines.md](search-engines.md) | Meilisearch and Typesense, master key, scoped search keys, production mode |
| [minio.md](minio.md) | MinIO: root credentials, certs directory TLS, scoped access keys |
| [object-storage.md](object-storage.md) | S3, R2, GCS, Azure Blob, Supabase Storage: private by default, scoped credentials, signed URLs |
| [firebase-supabase.md](firebase-supabase.md) | Firebase rules and Supabase RLS: the rules are the security |
| [pocketbase.md](pocketbase.md) | PocketBase and Appwrite: the rules are the security; lock the admin console |
| [rabbitmq.md](rabbitmq.md) | RabbitMQ: users and permissions, TLS listener, guest account |
| [mosquitto.md](mosquitto.md) | Mosquitto (MQTT): per-device credentials, TLS listener, mutual TLS |
| [kafka.md](kafka.md) | Apache Kafka: SASL_SSL listeners, SCRAM credentials, ACLs |
| [nats.md](nats.md) | NATS and JetStream, auth, TLS, and the unauthenticated monitoring port |

### AI and agent infrastructure

| Guide | Covers |
|---|---|
| [ollama.md](ollama.md) | Ollama: no built-in auth or TLS; protect it with a proxy or tunnel |
| [model-servers.md](model-servers.md) | llama.cpp, vLLM, TGI, SGLang, Triton, LM Studio: loopback, API keys, TLS in front |
| [litellm.md](litellm.md) | LiteLLM proxy: master key, per-app virtual keys |
| [vector-databases.md](vector-databases.md) | Qdrant, Weaviate, Milvus, Chroma, pgvector: API keys, TLS, what has no native auth |
| [mcp-servers.md](mcp-servers.md) | MCP servers: stdio versus Streamable HTTP, loopback, Origin checks, OAuth 2.1 or a fronting layer |
| [ray.md](ray.md) | Ray: dashboard, Jobs, and Client ports execute code; isolate, token auth, SSH forward |
| [mlflow.md](mlflow.md) | MLflow tracking server: no auth by default; basic-auth app, TLS in front |
| [llm-observability.md](llm-observability.md) | Langfuse, Phoenix, Helicone, OpenTelemetry Collector: they hold prompts and keys |
| [agent-builders.md](agent-builders.md) | Dify, Flowise, Langflow, LibreChat: admin setup, API keys, fronting TLS |
| [workflow-orchestrators.md](workflow-orchestrators.md) | Prefect, Dagster, Airflow, Temporal, Flower: keep off the public internet and require auth |

### App UIs and dev tools

| Guide | Covers |
|---|---|
| [open-webui.md](open-webui.md) | Open WebUI: signup control, pending role, fronting TLS |
| [chat-uis.md](chat-uis.md) | AnythingLLM, LobeChat, Chainlit, OpenHands: open by default; front with login |
| [image-gen-uis.md](image-gen-uis.md) | ComfyUI, A1111, InvokeAI, Fooocus: keep on loopback and add a login before exposing |
| [gradio.md](gradio.md) | Gradio: launch() auth and TLS parameters, share link risks |
| [streamlit.md](streamlit.md) | Streamlit: TLS options, native OIDC login, reverse proxy deployment |
| [jupyter.md](jupyter.md) | Jupyter Server, Lab, and Notebook: hashed password and TLS |
| [n8n.md](n8n.md) | n8n: listen address, native TLS, owner setup, MFA enforcement |
| [code-server.md](code-server.md) | code-server: SSH forwarding first, password auth, TLS |

### Dashboards and admin consoles

| Guide | Covers |
|---|---|
| [admin-uis.md](admin-uis.md) | phpMyAdmin, pgAdmin, mongo-express, Grafana, Prometheus: never public |
| [devops-uis.md](devops-uis.md) | Portainer, Coolify, Dokploy, Nginx Proxy Manager, Vaultwarden, Kubernetes Dashboard, Jenkins, Gitea, Uptime Kuma, Docker API: never public |
| [bi-dashboards.md](bi-dashboards.md) | Metabase, Superset, Redash: never public; least-privilege database user |

### Web application controls

| Guide | Covers |
|---|---|
| [cors.md](cors.md) | CORS: exact origins, never * with credentials |
| [headers.md](headers.md) | Security headers: HSTS, CSP, and companions for your app |
| [realtime-webhooks.md](realtime-webhooks.md) | WebSocket, SSE, and webhook authentication |

### Exposure and deployment operations

| Guide | Covers |
|---|---|
| [web-exposure.md](web-exposure.md) | Files a web server must never serve: dotfiles, .git, dumps, client secrets |
| [egress-metadata.md](egress-metadata.md) | Egress control and cloud metadata (IMDSv2), stop an agent exfiltrating credentials |
| [deployment-lifecycle.md](deployment-lifecycle.md) | Verify from outside, safe first-run order, previews, and teardown |
| [common-mistakes.md](common-mistakes.md) | The recurring findings, each linked to its fix |

## Verification checklist

Run the applicable checks below and the Verify steps in every selected guide. Record each result as pass, fail, untested, or not applicable, with evidence or a reason; report a control as verified only for the checks that passed.

1. No plaintext listener on a public interface: `ss -tlnp` (Linux) shows nothing bound to `0.0.0.0` or a public address on a plain HTTP port, except a listener whose only job is to redirect to HTTPS.
2. Where HTTP is offered, the redirect works: `curl -sI http://example.com/` returns `301` or `308` (the preferred permanent redirects), or `302`/`307` where a framework issues them, always with a `Location: https://...` header.
3. TLS works: `curl -sI https://example.com/` succeeds without `-k`.
4. Old protocols are refused: `openssl s_client -connect example.com:443 -tls1_1` fails to negotiate (TLS 1.2 is the minimum everywhere in these guides). Confirm the refusal came from the server and not from your own client: a local OpenSSL build, or a `MinProtocol` setting in its configuration, can refuse TLS 1.1 before any offer is sent, which looks identical. Check that your client can still offer TLS 1.1 at all, or use an external scanner that does.
5. Authentication is enforced: an unauthenticated request to any non-public path returns `401`, `403`, or a login redirect, never data. Test the API paths as well as the home page.
6. No default credentials remain, and no secret (password, key, token, certificate private key) is committed to the repository. Scan before pushing, for example with gitleaks.
7. Where ACME is used, renewal is automated: `sudo certbot renew --dry-run` passes AND something is actually scheduled to run it. The dry run proves the command works, not that it will ever be invoked, so check the scheduler too: `systemctl list-timers` shows an active certbot timer with a next run, or the packaged cron entry is present. Servers that manage renewal themselves (Caddy, Traefik) need no timer; confirm a completed renewal in their logs instead.
8. For public endpoints: scanned with the [Qualys SSL Labs test](https://www.ssllabs.com/ssltest/) or [testssl.sh](https://github.com/testssl/testssl.sh).
9. Human-facing logins carry a second factor where the stack supports one; [mfa.md](mfa.md) lists the options, and the per-tool guides state what is viable.
10. Probe from outside the deployment network, from a second host: cloud-firewall and Docker-publishing mistakes only show from outside. Shodan or Censys can corroborate, but they report what a scanner last observed rather than what is listening now, so a port published since their last pass will not appear; treat them as a second opinion, never as a substitute for a live probe. See [deployment-lifecycle.md](deployment-lifecycle.md).
11. Where login comes from an identity provider, an authenticated identity outside the allowed tenant, domain, group, or users is denied; test with such an account, not only an anonymous request.

Sources for these checks are listed in [README.sources.md](README.sources.md), numbered to match the items above.

## Scope and currency

The guides use placeholders (`example.com`, `app.example.com`, `203.0.113.10`) that you must replace. Configuration syntax was checked against the vendor documentation cited in each guide as of September 2026; directives and dashboard menu locations change, so verify version-specific items against the current documentation for your installed version. Each guide lists its sources.

Scope: deployment exposure, including TLS, human and machine authentication, MFA, access restrictions, secrets, and inbound and outbound network access, from first deployment through teardown. General application security, including injection, deserialization, and business logic flaws, belongs to the OWASP resources linked throughout the guides. To propose a tool or guide, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Everything in this repository (the guides, the configuration samples, and the site) is dedicated to the public domain under [CC0 1.0 Universal](LICENSE). Copy and reuse it freely; no attribution is required.
