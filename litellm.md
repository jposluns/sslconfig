# LiteLLM proxy: master key and virtual keys

A LiteLLM proxy fronts paid model APIs, so an exposed, keyless instance spends your provider credits for whoever finds it. Authentication is built in and must be switched on before anything else.

## 1. Set the master key

In `config.yaml` under `general_settings: master_key`, or via the environment (preferred; see [secrets.md](secrets.md)):

```bash
export LITELLM_MASTER_KEY="sk-REPLACE_WITH_LONG_RANDOM_VALUE"   # must start with sk-
```

The master key is the root credential for the proxy; it belongs to the operator only and never to client applications.

## 2. Issue virtual keys per application

```bash
curl https://llm.example.com/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"key_alias": "app-frontend"}'
```

Each app gets its own virtual key, which can be revoked or budgeted independently; LiteLLM's docs cover per-key models, budgets, and expiry. Clients send the virtual key in the `Authorization` header (the header name is configurable via `litellm_key_header_name`).

## 3. Bind privately and add TLS in front

Run the proxy on loopback (or a private container network) and publish it only through a TLS layer: [caddy.md](caddy.md)/[nginx.md](nginx.md) with a certificate from [free-certificates.md](free-certificates.md), or [cloudflare.md](cloudflare.md)/[tailscale.md](tailscale.md) for no-open-port setups. Bearer keys over plain HTTP are compromised on first use. For human access to the LiteLLM admin UI, add MFA at the fronting layer ([mfa.md](mfa.md)).

## 4. Verify

```bash
curl -s https://llm.example.com/v1/models                       # 401 without a key
curl -s https://llm.example.com/v1/models -H "Authorization: Bearer <virtual-key>"   # model list
ss -tlnp | grep 4000                                            # loopback only
```

## Sources (checked September 2026)

- LiteLLM proxy virtual keys (master_key, /key/generate, header name): https://docs.litellm.ai/docs/proxy/virtual_keys
