# lighttpd: TLS and authentication

Applies to lighttpd 1.4.56 and later, which disables SSLv2/SSLv3/TLS 1.0/TLS 1.1 by default. Get a certificate first: [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md).

## 1. Enable TLS

```
server.modules += ( "mod_openssl" )

$SERVER["socket"] == ":443" {
    ssl.engine  = "enable"
    ssl.pemfile = "/etc/letsencrypt/live/example.com/fullchain.pem"
    ssl.privkey = "/etc/letsencrypt/live/example.com/privkey.pem"
}

$SERVER["socket"] == "[::]:443" {
    ssl.engine  = "enable"
    ssl.pemfile = "/etc/letsencrypt/live/example.com/fullchain.pem"
    ssl.privkey = "/etc/letsencrypt/live/example.com/privkey.pem"
}
```

Version notes:

- `ssl.privkey` exists from lighttpd 1.4.53. On older versions, concatenate certificate and key into one file and point `ssl.pemfile` at it.
- To set the protocol floor explicitly (recent versions already default to TLS 1.2):

```
ssl.openssl.ssl-conf-cmd = ( "MinProtocol" => "TLSv1.2" )
```

## 2. Redirect HTTP to HTTPS

`mod_redirect` must be loaded: only `mod_indexfile`, `mod_dirlisting`, and `mod_staticfile` load without being listed in `server.modules`. Per the lighttpd wiki:

```
server.modules += ( "mod_redirect" )

$HTTP["scheme"] == "http" {
    url.redirect = ("" => "https://${url.authority}${url.path}${qsa}")
    url.redirect-code = 308        # explicit on versions before 1.4.75
}
```

## 3. Require authentication

Application-level login is preferable ([authentication.md](authentication.md)). Basic authentication at the server, over TLS only:

```
server.modules += ( "mod_auth", "mod_authn_file" )

auth.backend = "htpasswd"
auth.backend.htpasswd.userfile = "/etc/lighttpd/lighttpd.user"

auth.require = ( "/" =>
  (
    "method"  => "basic",
    "realm"   => "Restricted",
    "require" => "valid-user"
  )
)
```

Create the user file with Apache's `htpasswd` (package `apache2-utils` or `httpd-tools`). The lighttpd htpasswd backend reads `user:crypt()-hashed-password` entries; check the mod_auth documentation below for the hash algorithms your lighttpd build accepts before choosing an `htpasswd` flag.

Basic authentication is single-factor, and lighttpd is absent from Authelia's supported-proxy list. Add MFA by fronting the service with Cloudflare Access ([cloudflare.md](cloudflare.md)) or an MFA-capable proxy; options in [mfa.md](mfa.md).

## 4. Verify

These are read-and-judge checks: the status code is printed and you compare it.

```bash
sudo lighttpd -tt -f /etc/lighttpd/lighttpd.conf && sudo systemctl reload lighttpd
curl -sI http://example.com/        # expect a redirect to https://
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/
                                    # expect 401 without credentials once auth is on

# Read every listener rather than filtering to the ports you expect. The checks above prove
# the front door asks for credentials; they do not prove it is the only door, and a filtered
# list cannot show you a port you did not think of.
ss -tlnp

# `auth.require` can sit at the top level or inside a `$HTTP["host"]` conditional, and a
# conditional one applies only to the hosts it names. If yours is conditional, a request
# carrying a host it does not name is served by the global configuration instead. That
# conditional reads the Host HEADER, so setting the header is the right test here, unlike
# Apache, which selects its virtual host by the SNI name when the connection is TLS:
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: not-configured.example' \
  https://example.com/REPLACE_WITH_A_PROTECTED_PATH
                                    # 401 is the pass. 200 means the protected path is served
                                    # without authentication to anyone who sends another host
```

## Common mistakes

- Loading `mod_openssl` but leaving the `:80` socket serving content instead of only the redirect.
- Forgetting the `[::]:443` socket, leaving IPv6 clients on plain HTTP.
- Pointing `ssl.pemfile` at a certificate without its chain; use `fullchain.pem`.

## Sources (checked September 2026)

- lighttpd TLS documentation: https://redmine.lighttpd.net/projects/lighttpd/wiki/Docs_SSL
- lighttpd mod_auth documentation, including `auth.require` inside a `$HTTP["host"]` conditional: https://redmine.lighttpd.net/projects/lighttpd/wiki/Mod_auth
- lighttpd HTTP-to-HTTPS redirect how-to: https://redmine.lighttpd.net/projects/lighttpd/wiki/HowToRedirectHttpToHttps
- lighttpd configuration options (`server.modules`, the three modules loaded by default): https://redmine.lighttpd.net/projects/lighttpd/wiki/Docs_ConfigurationOptions
