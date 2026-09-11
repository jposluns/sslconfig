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

## 3. Bound the expensive endpoints

The timeouts in section 1 are half of this. Add a concurrency cap with `maxconn`, which in `global` is
the maximum per-process concurrent connections and in a frontend caps that frontend.

HAProxy has **no single request-body-size directive**. The rule below uses the `req.body_size` fetch,
which the manual defines as the *advertised* length of the body, so for a request carrying
`Content-Length` it reads that value. Two limits are worth knowing. `option http-buffer-request` makes
HAProxy wait for the complete body, or for a full request buffer, before the frontend rules run, so this
does not refuse at the headers and the upload is buffered before it is rejected. And a chunked request
advertises no length at all, so the fetch falls back to what is available and `tune.bufsize` bounds it.
Enforce the real limit at the application and treat this as a front-door guard against the common case.

```haproxy
global
    maxconn 4096

frontend web
    maxconn 2000
    option  http-buffer-request
    http-request deny deny_status 413 if { req.body_size gt 10485760 }
```

## 4. Verify

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg && sudo systemctl reload haproxy
curl -sI http://example.com/        # expect 301 with a https:// Location
curl -sI https://example.com/       # expect 401 without credentials once auth is on
head -c 1M /dev/zero > /tmp/under.bin && head -c 11M /dev/zero > /tmp/over.bin
curl -s -o /dev/null -w '%{http_code}\n' -u admin:REPLACE_WITH_PASSWORD --data-binary @/tmp/under.bin https://example.com/
                                    # positive control: under the limit, must NOT be 413
curl -s -o /dev/null -w '%{http_code}\n' -u admin:REPLACE_WITH_PASSWORD --data-binary @/tmp/over.bin  https://example.com/
                                    # 413. req.body_size reads the advertised Content-Length, which curl
                                    # sets here. A chunked upload advertises none and is not covered.
                                    # A backend limit returns the same code, so remove the http-request
                                    # deny line and re-run to attribute the refusal to HAProxy
rm -f /tmp/under.bin /tmp/over.bin
ss -tlnp | grep 3000                # the backend itself: 127.0.0.1 only, never 0.0.0.0. All the checks
                                    # above pass while the backend also answers directly on port 3000,
                                    # which bypasses HAProxy's TLS and its authentication
```

## Common mistakes

- Copying only `fullchain.pem` into the crt file; HAProxy needs the private key in the same PEM.
- Renewing the certificate without rebuilding the combined PEM or reloading HAProxy.
- Backends reachable directly on `0.0.0.0`, bypassing the proxy; bind them to `127.0.0.1` and confirm with `ss -tlnp`.

## Sources (checked September 2026)

- HAProxy documentation: https://www.haproxy.org/ (configuration manual for your installed version)
- Configuration manual (`maxconn`, `option http-buffer-request`, `req.body_size`, `tune.bufsize`, `http-request deny deny_status`): https://docs.haproxy.org/3.0/configuration.html
- Mozilla SSL Configuration Generator: https://ssl-config.mozilla.org/
