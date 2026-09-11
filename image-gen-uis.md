# Image-generation UIs: ComfyUI, Stable Diffusion WebUI, InvokeAI, Fooocus

None of these tools ships real authentication by default, and each accepts arbitrary Python through custom nodes or extensions. **Binding one to a public interface is host compromise, not just data exposure.** Keep every instance on loopback and reach it only through a tunnel or an authenticated TLS proxy: [fronting-auth.md](fronting-auth.md), [cloudflare.md](cloudflare.md), [tailscale.md](tailscale.md), or a reverse proxy per [nginx.md](nginx.md)/[caddy.md](caddy.md).

If you run any of these in a container, do not stop at the network boundary: a compromised custom node or extension can still reach whatever the container can reach, so apply [container-hardening.md](container-hardening.md) (a non-root user, a read-only filesystem where the tool allows it, no unnecessary mounts) as a second layer, not a substitute for keeping the port off the network.

## ComfyUI

`--listen` with no argument binds to `0.0.0.0,::` (every IPv4 and IPv6 interface); given an address it binds only there. The default with the flag absent is `127.0.0.1`, and the default port is `8188`. There is no built-in login: the server accepts any workflow from anyone who can reach it.

Custom nodes are the bigger risk. They run as plain Python with the same privileges as the server process; ComfyUI's own security update warns that `eval`/`exec` calls in a node are "direct attack vectors" for remote code execution. ComfyUI-Manager (the default node installer) had its own unauthenticated-RCE advisory, CVE-2025-67303 (GHSA-95pq-hr8p-f5g7): an unprotected alternate channel left the manager's data and configuration directories insufficiently protected by ComfyUI's web API access control, letting an attacker upload arbitrary files for full system compromise with no credentials at all. The fix spans both projects and needs both minimums together: ComfyUI v0.3.76 or later (adds the protected-directory API the fix depends on) and ComfyUI-Manager v3.38 or later (contains the fix itself). Keep both at or above those versions, and only install nodes you trust regardless.

```bash
python main.py --listen 127.0.0.1 --port 8188
```

Front it with a TLS proxy that adds login before anything reaches port 8188. If you must run untrusted workflows, `--disable-all-custom-nodes` starts the server with none of them loaded, and `--whitelist-custom-nodes FOLDER...` re-allows specific folders despite that flag; neither is a substitute for keeping the port off the network.

## AUTOMATIC1111 Stable Diffusion WebUI

`--listen` launches gradio bound to `0.0.0.0` (default `False`, i.e. loopback); `--port` defaults to `7860`. `--gradio-auth user:pass` (comma-delimited for multiple users) or `--gradio-auth-path /path/to/file` requires a login before the UI loads; `--api-auth` does the same for the API. `--share` registers a public `*.gradio.live` relay URL, documented as intended for Colab, not a deployment mechanism, and it bypasses your network boundary entirely. `--enable-insecure-extension-access` reopens the extensions tab regardless of other flags and should stay off on anything reachable beyond loopback.

```bash
python launch.py --port 7860 --gradio-auth "admin:REPLACE_WITH_LONG_RANDOM_VALUE"
```

Even with `--gradio-auth` set, put TLS in front; the flag alone only gates plaintext HTTP. `--server-name` sets an explicit hostname if you bind somewhere other than the default.

## InvokeAI

InvokeAI's `invokeai.yaml` uses a flat schema (current as of InvokeAI 6.14.1, `schema_version: 4.0.2`): `host` (default `127.0.0.1`) and `port` (default `9090`) are top-level keys, not nested under a `Web Server` or `InvokeAI` section. Setting `host: 0.0.0.0` serves the local network with no login at all in the default single-user mode. `INVOKEAI_HOST` and `INVOKEAI_PORT` override the same settings from the environment.

An experimental multi-user mode exists: add `multiuser: true` to `invokeai.yaml` to require per-user login (username and password, stateless JWT sessions), and `strict_password_checking: true` to enforce a minimum password (8+ characters, upper, lower, and a digit) rather than just warning on a weak one. Restarting the server logs every user out. Outside multi-user mode, treat InvokeAI as having no login and keep it on loopback regardless.

```yaml
# invokeai.yaml, flat schema (schema_version 4.0.2, InvokeAI 6.14.1 and later)
host: 127.0.0.1
port: 9090
multiuser: true
strict_password_checking: true
```

## Fooocus

`--listen` exposes the UI to the network (optionally to a specific address); `--port` sets the port; `--share` registers a public `*.gradio.live` endpoint, same relay mechanism and same caution as above. Fooocus's own README states access is unauthenticated by default. Optional basic auth comes from an `auth.json` file with `user`/`pass` entries (no dedicated command-line auth flag exists); use it, but still keep the instance off any public interface.

```json
[
  {"user": "admin", "pass": "REPLACE_WITH_LONG_RANDOM_VALUE"}
]
```

## Verify

```bash
ss -tlnp | grep -E '8188|7860|9090'                 # each service on 127.0.0.1 only
curl -s http://203.0.113.10:8188/                    # ComfyUI from another host: connection refused
curl -s http://203.0.113.10:7860/                    # Stable Diffusion WebUI: connection refused
curl -s http://203.0.113.10:9090/                    # InvokeAI: connection refused
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9090/api/v1/boards/
                                                       # from the host itself, InvokeAI multiuser mode: 401
                                                       # without a Bearer token, never the app itself
curl -sI https://imagegen.example.com/                # via the proxy: TLS, and a login prompt
                                                       # or 401 without credentials, before the UI loads
```

## Common mistakes

- Adding `--listen`/`host: 0.0.0.0` "just to test from my phone" and forgetting it is still set a week later.
- Treating `--share` (Stable Diffusion WebUI, Fooocus) as a deployment option instead of a short-lived demo link.
- Installing a custom node or extension without reading it, on the assumption that "it's just a UI".
- Relying on `--gradio-auth` or Fooocus's `auth.json` alone: single-factor credentials over plain HTTP still leak on the wire without a TLS proxy in front.
- Assuming InvokeAI's multi-user mode is on by default; the base install has no login at all, so loopback binding still carries the whole burden.

## Sources (checked September 2026)

- ComfyUI Startup Flags (`--listen`, `--port` defaults): https://docs.comfy.org/development/comfyui-server/startup-flags
- ComfyUI custom node security standards (eval/exec prohibited): https://docs.comfy.org/registry/standards
- ComfyUI 2025 Jan Security Update (custom node code-execution risk): https://blog.comfy.org/p/comfyui-2025-jan-security-update
- ComfyUI-Manager security advisory, CVE-2025-67303, GHSA-95pq-hr8p-f5g7 (both minimum versions): https://github.com/Comfy-Org/ComfyUI-Manager/security/advisories/GHSA-95pq-hr8p-f5g7
- AUTOMATIC1111 Command Line Arguments and Settings wiki: https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/Command-Line-Arguments-and-Settings
- InvokeAI YAML Config (host/port defaults): https://invoke.ai/configuration/invokeai-yaml/
- InvokeAI Multi-User Administrator Guide: https://invoke.ai/features/multi-user-mode/admin-guide/
- Fooocus repository README (`--listen`, `--share`, auth.json): https://github.com/lllyasviel/Fooocus
