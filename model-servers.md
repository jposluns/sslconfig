# Model servers: llama.cpp and vLLM

Self-hosted model servers follow the [ollama.md](ollama.md) pattern: they default to local use, and exposing them means someone else's prompts run on your GPU. Keep them on loopback, require an API key where the server supports one, and terminate TLS in front.

## llama.cpp (llama-server)

`llama-server` listens on `127.0.0.1:8080` by default; keep that bind. Require a key:

```bash
llama-server -m model.gguf --api-key "$LLAMA_API_KEY"
# --api-key accepts a comma-separated list for multiple keys
```

Native TLS exists when the binary is built with OpenSSL (`-DLLAMA_OPENSSL=ON`): `--ssl-key-file` and `--ssl-cert-file` take PEM files ([self-signed.md](self-signed.md) or [free-certificates.md](free-certificates.md)). A reverse proxy per [nginx.md](nginx.md)/[caddy.md](caddy.md) is the alternative when your build lacks SSL support.

## vLLM (OpenAI-compatible server)

vLLM's server supports requiring an API key; check `vllm serve --help` on your installed version for the current option name (the docs at https://docs.vllm.ai/ document it; this guide avoids pinning the flag because vLLM's CLI moves quickly). vLLM does not terminate TLS for you in typical deployments, so front it with a TLS proxy or tunnel and keep the server itself on loopback or a private network.

## The pattern, whatever the server

1. Bind to `127.0.0.1` (or a private container network); confirm with `ss -tlnp`.
2. Require a per-client API key at the server where supported, or at the proxy otherwise (bearer-token check per [ollama.md](ollama.md)); generate keys per [authentication.md](authentication.md).
3. TLS in front: [caddy.md](caddy.md), [nginx.md](nginx.md), [cloudflare.md](cloudflare.md), or [tailscale.md](tailscale.md).
4. Human-facing UIs on top of these servers ([open-webui.md](open-webui.md)) carry their own login and MFA ([mfa.md](mfa.md)).

## Verify

```bash
ss -tlnp | grep -E '8080|8000'                          # loopback only
curl -s https://models.example.com/v1/models            # 401 without a key
curl -s https://models.example.com/v1/models -H "Authorization: Bearer <key>"   # succeeds
```

## Sources (checked September 2026)

- llama.cpp server README (defaults, --api-key, SSL flags): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- vLLM documentation: https://docs.vllm.ai/
