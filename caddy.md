# Caddy: TLS and authentication

Caddy 2 obtains, installs, and renews publicly trusted certificates automatically and redirects HTTP to HTTPS by default. For a new deployment with a public domain, it is the shortest correct path to HTTPS: no ACME client, no renewal timer, no redirect block.

## 1. Public site with automatic HTTPS

`/etc/caddy/Caddyfile`:

```caddyfile
{
    email admin@example.com        # ACME account contact for expiry notices
}

app.example.com {
    reverse_proxy 127.0.0.1:3000
}
```

Requirements: the DNS record points at this host, and ports 80 and 443 are reachable from the internet. Start or reload:

```bash
sudo systemctl reload caddy
```

That is the whole TLS setup. Certificates come from Let's Encrypt or ZeroSSL and renew automatically.

## 2. Internal hosts without a public domain

`tls internal` makes Caddy issue from its own local CA instead of a public one:

```caddyfile
app.internal {
    tls internal
    reverse_proxy 127.0.0.1:3000
}
```

Clients must trust Caddy's root CA (on the Caddy host itself, `caddy trust` installs it into the local trust store). Distribution of that trust to other machines follows [self-signed.md](self-signed.md). To use certificate files you generated yourself instead: `tls /path/cert.pem /path/key.pem`.

## 3. Require authentication

Application-level login is preferable ([authentication.md](authentication.md)). At the proxy, use `basic_auth` (named `basicauth` before Caddy v2.8.0). Hash the password first:

```bash
caddy hash-password        # prompts, outputs a bcrypt hash
```

```caddyfile
app.example.com {
    basic_auth {
        admin $2a$14$REPLACE_WITH_HASH_FROM_caddy_hash-password
    }
    reverse_proxy 127.0.0.1:3000
}
```

To protect only part of a site, wrap the directive in a matcher:

```caddyfile
    @admin path /admin/*
    basic_auth @admin {
        admin $2a$14$REPLACE_WITH_HASH
    }
```

`basic_auth` is single-factor. For human-facing sites, add MFA with the `forward_auth` directive (Caddy 2.5.1 and later) pointed at an [Authelia](https://www.authelia.com/) portal, or front the site with Cloudflare Access; options in [mfa.md](mfa.md).

## 4. Verify

```bash
caddy validate --config /etc/caddy/Caddyfile
curl -sI http://app.example.com/     # expect a redirect to https://
curl -sI https://app.example.com/    # expect 401 without credentials once auth is on
```

## Common mistakes

- The app also listens on a public interface, bypassing Caddy; bind it to `127.0.0.1`.
- Blocking port 80 at the firewall: Caddy needs it for the HTTP-01 challenge and for the automatic redirect.
- Putting the literal password in the Caddyfile; `basic_auth` takes the bcrypt hash, not the password.

## Sources (checked September 2026)

- Automatic HTTPS: https://caddyserver.com/docs/automatic-https
- basic_auth directive: https://caddyserver.com/docs/caddyfile/directives/basic_auth
- tls directive: https://caddyserver.com/docs/caddyfile/directives/tls
