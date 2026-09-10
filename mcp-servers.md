# MCP servers: exposing Model Context Protocol servers safely

An MCP server gives a model tools, and every tool it exposes runs with the credentials the server holds. The 2025-11-25 specification defines two transports. Over **stdio** the client launches the server as a subprocess and talks over stdin and stdout: there is no network listener, but the process runs as the launching user with every credential in its environment, so a malicious or careless server is a local compromise, not a network one. Over **Streamable HTTP** the server is a web service with a single endpoint accepting POST and GET, and every rule in [authentication.md](authentication.md) applies to it. The older HTTP with SSE transport (protocol version 2024-11-05) is deprecated; Streamable HTTP replaces it. The spec makes authorization OPTIONAL at the protocol level; this repository does not, so an HTTP MCP server reachable beyond loopback authenticates every request, either natively or through a fronting layer.

## 1. Prefer stdio, and keep HTTP on loopback

- For a single-user tool on a workstation, use the stdio transport. The spec's own guidance for local servers is to "use the `stdio` transport to limit access to just the MCP client" and, if HTTP is used anyway, to require an authorization token or use a Unix domain socket with restricted access.
- Give a stdio server only the environment it needs: the API key for the one service it wraps, not a shell profile full of cloud credentials. Per the spec, stdio servers "retrieve credentials from the environment", which means that environment is the server's whole privilege set ([secrets.md](secrets.md)).
- For Streamable HTTP, the spec's Security Warning says: "When running locally, servers SHOULD bind only to localhost (127.0.0.1) rather than all network interfaces (0.0.0.0)". Bind to `127.0.0.1` and publish only a fronting layer, exactly as [ollama.md](ollama.md) does for a model server. Check the SDK or framework you use for its bind-address option; do not assume its default is loopback.

## 2. Validate `Origin` (DNS rebinding)

The spec requires it: "Servers MUST validate the `Origin` header on all incoming connections to prevent DNS rebinding attacks. If the `Origin` header is present and invalid, servers MUST respond with HTTP 403 Forbidden." Without this, "attackers could use DNS rebinding to interact with local MCP servers from remote websites": a page in the user's browser resolves its own hostname to `127.0.0.1` and drives the local server. Do the check in the server (most SDKs have an allowed-origins option; confirm yours is on). A reverse proxy can add a second check in front, using the nginx `if` directive with the `$http_origin` variable:

```nginx
    location /mcp {
        if ($http_origin !~ "^https://mcp\.example\.com$") { return 403; }
        proxy_pass http://127.0.0.1:3000;
    }
```

Non-browser clients often send no `Origin` at all; the spec's requirement is about a present and invalid header, so decide deliberately whether a missing header is accepted (the nginx test above rejects it) and document the choice.

To accept requests that carry no `Origin` while still rejecting a wrong one, use a `map` in the `http` block (an empty string key matches a missing header) and test the variable in the location:

```nginx
map $http_origin $bad_origin {
    default                   1;
    ""                        0;    # no Origin header: a non-browser MCP client
    "https://mcp.example.com" 0;
}
```

```nginx
    location /mcp {
        if ($bad_origin) { return 403; }
        proxy_pass http://127.0.0.1:3000;
    }
```

## 3. TLS

The MCP server itself speaks plain HTTP on loopback. Terminate TLS at the proxy per [nginx.md](nginx.md) or [caddy.md](caddy.md) with a certificate from [free-certificates.md](free-certificates.md), or publish through [cloudflare.md](cloudflare.md) or [tailscale.md](tailscale.md). Bearer tokens cross the network with every request, so the spec requires HTTPS for all authorization server endpoints, and [authentication.md](authentication.md) requires it for every credential.

## 4. Authentication: native OAuth 2.1 or a fronting layer

**Option A, spec authorization.** The MCP server acts as an OAuth 2.1 resource server. The spec's requirements, in its own terms:

- MCP servers "MUST implement OAuth 2.0 Protected Resource Metadata (RFC9728)", and the metadata "MUST include the `authorization_servers` field". Discovery is either a `WWW-Authenticate` header carrying `resource_metadata` on `401 Unauthorized` responses, or the well-known URI (`/.well-known/oauth-protected-resource`, optionally suffixed with the endpoint path); clients must support both.
- Clients "MUST implement PKCE" with the `S256` method and "MUST refuse to proceed" if the authorization server's metadata lacks `code_challenge_methods_supported`. Clients MUST send the RFC 8707 `resource` parameter naming the MCP server's canonical URI.
- Servers "MUST validate that access tokens were issued specifically for them as the intended audience"; invalid or expired tokens get `401`, insufficient scope gets `403`. Servers "MUST NOT accept or transit any other tokens": the token the client presents never travels on to an upstream API. If the server calls upstream APIs, "the access token used at the upstream API is a separate token, issued by the upstream authorization server".
- Tokens go in `Authorization: Bearer ...` on every request, never in the URL. Sessions are not authentication: servers "MUST NOT use sessions for authentication", and the `MCP-Session-Id` must be a secure, non-deterministic value.

Pick an identity provider from [identity-providers.md](identity-providers.md) as the authorization server; the client-side hygiene in [oidc-integration.md](oidc-integration.md) applies. Azure App Service can serve the RFC 9728 document for an app behind its built-in authentication: set the `WEBSITE_AUTH_PRM_DEFAULT_WITH_SCOPES` application setting to the required scopes, and the 401 challenge then carries the metadata URL and scopes. Microsoft marks this **preview** at the time of writing and says the configuration may change ([cloud-identity-proxies.md](cloud-identity-proxies.md) covers the rest of Easy Auth).

**Option B, a fronting layer.** Keep the server on loopback and authenticate at the edge: a reverse proxy bearer-token check (the nginx `if ($http_authorization ...)` block in [ollama.md](ollama.md)) or basic auth per [nginx.md](nginx.md)/[caddy.md](caddy.md); Cloudflare Access with a service token for machine clients per [cloudflare.md](cloudflare.md); or an identity-aware proxy per [cloud-identity-proxies.md](cloud-identity-proxies.md). Generate and rotate the token per [machine-auth.md](machine-auth.md).

Be clear about what Option B is. A static bearer token at the proxy is a fronting control, not MCP authorization: it serves no Protected Resource Metadata and no `WWW-Authenticate` challenge with `resource_metadata`, so an MCP client that expects the OAuth discovery flow will not negotiate it. Such clients need the token pre-configured (most clients accept static headers for a server), or Option A.

MFA: MCP has no login dialogue of its own. Under Option A, MFA is whatever the authorization server enforces; under Option B it comes from the identity provider behind Access or the identity-aware proxy. Enforce it there per [mfa.md](mfa.md).

## 5. The credentials the server holds

- Each tool's upstream API key is a secret the server holds on behalf of every caller. Load it from the environment or a secret manager, one key per server and environment, never from the repository ([secrets.md](secrets.md)).
- Least privilege per tool: a read-only tool gets a read-only key. A server that wraps a database, a cloud account, and a mail API with admin credentials turns every prompt injection into an administrator.
- Never forward the client's token upstream (spec: "Token passthrough" is an anti-pattern and "explicitly forbidden"). Log tool calls with the authenticated identity so an incident can be traced.

## Verify

```bash
ss -tlnp | grep 3000                                   # 127.0.0.1:3000 only, never 0.0.0.0 or ::
# From another host: refused at the origin, or answered only by the fronting layer.
curl -s http://203.0.113.10:3000/mcp                   # connection refused

# Unauthenticated initialize: 401 with a WWW-Authenticate header (Option A) or the proxy's 401 (Option B).
curl -si -X POST https://mcp.example.com/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"check","version":"1.0.0"}}}'
# Option A only: the metadata the 401 points at exists and names your authorization server.
curl -s https://mcp.example.com/.well-known/oauth-protected-resource   # JSON with "authorization_servers"

# Wrong Origin, with a valid credential: 403.
curl -si -X POST https://mcp.example.com/mcp -H 'Origin: https://attacker.example' \
  -H 'Authorization: Bearer REPLACE_WITH_LONG_RANDOM_VALUE' \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{}'
```

A token issued for a different resource (wrong audience) must also fail with `401`; test it under Option A.

## Common mistakes

- Binding the HTTP transport to `0.0.0.0` "for Docker" and leaving it there. Publish the container port on `127.0.0.1` only ([docker.md](docker.md)).
- Treating stdio as safe because it has no port: the server runs as you, with your environment.
- Accepting any token from your identity provider without checking the audience, so a token issued for another API also opens the MCP server.
- Passing the caller's token to the upstream API, which makes the upstream trust a token it never issued and loses the audit trail.

## Sources (checked September 2026)

- MCP specification 2025-11-25, Transports (stdio, Streamable HTTP, Security Warning, deprecated HTTP+SSE, `MCP-Session-Id`): https://modelcontextprotocol.io/specification/2025-11-25/basic/transports
- MCP specification 2025-11-25, Authorization (OPTIONAL, RFC 9728, PKCE, `resource`, audience validation, error codes): https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- MCP specification 2025-11-25, Security Best Practices (token passthrough, session hijacking, local server compromise): https://modelcontextprotocol.io/specification/2025-11-25/basic/security_best_practices
- MCP specification 2025-11-25, Lifecycle (`initialize` request shape): https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle
- Azure App Service authentication (protected resource metadata preview, `WEBSITE_AUTH_PRM_DEFAULT_WITH_SCOPES`): https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization
- nginx `if` and `return` directives: https://nginx.org/en/docs/http/ngx_http_rewrite_module.html
- nginx embedded variables (`$http_name`): https://nginx.org/en/docs/http/ngx_http_core_module.html
- nginx ngx_http_map_module (Origin allowlist map): https://nginx.org/en/docs/http/ngx_http_map_module.html
