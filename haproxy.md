# HAProxy: TLS termination and authentication

Get a certificate first ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)). HAProxy loads the certificate and private key from one combined PEM file:

```bash
sudo mkdir -p /etc/haproxy/certs
sudo bash -c 'cat /etc/letsencrypt/live/example.com/fullchain.pem \
              /etc/letsencrypt/live/example.com/privkey.pem \
              > /etc/haproxy/certs/example.com.pem'
sudo chmod 600 /etc/haproxy/certs/example.com.pem
```

Re-run the concatenation from a certbot deploy hook so renewals reach HAProxy.

## 1. Terminate TLS and redirect HTTP

```haproxy
global
    ssl-default-bind-options ssl-min-ver TLSv1.2

defaults
    mode http
    timeout connect 5s
    timeout client  30s
    timeout server  30s

frontend web
    bind :80
    bind :443 ssl crt /etc/haproxy/certs/example.com.pem
    http-request redirect scheme https code 301 unless { ssl_fc }
    http-response set-header Strict-Transport-Security "max-age=31536000; includeSubDomains"
    default_backend app

backend app
    server app1 127.0.0.1:3000 check
```

`ssl-min-ver` requires HAProxy 1.8 or later. For explicit cipher lists use the [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/).

## 2. Require authentication

Application-level login is preferable ([authentication.md](authentication.md)). At the proxy, define a userlist with a crypt(3)-hashed password and demand it:

```bash
openssl passwd -6        # prompts, outputs a $6$ SHA-512 crypt hash
```

```haproxy
userlist admins
    user admin password $6$REPLACE_WITH_HASH

backend app
    http-request auth realm Restricted unless { http_auth(admins) }
    server app1 127.0.0.1:3000 check
```

Hashed `password` entries rely on the system's crypt(3); `$6$` works on glibc-based Linux. Avoid `insecure-password`, which stores the password in cleartext in the configuration file. For machine-to-machine access, client certificates are stronger: add `verify required ca-file /etc/ssl/certs/internal-ca.crt` to the `bind :443` line.

Basic authentication here is single-factor. For human-facing sites, add MFA with an [Authelia](https://www.authelia.com/) portal (HAProxy is supported through Authelia's Lua module) or by fronting the site with Cloudflare Access; options in [mfa.md](mfa.md).

## 3. Verify

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg && sudo systemctl reload haproxy
curl -sI http://example.com/        # expect 301 with a https:// Location
curl -sI https://example.com/       # expect 401 without credentials once auth is on
```

## Common mistakes

- Copying only `fullchain.pem` into the crt file; HAProxy needs the private key in the same PEM.
- Renewing the certificate without rebuilding the combined PEM or reloading HAProxy.
- Backends reachable directly on `0.0.0.0`, bypassing the proxy; bind them to `127.0.0.1` and confirm with `ss -tlnp`.

## Sources (checked September 2026)

- HAProxy documentation: https://www.haproxy.org/ (configuration manual for your installed version)
- Mozilla SSL Configuration Generator: https://ssl-config.mozilla.org/
