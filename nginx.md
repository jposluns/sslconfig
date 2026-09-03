# nginx: TLS and authentication

Get a certificate first: [free-certificates.md](free-certificates.md) for a public host (note that `certbot --nginx` edits the server block for you), or [self-signed.md](self-signed.md) for internal use.

## 1. HTTPS server block

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;                     # nginx 1.25.1+; on older versions: listen 443 ssl http2;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    # Send HSTS only once HTTPS is confirmed working
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://127.0.0.1:3000;      # your app, bound to loopback only
        proxy_set_header Host              $host;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

For explicit cipher lists, generate them with the [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/) instead of copying from old tutorials; the protocol floor above is the part that must not be omitted.

## 2. Redirect HTTP to HTTPS

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name example.com;
    return 301 https://$host$request_uri;
}
```

## 3. Require authentication

Application-level login is preferable ([authentication.md](authentication.md)). To gate a site or path at the proxy, use basic authentication over TLS:

```bash
sudo apt install apache2-utils          # provides htpasswd
sudo htpasswd -B -c /etc/nginx/.htpasswd admin
```

```nginx
    location / {
        auth_basic           "Restricted";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://127.0.0.1:3000;
    }
```

Mutual TLS for machine-to-machine access:

```nginx
    ssl_client_certificate /etc/ssl/certs/internal-ca.crt;
    ssl_verify_client on;
```

## 4. Verify

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -sI http://example.com/        # expect 301 with a https:// Location
curl -sI https://example.com/       # expect 200 without -k
curl -s  https://example.com/api    # expect 401/403 without credentials
```

## Common mistakes

- The app still listens on `0.0.0.0:3000` next to the proxy, so the proxy's TLS and auth are bypassed. Bind the app to `127.0.0.1` and confirm with `ss -tlnp`.
- `add_header` in a `location` block silently drops headers inherited from `server`; keep HSTS at the `server` level with `always`.
- A default `server` block that still serves plain HTTP for unmatched hosts; give the catch-all server the same redirect.
- `auth_basic` on `/` but a later `location` (for example `/static`) that re-opens access; `auth_basic off` should be a deliberate exception, not an accident.

## Sources (checked September 2026)

- Configuring HTTPS servers: https://nginx.org/en/docs/http/configuring_https_servers.html
- ngx_http_auth_basic_module: https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html
- Mozilla SSL Configuration Generator: https://ssl-config.mozilla.org/
