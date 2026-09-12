# Apache HTTP Server: TLS and authentication

Applies to Apache 2.4. Get a certificate first: [free-certificates.md](free-certificates.md) for a public host (note that `certbot --apache` performs steps 1 to 3 of this guide for you), or [self-signed.md](self-signed.md) for internal use.

## 1. Enable the modules

```bash
# Debian/Ubuntu
sudo a2enmod ssl headers
sudo a2ensite default-ssl        # or your own :443 vhost file

# RHEL/Fedora
sudo dnf install mod_ssl httpd-tools
```

## 2. Configure the HTTPS virtual host

```apache
<VirtualHost *:443>
    ServerName example.com
    DocumentRoot /var/www/html

    SSLEngine on
    SSLCertificateFile      /etc/letsencrypt/live/example.com/fullchain.pem
    SSLCertificateKeyFile   /etc/letsencrypt/live/example.com/privkey.pem

    # TLS 1.2 minimum. The TLSv1.3 keyword needs Apache 2.4.36+ with OpenSSL 1.1.1+;
    # on older builds use: SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
    SSLProtocol -all +TLSv1.2 +TLSv1.3

    # Send HSTS only once HTTPS is confirmed working
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"
</VirtualHost>
```

On Apache 2.4.8 and later, `SSLCertificateFile` may contain the certificate plus its chain (certbot's `fullchain.pem`), and `SSLCertificateChainFile` is deprecated. For cipher suites beyond the protocol floor, generate a current list with the [Mozilla SSL Configuration Generator](https://ssl-config.mozilla.org/) rather than copying one from an old tutorial.

## 3. Redirect HTTP to HTTPS

```apache
<VirtualHost *:80>
    ServerName example.com
    Redirect permanent / https://example.com/
</VirtualHost>
```

Keep port 80 serving only this redirect (and ACME HTTP-01 challenges if certbot uses the webroot method).

## 4. Require authentication

Application-level login is preferable ([authentication.md](authentication.md)). To gate a whole site or path at the server, use basic authentication over TLS with bcrypt-hashed entries:

```bash
sudo htpasswd -B -c /etc/apache2/.htpasswd admin     # -c only for the first user
```

```apache
<Location "/">
    AuthType Basic
    AuthName "Restricted"
    AuthUserFile /etc/apache2/.htpasswd
    Require valid-user
</Location>
```

For machine-to-machine links, mutual TLS is stronger than passwords:

```apache
SSLCACertificateFile /etc/ssl/certs/internal-ca.crt
SSLVerifyClient require
SSLVerifyDepth 2
```

Basic authentication is single-factor, and Authelia documents Apache as unsupported for its portal. For human-facing sites, add MFA by making Apache an OIDC client with [mod_auth_openidc](https://github.com/OpenIDC/mod_auth_openidc), with MFA enforced at the identity provider, or by fronting the site with Cloudflare Access; options in [mfa.md](mfa.md).

## 5. Verify

These are read-and-judge checks. `curl` exits 0 for a 401 as readily as for a 200, so the
status code is printed and you compare it; nothing here fails on its own.

```bash
sudo apachectl configtest && sudo systemctl reload apache2   # httpd on RHEL
curl -sI http://example.com/            # expect 301 with a https:// Location
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/
                                        # 200 before section 4, 401 after it. Once
                                        # authentication is on, a 200 here is the finding

# Read every listener. Do not filter to the ports you expect: a filter cannot show you a port
# you did not think of, which is the whole question, and `grep ':(80|443)'` also matches an
# address such as [2001:db8:80::1]:9000.
ss -tlnp

# A request whose Host matches no ServerName or ServerAlias does not fail. Apache says it falls
# through to "the first listed virtual host that matches" the address and port, so a vhost
# listed before yours over the same DocumentRoot answers without your authentication. Ask for
# the PROTECTED path rather than `/`, because `/` can legitimately be public:
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: not-configured.example' \
  https://example.com/REPLACE_WITH_A_PROTECTED_PATH
                                        # 401 is the pass. 200 means another vhost served the
                                        # protected resource with no authentication. 421 means
                                        # the TLS configuration for that combination was
                                        # rejected before any of this was decided, so the probe
                                        # says nothing: curl sends SNI for the URL's hostname
                                        # and not for the Host header, and Apache's
                                        # SSLVHostSNIPolicy decides whether that pairing is
                                        # allowed at all
```

## Common mistakes

- Serving the application on port 80 next to the HTTPS vhost instead of only redirecting.
- Enabling `mod_ssl` without `Header`/HSTS, leaving downgrade open on repeat visits.
- World-readable private keys; keep them `0600` and root-owned.
- Protecting `/admin` but leaving `/api` open; `Require` rules apply per path, so enumerate what is public.

## Sources (checked September 2026)

- Apache SSL/TLS how-to: https://httpd.apache.org/docs/2.4/ssl/ssl_howto.html
- Apache authentication how-to: https://httpd.apache.org/docs/2.4/howto/auth.html
- Apache name-based virtual hosts, for which vhost answers an unmatched Host header: https://httpd.apache.org/docs/2.4/vhosts/name-based.html
- Apache mod_ssl `SSLVHostSNIPolicy`, for the 421 a mismatched SNI and Host pairing can produce: https://httpd.apache.org/docs/2.4/mod/mod_ssl.html#sslvhostsnipolicy
- Mozilla SSL Configuration Generator: https://ssl-config.mozilla.org/
