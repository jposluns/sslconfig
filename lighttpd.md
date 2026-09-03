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

`mod_redirect` is built in. Per the lighttpd wiki:

```
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

## 4. Verify

```bash
sudo lighttpd -tt -f /etc/lighttpd/lighttpd.conf && sudo systemctl reload lighttpd
curl -sI http://example.com/        # expect a redirect to https://
curl -sI https://example.com/       # expect 401 without credentials once auth is on
```

## Common mistakes

- Loading `mod_openssl` but leaving the `:80` socket serving content instead of only the redirect.
- Forgetting the `[::]:443` socket, leaving IPv6 clients on plain HTTP.
- Pointing `ssl.pemfile` at a certificate without its chain; use `fullchain.pem`.

## Sources (checked September 2026)

- lighttpd TLS documentation: https://redmine.lighttpd.net/projects/lighttpd/wiki/Docs_SSL
- lighttpd mod_auth documentation: https://redmine.lighttpd.net/projects/lighttpd/wiki/Docs_ModAuth
- lighttpd HTTP-to-HTTPS redirect how-to: https://redmine.lighttpd.net/projects/lighttpd/wiki/HowToRedirectHttpToHttps
