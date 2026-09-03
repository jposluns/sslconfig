# Gradio: launch() authentication and TLS

Gradio binds to `127.0.0.1` by default. Two launch choices create exposure: `server_name="0.0.0.0"` (all interfaces) and `share=True` (a public `*.gradio.live` URL through Gradio's relay). Neither is acceptable without authentication.

## 1. Require a login

`launch()` takes credentials directly:

```python
import os
demo.launch(
    auth=(os.environ["GRADIO_USER"], os.environ["GRADIO_PASS"]),
    auth_message="Authorized users only",
)
```

`auth` also accepts a list of `(user, password)` tuples or a callable `f(username, password) -> bool`, which lets you check hashed credentials per [authentication.md](authentication.md). Keep the credentials in environment variables, not in the script.

## 2. Enable TLS

For a public deployment, prefer a reverse proxy or tunnel in front of a loopback-bound Gradio app: [caddy.md](caddy.md), [nginx.md](nginx.md), or [cloudflare.md](cloudflare.md). Gradio can also serve HTTPS itself with a certificate from [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md):

```python
demo.launch(
    server_name="0.0.0.0",
    server_port=8443,
    ssl_certfile="/path/cert.pem",
    ssl_keyfile="/path/key.pem",
    ssl_verify=False,   # only for self-signed certificates; skips validating your own cert
    auth=(os.environ["GRADIO_USER"], os.environ["GRADIO_PASS"]),
)
```

`ssl_keyfile_password` exists for encrypted keys. `ssl_verify=False` here affects how the launcher checks its own certificate; it is needed for self-signed certificates and unnecessary with a CA-issued one.

## 3. share=True is publication

`share=True` publishes the app at a random public URL for anyone who obtains the link, with your machine executing the requests. Use it only for short demos, always combined with `auth`, and shut it down afterwards. It is not a deployment mechanism; for persistent authenticated remote access use [cloudflare.md](cloudflare.md).

## 4. Verify

```bash
ss -tlnp | grep 7860                        # loopback unless deliberately exposed
curl -sI https://gradio.example.com/        # succeeds over TLS
# In a private browser window: the login form appears before the app.
```

## Sources (checked September 2026)

- Gradio Blocks.launch() parameters (auth, auth_message, ssl_certfile, ssl_keyfile, ssl_keyfile_password, ssl_verify, server_name, share): https://www.gradio.app/docs/gradio/blocks
