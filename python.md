# Python web apps: TLS and authentication

Covers Flask, FastAPI/Uvicorn, Gunicorn, and Django. Preferred production layout: bind the app server to `127.0.0.1` and terminate TLS in a reverse proxy ([caddy.md](caddy.md), [nginx.md](nginx.md)) or behind [cloudflare.md](cloudflare.md). The app servers can also terminate TLS themselves, shown below. Certificates: [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md).

## 1. TLS per server

Flask's built-in server (development only; it is not a production server, TLS or not):

```python
app.run(host="127.0.0.1", port=8443, ssl_context=("cert.pem", "key.pem"))
# ssl_context="adhoc" generates a throwaway self-signed cert; requires pyOpenSSL
```

Gunicorn (Flask/Django/WSGI in production):

```bash
gunicorn --bind 0.0.0.0:8443 \
  --certfile /etc/ssl/certs/server.crt \
  --keyfile  /etc/ssl/private/server.key \
  app:app
```

Uvicorn (FastAPI/ASGI):

```bash
uvicorn main:app --host 0.0.0.0 --port 8443 \
  --ssl-certfile /etc/ssl/certs/server.crt \
  --ssl-keyfile  /etc/ssl/private/server.key
```

Bind to `0.0.0.0` only when the process itself terminates TLS and authentication is in place; otherwise keep `127.0.0.1`.

## 2. Django settings for HTTPS

```python
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # only behind a proxy that sets it
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
```

`SECURE_PROXY_SSL_HEADER` must be set only when a proxy you control always sets that header; otherwise clients can spoof it. Run `python manage.py check --deploy` and fix what it reports.

## 3. Authentication

Follow [authentication.md](authentication.md). Framework specifics:

- Django's built-in auth already hashes passwords correctly; do not replace it with custom code.
- Flask and FastAPI have no user store; hash passwords with `argon2-cffi` or `bcrypt`:

```python
from argon2 import PasswordHasher
ph = PasswordHasher()
hash_ = ph.hash(password)
ph.verify(hash_, password)   # raises on mismatch
```

- Generate tokens and secrets with the standard library, and load them from the environment:

```python
import secrets
token = secrets.token_urlsafe(32)
```

- FastAPI's security utilities (`fastapi.security`) implement OAuth2/OIDC flows and API-key headers; use them rather than parsing `Authorization` by hand.
- Rate-limit login routes (for example with a proxy-level limit or a library such as slowapi for ASGI apps).

## 4. Client-side TLS discipline

Never ship `verify=False` (requests/httpx) or `ssl._create_unverified_context`. For an internal CA, point the client at it instead:

```bash
export REQUESTS_CA_BUNDLE=/path/ca.crt   # requests
export SSL_CERT_FILE=/path/ca.crt        # httpx and the ssl module
```

## 5. Verify

```bash
curl -sI https://example.com/        # succeeds without -k
curl -s  https://example.com/api     # expect 401/403 without credentials
ss -tlnp | grep -E 'gunicorn|uvicorn|python'   # behind a proxy: 127.0.0.1 only
```

## Sources (checked September 2026)

- Gunicorn documentation (settings reference): https://docs.gunicorn.org/
- Uvicorn settings reference: https://github.com/encode/uvicorn/blob/master/docs/settings.md
- Django deployment checklist: https://docs.djangoproject.com/en/stable/howto/deployment/checklist/
- argon2-cffi: https://argon2-cffi.readthedocs.io/
