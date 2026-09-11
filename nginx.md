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

Basic authentication is single-factor. For human-facing sites, add MFA with the `auth_request` mechanism pointed at an [Authelia](https://www.authelia.com/) or [oauth2-proxy](https://github.com/oauth2-proxy/oauth2-proxy) portal, or front the site with Cloudflare Access; options in [mfa.md](mfa.md).

## 4. Bound the expensive endpoints

An authenticated caller can still exhaust an inference, upload, or job-submission endpoint, which is
denial of wallet when the endpoint costs GPU time ([authentication.md](authentication.md)). Declare the
zones in the `http` block and apply the limits per location.

```nginx
# http block, alongside the other http-level directives
limit_req_zone  $binary_remote_addr zone=api:10m rate=10r/s;
limit_conn_zone $binary_remote_addr zone=apiconn:10m;

# merge these into the SAME server block from section 1, not a new one
server {
    client_max_body_size 10m;                   # 413 above this; the default is 1m

    location / {
        auth_basic           "Restricted";      # keep the section 3 directives here
        auth_basic_user_file /etc/nginx/.htpasswd;

        limit_req  zone=api burst=20 nodelay;   # 503 once the burst is spent
        limit_conn apiconn 10;                  # concurrent connections per client address
        proxy_read_timeout 60s;
        proxy_pass http://127.0.0.1:3000;
    }
}
```

Put the limits in the location that already carries authentication. nginx selects the single most
specific matching location and does not inherit `auth_basic` from a less specific one, so adding a
separate `location /api/` for the limits would create a route that is rate limited and unauthenticated.
If you do split them out, repeat the `auth_basic` directives in each location, or move them to the
`server` level so every location inherits them.

`proxy_read_timeout` bounds the gap between successive reads from the upstream, not the total duration
of a response. A stream that keeps sending stays alive indefinitely under a 60s value; a stream that
stalls for 61s is cut. Choose it from the longest acceptable silence, and note that raising it lengthens
that tolerance rather than removing the timeout.

## 5. Verify

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -sI http://example.com/        # expect 301 with a https:// Location
curl -sI https://example.com/       # expect 200 without -k
curl -s  https://example.com/api    # expect 401/403 without credentials
head -c 1M  /dev/zero > /tmp/under.bin && head -c 11M /dev/zero > /tmp/over.bin
curl -s -o /dev/null -w '%{http_code}\n' -u admin:REPLACE_WITH_PASSWORD --data-binary @/tmp/under.bin https://example.com/
                                    # positive control: under the limit, must NOT be 413
curl -s -o /dev/null -w '%{http_code}\n' -u admin:REPLACE_WITH_PASSWORD --data-binary @/tmp/over.bin  https://example.com/
                                    # 413. Send from a FILE, not a pipe: curl sets Content-Length from a
                                    # file, so nginx refuses at the headers. Piped stdin is sent chunked
                                    # with no length, which a backend may reject instead, and a 413 from
                                    # the backend looks identical here
seq 1 40 | xargs -P 40 -I{} curl -s -o /dev/null -w '%{http_code}\n' -u admin:REPLACE_WITH_PASSWORD https://example.com/ | sort | uniq -c
                                    # 503 must appear. Run them CONCURRENTLY: a sequential loop pays a
                                    # TLS handshake per request and can stay under 10r/s, so every
                                    # request is admitted and the check passes while no limit exists
rm -f /tmp/under.bin /tmp/over.bin
ss -tlnp | grep 3000                # the app itself: 127.0.0.1 only, never 0.0.0.0. All the checks
                                    # above pass while the app also answers directly on port 3000,
                                    # which bypasses this proxy's TLS and its authentication. That
                                    # bypass is the first common mistake below, and the first item in
                                    # common-mistakes.md
```

## Common mistakes

- The app still listens on `0.0.0.0:3000` next to the proxy, so the proxy's TLS and auth are bypassed. Bind the app to `127.0.0.1` and confirm with `ss -tlnp`.
- `add_header` in a `location` block silently drops headers inherited from `server`; keep HSTS at the `server` level with `always`.
- A default `server` block that still serves plain HTTP for unmatched hosts; give the catch-all server the same redirect.
- `auth_basic` on `/` but a later `location` (for example `/static`) that re-opens access; `auth_basic off` should be a deliberate exception, not an accident.

## Sources (checked September 2026)

- Configuring HTTPS servers: https://nginx.org/en/docs/http/configuring_https_servers.html
- Core module (`client_max_body_size`): https://nginx.org/en/docs/http/ngx_http_core_module.html
- Request rate limiting (`limit_req_zone`, `limit_req`, `burst`, `nodelay`): https://nginx.org/en/docs/http/ngx_http_limit_req_module.html
- Connection limiting (`limit_conn_zone`, `limit_conn`): https://nginx.org/en/docs/http/ngx_http_limit_conn_module.html
- Proxy module (`proxy_read_timeout`, `proxy_send_timeout`, `proxy_connect_timeout`): https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- ngx_http_auth_basic_module: https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html
- Mozilla SSL Configuration Generator: https://ssl-config.mozilla.org/
