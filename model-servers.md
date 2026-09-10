# Model servers: llama.cpp, vLLM, TGI, SGLang, Triton, and LM Studio

Self-hosted model servers follow the [ollama.md](ollama.md) pattern: exposing one means someone else's prompts run on your GPU. Most default to local use, but TGI and Triton bind to `0.0.0.0` out of the box, and Triton has no authentication at all. Keep every server on loopback or a private network, require an API key where the server supports one, and terminate TLS in front.

## llama.cpp (llama-server)

`llama-server` listens on `127.0.0.1:8080` by default; keep that bind. Require a key:

```bash
llama-server -m model.gguf --api-key "$LLAMA_API_KEY"
# --api-key accepts a comma-separated list for multiple keys
```

Native TLS exists when the binary is built with OpenSSL (`-DLLAMA_OPENSSL=ON`): `--ssl-key-file` and `--ssl-cert-file` take PEM files ([self-signed.md](self-signed.md) or [free-certificates.md](free-certificates.md)). A reverse proxy per [nginx.md](nginx.md)/[caddy.md](caddy.md) is the alternative when your build lacks SSL support.

## vLLM (OpenAI-compatible server)

vLLM's server supports requiring an API key; check `vllm serve --help` on your installed version for the current option name (the docs at https://docs.vllm.ai/ document it; this guide avoids pinning the flag because vLLM's CLI moves quickly). vLLM does not terminate TLS for you in typical deployments, so front it with a TLS proxy or tunnel and keep the server itself on loopback or a private network.

## Hugging Face Text Generation Inference (TGI)

`text-generation-launcher` listens on `0.0.0.0:3000` by default (`--hostname`, env `HOSTNAME`; `--port`, env `PORT`), so a bare TGI container answers on every interface. Bind it to loopback, or publish nothing from the container network except the proxy:

Lifecycle note, as of September 2026: the TGI repository is in maintenance mode and was archived on 2026-03-21 (read-only). Hugging Face recommends vLLM, SGLang, or local engines such as llama.cpp going forward. A server that no longer receives fixes belongs behind the same controls as any other, and on a migration list.

```bash
text-generation-launcher --model-id <model> --hostname 127.0.0.1 --port 3000
```

The launcher reference lists `--api-key` (env `API_KEY`) without describing it. The router source shows what it does: when set, every inference request must carry a matching `Authorization: Bearer <key>` header or receives 401, while the health, info, and metrics routes stay unauthenticated. Treat it as a second layer and enforce the bearer check at the proxy too (pattern in [ollama.md](ollama.md)). The launcher has no TLS option, so front TGI per [nginx.md](nginx.md)/[caddy.md](caddy.md). The Prometheus listener (`--prometheus-port`, default 9000) is unauthenticated as well; keep it private.

## SGLang

`python -m sglang.launch_server` listens on `127.0.0.1:30000` by default (`--host`, `--port`); keep that bind. `--api-key` sets the key the OpenAI-compatible endpoints require, and `--admin-api-key` separately protects administrative endpoints (weight updates, cache flush, `/server_info`), which then require `Authorization: Bearer <admin key>`:

```bash
python -m sglang.launch_server --model-path <model> --api-key "$SGLANG_API_KEY" --admin-api-key "$SGLANG_ADMIN_KEY"
```

Native TLS exists: `--ssl-keyfile` and `--ssl-certfile` take PEM files ([self-signed.md](self-signed.md) or [free-certificates.md](free-certificates.md)), `--ssl-ca-certs` names a CA bundle, and `--enable-ssl-refresh` hot-reloads renewed certificates. A reverse proxy remains the simpler choice when you already run one.

## NVIDIA Triton Inference Server

`tritonserver` starts three listeners on `0.0.0.0`: HTTP on 8000, gRPC on 8001, and Prometheus metrics on 8002. It has no built-in authentication. NVIDIA's secure deployment guidance is that Triton is a microservice that is "not exposed directly to an untrusted network": a dedicated gateway or proxy (NGINX, Envoy, Istio, Kong are the examples given) handles authorization, access control, and encryption, and Triton "handles only trusted, validated requests". Bind each listener privately and disable the protocols you do not use:

```bash
tritonserver --model-repository=/models --http-address=127.0.0.1 --grpc-address=127.0.0.1 --metrics-address=127.0.0.1
```

`--allow-http` and `--allow-grpc` default to true; NVIDIA recommends setting either to false when not required, and `--allow-metrics` switches off the metrics listener. For gRPC, `--grpc-use-ssl` with `--grpc-server-cert` and `--grpc-server-key` enables a TLS channel, and `--grpc-use-ssl-mutual` requires client certificates. HTTP has no TLS option; the proxy provides it. `--http-restricted-api` and `--grpc-restricted-protocol` fence the model-control APIs behind a shared-secret header, a useful second layer but not a substitute for the gateway.

## LM Studio (local server)

LM Studio's developer server is a desktop feature. The documentation addresses it at `http://localhost:1234` throughout (the port is a field in Developers Page > Server Settings), and "By default, LM Studio does not require authentication for API requests." The "Serve on Local Network" switch (or `lms server start --bind 0.0.0.0`) rebinds it to every interface; LM Studio's own note reads: "Any bind other than 127.0.0.1 exposes the server beyond localhost; we recommend enabling authentication." Leave that switch off. If another machine must reach it, first enable "Require Authentication" (LM Studio 0.4.0 or newer) and create a token under "Manage Tokens"; clients then send `Authorization: Bearer <token>`. The server settings list no TLS option, so anything beyond the local machine goes through a tailnet ([tailscale.md](tailscale.md)) or an authenticated TLS proxy, never a port-forward.

## The pattern, whatever the server

1. Bind to `127.0.0.1` (or a private container network); confirm with `ss -tlnp`.
2. Require a per-client API key at the server where supported, or at the proxy otherwise (bearer-token check per [ollama.md](ollama.md)); generate keys per [authentication.md](authentication.md).
3. TLS in front: [caddy.md](caddy.md), [nginx.md](nginx.md), [cloudflare.md](cloudflare.md), or [tailscale.md](tailscale.md).
4. Human-facing UIs on top of these servers ([open-webui.md](open-webui.md)) carry their own login and MFA ([mfa.md](mfa.md)).

## Verify

```bash
ss -tlnp | grep -E ':(8080|8000|8001|8002|3000|9000|30000|1234) '   # loopback only
curl -s https://models.example.com/v1/models            # 401 without a key
curl -s https://models.example.com/v1/models -H "Authorization: Bearer <key>"   # succeeds
```

## Sources (checked September 2026)

- llama.cpp server README (defaults, --api-key, SSL flags): https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- vLLM documentation: https://docs.vllm.ai/
- TGI launcher arguments (--hostname, --port, --api-key, --prometheus-port): https://huggingface.co/docs/text-generation-inference/reference/launcher
- TGI router source (what --api-key enforces): https://github.com/huggingface/text-generation-inference/blob/main/router/src/server.rs
- TGI repository (maintenance-mode notice, archived 2026-03-21): https://github.com/huggingface/text-generation-inference
- SGLang server arguments (--host, --port, --api-key, --admin-api-key, SSL flags; docs.sglang.ai redirects here): https://docs.sglang.io/advanced_features/server_arguments.html
- Triton secure deployment considerations: https://docs.nvidia.com/deeplearning/triton-inference-server/user-guide/docs/customization_guide/deploy.html
- Triton quickstart (default listeners on 8000, 8001, 8002): https://github.com/triton-inference-server/server/blob/main/docs/getting_started/quickstart.md
- Triton inference protocols (gRPC SSL flags, restricted APIs): https://github.com/triton-inference-server/server/blob/main/docs/customization_guide/inference_protocols.md
- Triton command line parser (address and port flags with defaults): https://github.com/triton-inference-server/server/blob/main/src/command_line_parser.cc
- LM Studio local server: https://lmstudio.ai/docs/developer/core/server
- LM Studio serve on local network: https://lmstudio.ai/docs/developer/core/server/serve-on-network
- LM Studio server settings: https://lmstudio.ai/docs/developer/core/server/settings
- LM Studio authentication: https://lmstudio.ai/docs/developer/core/authentication
- LM Studio OpenAI compatibility (localhost:1234 examples): https://lmstudio.ai/docs/developer/openai-compat
