# Vector databases: Qdrant, Weaviate, Milvus, Chroma, pgvector

A RAG store holds every document the application was given, often including private data, and it answers similarity queries that reconstruct that text. Several of these servers ship with no authentication enabled and none of them serves TLS out of the box, so an exposed default install is a searchable copy of your corpus. Keep the store on a private interface, turn on the native key or account control where one exists, and put TLS in front or on the server before any client crosses a network.

## 1. Bind privately

Each server listens on plain TCP; publish only a reverse proxy ([nginx.md](nginx.md), [caddy.md](caddy.md)), a tunnel ([cloudflare.md](cloudflare.md)), or a tailnet ([tailscale.md](tailscale.md)). In Docker, map to loopback (`-p 127.0.0.1:6333:6333`), not `-p 6333:6333`, which binds every interface ([docker.md](docker.md)). Default ports, from the vendor pages in Sources:

| Server | Default ports |
|---|---|
| Qdrant | 6333 (REST), 6334 (gRPC), 6335 (internal cluster gRPC) |
| Weaviate | 8080 (HTTP), 50051 (gRPC) |
| Milvus | 19530 (gRPC), 9091 (WebUI) |
| Chroma | 8000 |
| pgvector | 5432 (it is PostgreSQL) |

## 2. Qdrant: API key and TLS

Per the Qdrant security page, "all self-deployed Qdrant instances are not secure" by default and connections are unencrypted. Set an API key in the config file or through the environment, and add a read-only key for query-only clients:

```yaml
service:
  api_key: REPLACE_WITH_LONG_RANDOM_VALUE
  read_only_api_key: REPLACE_WITH_ANOTHER_LONG_RANDOM_VALUE
  enable_tls: true

tls:
  cert: ./tls/cert.pem
  key: ./tls/key.pem
```

Environment equivalents: `QDRANT__SERVICE__API_KEY` and `QDRANT__SERVICE__READ_ONLY_API_KEY`. Clients send the key in the `api-key` header (or `Authorization: Bearer`). Qdrant's own docs say that enabling the key without TLS is insecure; terminate TLS either in Qdrant as above or at a proxy in front.

## 3. Weaviate: disable anonymous access, then authorize

`AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED` defaults to `true`, which the Weaviate docs describe as strongly discouraged outside development. The secured Docker example:

```yaml
environment:
  AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'false'
  AUTHENTICATION_APIKEY_ENABLED: 'true'
  AUTHENTICATION_APIKEY_ALLOWED_KEYS: 'REPLACE_WITH_ADMIN_KEY,REPLACE_WITH_APP_KEY'
  AUTHENTICATION_APIKEY_USERS: 'admin-user,app-user'
  AUTHORIZATION_RBAC_ENABLED: 'true'
  AUTHORIZATION_RBAC_ROOT_USERS: 'admin-user'
```

Keys map to users by position, so the first key belongs to `admin-user` and the second to `app-user`. Only `admin-user` is a root user with full access; give `app-user` a custom role limited to its collections, created with the admin key through the RBAC API as the [RBAC configuration page](https://docs.weaviate.io/deploy/configuration/configuring-rbac) describes, and keep the admin key off the application host. Authentication alone lets any key holder do anything; add authorization with either RBAC (above, generally available from v1.29 per the authorization page) or the simpler admin list (`AUTHORIZATION_ADMINLIST_ENABLED`, `AUTHORIZATION_ADMINLIST_USERS`, `AUTHORIZATION_ADMINLIST_READONLY_USERS`; it cannot be combined with RBAC). For human logins, `AUTHENTICATION_OIDC_ENABLED` with `AUTHENTICATION_OIDC_ISSUER` and `AUTHENTICATION_OIDC_CLIENT_ID` delegates to an identity provider, where MFA is enforced ([mfa.md](mfa.md)). The documented deployment starts Weaviate with `--scheme http` and points to a reverse proxy for domain access, forwarding both 8080 and 50051; give the proxy the certificate ([free-certificates.md](free-certificates.md)) and do not expose the plain ports.

## 4. Milvus: enable authentication, change root, add TLS

Authentication is enabled by setting `common.security.authorizationEnabled: true` in `milvus.yaml` (or through the Helm `extraConfigFiles` / Operator `spec.config` equivalents). Once on, the built-in `root` user exists with the password `Milvus`; change it before exposure, since a documented default is a public credential ([authentication.md](authentication.md)):

```python
client = MilvusClient(uri="https://milvus.example.com:19530", token="root:Milvus")
client.update_password(user_name="root", old_password="Milvus", new_password="REPLACE_WITH_LONG_RANDOM_VALUE")
```

Create a per-application user rather than handing `root` to the app. TLS is configured in the same file, with certificates mounted into the container (Docker Compose: a volume such as `./tls:/milvus/tls`):

```yaml
tls:
  serverPemPath: /milvus/tls/server.pem
  serverKeyPath: /milvus/tls/server.key
  caPemPath: /milvus/tls/ca.pem
common:
  security:
    tlsMode: 1      # 1 = server certificate only; 2 = mutual TLS, clients present a certificate too
```

Clients then connect with `secure=True` and the server certificate path. TLS and authentication are independent in Milvus; enable both.

## 5. Chroma: no native authentication since 1.0

Chroma's migration notes for v1.0.0 state that "Chroma no longer provides built-in authentication implementations". A self-hosted `chroma run --path /db_path` server (port 8000) therefore accepts every request, and the older `CHROMA_SERVER_AUTHN_PROVIDER` / `CHROMA_SERVER_AUTHN_CREDENTIALS` variables from the 2024 auth overhaul no longer do anything; do not paste them from old tutorials and assume protection. Keep Chroma on loopback and expose it only through an authenticated TLS proxy (bearer-token or basic-auth block per [nginx.md](nginx.md) / [caddy.md](caddy.md)), a Cloudflare Tunnel with Access ([cloudflare.md](cloudflare.md)), or a tailnet ([tailscale.md](tailscale.md)).

## 6. pgvector: it is PostgreSQL

pgvector is an extension (`CREATE EXTENSION vector;`, PostgreSQL 13 and later), so [postgresql.md](postgresql.md) applies unchanged: `ssl = on`, `hostssl` lines with `scram-sha-256`, a least-privilege role per application, and `sslmode=verify-full` in every connection string. When several tenants share one embeddings table, add row-level security keyed on the tenant column so a query can only match rows the connected role may see.

## 7. Hosted services and MFA

Pinecone, Qdrant Cloud, Weaviate Cloud, and Zilliz authenticate with API keys: those are secrets under [secrets.md](secrets.md), one per environment, never committed, rotated on leak. The vendor terminates TLS, so the client-side check is that the SDK is pointed at the `https://` endpoint the console gives you. None of the self-hosted servers has a human login with a second factor; MFA exists only on the vendor console for the hosted tiers, at the identity provider when Weaviate uses OIDC, or on the fronting layer (Access policy, Authelia-style portal) for everything else ([mfa.md](mfa.md)).

## Verify

```bash
ss -tlnp | grep -E '6333|6334|8080|50051|19530|9091|8000|5432'   # 127.0.0.1 only
curl -si https://qdrant.example.com/collections | head -1           # 401 or 403 without a key
curl -s -H 'api-key: REPLACE_WITH_LONG_RANDOM_VALUE' https://qdrant.example.com/collections   # collection list
curl -si https://weaviate.example.com/v1/schema | head -1           # 401 without a key
curl -si https://chroma.example.com/ | head -1                      # 401 from the proxy, never a Chroma response
```

For Milvus, a `MilvusClient(uri=...)` call with no `token` must fail once `authorizationEnabled` is on, and the same call with the application user's credentials must succeed.

## Sources (checked September 2026)

- Qdrant security (API key, read-only key, `api-key` header, TLS keys, ports, default insecurity): https://qdrant.tech/documentation/security/
- Weaviate authentication (anonymous access, API key, OIDC variables): https://docs.weaviate.io/deploy/configuration/authentication
- Weaviate authorization (admin list, RBAC availability): https://docs.weaviate.io/deploy/configuration/authorization and RBAC configuration (`AUTHORIZATION_RBAC_ENABLED`, `AUTHORIZATION_RBAC_ROOT_USERS`): https://docs.weaviate.io/deploy/configuration/configuring-rbac
- Weaviate environment variables (`AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED` default, `GRPC_PORT` default): https://docs.weaviate.io/deploy/configuration/env-vars
- Weaviate Docker installation (ports 8080/50051, `--scheme http`, reverse proxy layout): https://docs.weaviate.io/deploy/installation-guides/docker-installation
- Milvus authentication (`common.security.authorizationEnabled`, default `root`/`Milvus`, `update_password`): https://milvus.io/docs/authenticate.md
- Milvus TLS (`tls.*` paths, `common.security.tlsMode`, RESTful port note): https://milvus.io/docs/tls.md ; standalone install (ports 19530 and 9091): https://milvus.io/docs/install_standalone-docker.md
- Chroma migration notes (v1.0.0 removal of built-in authentication; 2024 auth overhaul variables): https://docs.trychroma.com/docs/overview/migration ; client-server mode (`chroma run --path`, port 8000): https://docs.trychroma.com/docs/run-chroma/client-server
- pgvector (`CREATE EXTENSION vector`, PostgreSQL 13 and later): https://github.com/pgvector/pgvector
