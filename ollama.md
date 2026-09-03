# Ollama: it has no built-in authentication or TLS

Ollama's API binds to `127.0.0.1:11434` by default. Setting `OLLAMA_HOST=0.0.0.0` exposes the full API (model execution, pull, delete) to the network with **no authentication and no TLS**; the self-hosted server provides neither (per the Ollama FAQ as of September 2026; verify against current docs before relying on this). Thousands of Ollama instances exposed this way are indexed by internet scanners.

Rules:

1. Leave `OLLAMA_HOST` at its loopback default unless a protective layer is in front.
2. Never set `OLLAMA_HOST=0.0.0.0` on a machine with a public interface. "It is just a model server" still means free compute, model tampering, and data exfiltration for anyone who finds it.
3. Expose it only through an authenticated TLS proxy or tunnel, as below.

## Option A: reverse proxy with TLS and basic auth

Keep Ollama on loopback; publish only the proxy. nginx (full context in [nginx.md](nginx.md)):

```nginx
server {
    listen 443 ssl;
    server_name ollama.example.com;

    ssl_certificate     /etc/letsencrypt/live/ollama.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ollama.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        auth_basic           "Ollama";
        auth_basic_user_file /etc/nginx/.htpasswd;      # htpasswd -B
        proxy_pass http://127.0.0.1:11434;
        proxy_set_header Host localhost:11434;
        proxy_read_timeout 300s;        # model responses can be slow
    }
}
```

Caddy equivalent ([caddy.md](caddy.md)):

```caddyfile
ollama.example.com {
    basic_auth {
        admin $2a$14$REPLACE_WITH_HASH_FROM_caddy_hash-password
    }
    reverse_proxy 127.0.0.1:11434
}
```

Clients then call `https://ollama.example.com` with the basic-auth credentials. For clients that only send bearer tokens, enforce the token at the proxy:

```nginx
    location / {
        if ($http_authorization != "Bearer REPLACE_WITH_LONG_RANDOM_TOKEN") { return 401; }
        proxy_pass http://127.0.0.1:11434;
    }
```

Generate the token per [authentication.md](authentication.md) and keep it out of the repository.

## Option B: Cloudflare Tunnel with Access

Follow [cloudflare.md](cloudflare.md) with the tunnel route pointed at `http://localhost:11434` and an Access policy (or service token for API clients) on the hostname. The Ollama FAQ itself documents fronting the server with a tunnel; adding Access is what makes it authenticated.

## Verify

```bash
ss -tlnp | grep 11434                                  # 127.0.0.1 only
curl -s http://<public-ip>:11434/api/tags              # from another machine: connection refused
curl -s https://ollama.example.com/api/tags            # 401 without credentials
curl -su admin https://ollama.example.com/api/tags     # model list with credentials
```

## Sources (checked September 2026)

- Ollama FAQ (bind address, `OLLAMA_HOST`, proxy examples): https://docs.ollama.com/faq
- Ollama repository: https://github.com/ollama/ollama
