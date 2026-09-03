# Jupyter: password and TLS

An exposed Jupyter server is remote code execution for whoever finds it. Jupyter Server (which also runs JupyterLab and Notebook 7) ships with token authentication on and binds to localhost; keep both properties when you change anything else. For multi-user or internet-facing use, prefer JupyterHub or access through [cloudflare.md](cloudflare.md) over exposing a single server directly.

## 1. Generate the config and set a password

```bash
jupyter server --generate-config     # writes ~/.jupyter/jupyter_server_config.py
jupyter server password              # prompts; stores the hashed password in jupyter_server_config.json
```

## 2. Enable TLS

Get a certificate per [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md), then in `~/.jupyter/jupyter_server_config.py`:

```python
c.ServerApp.certfile = '/absolute/path/to/cert.pem'
c.ServerApp.keyfile  = '/absolute/path/to/key.pem'
```

Or per invocation:

```bash
jupyter lab --certfile=/path/cert.pem --keyfile=/path/key.pem
```

Once TLS is on, connect via `https://`; the server no longer answers plain `http://` usefully.

## 3. Exposure rules

- Do not set `c.ServerApp.ip = '0.0.0.0'` (or `--ip 0.0.0.0`) without the password from step 1 **and** TLS from step 2 in place.
- Never blank the token or password settings to make login prompts go away; that is exactly the configuration internet scanners look for.
- A reverse proxy with its own auth ([nginx.md](nginx.md), [caddy.md](caddy.md)) or Cloudflare Access ([cloudflare.md](cloudflare.md)) in front of a loopback-bound Jupyter is a sound alternative to native TLS, and adds a second factor in the Access case.

## 4. Verify

```bash
curl -skI https://host:8888/           # answers over TLS
# In a private browser window: the server asks for the password before showing any notebook.
ss -tlnp | grep 8888                   # bound to 127.0.0.1 unless deliberately exposed
```

## Sources (checked September 2026)

- Jupyter Server public server guide: https://jupyter-server.readthedocs.io/en/latest/operators/public-server.html
