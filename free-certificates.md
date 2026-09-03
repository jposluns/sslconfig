# Free publicly trusted certificates (ACME)

Publicly trusted certificates are free through ACME certificate authorities such as Let's Encrypt and ZeroSSL. Browsers and libraries accept them without any client-side configuration, which makes them the correct choice for every service with a public DNS name. Use [self-signed.md](self-signed.md) only when no public domain exists, or [cloudflare.md](cloudflare.md) when the host cannot accept inbound connections.

## Prerequisites

- A DNS record (`A` or `AAAA`, or `CNAME`) for the hostname, pointing at the server.
- For the HTTP-01 challenge: inbound port 80 reachable from the internet.
- For the TLS-ALPN-01 challenge (used by Caddy and Traefik): inbound port 443.
- For the DNS-01 challenge (required for wildcard certificates): API access to the DNS provider.

If none of these is possible, use [cloudflare.md](cloudflare.md) instead.

## Certbot with Let's Encrypt

Certbot is the reference ACME client. Install it from your distribution or via snap:

```bash
# Debian/Ubuntu
sudo apt install certbot python3-certbot-nginx python3-certbot-apache

# Any distribution with snapd
sudo snap install --classic certbot
sudo ln -s /snap/bin/certbot /usr/bin/certbot
```

Issue and install in one step when certbot supports your web server:

```bash
sudo certbot --nginx  -d example.com -d www.example.com
sudo certbot --apache -d example.com -d www.example.com
```

Issue only the certificate when you configure the server yourself, or when no web server is running yet:

```bash
# Standalone: certbot binds port 80 itself; stop anything using it first
sudo certbot certonly --standalone -d example.com

# Webroot: the existing web server keeps running and serves the challenge files
sudo certbot certonly --webroot -w /var/www/html -d example.com
```

Wildcard certificates require the DNS-01 challenge through a DNS plugin (for example `python3-certbot-dns-cloudflare`), with provider API credentials in a root-owned file:

```bash
sudo certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /root/.secrets/cloudflare.ini \
  -d example.com -d "*.example.com"
```

Certificates land in stable paths that server configuration should reference directly:

```
/etc/letsencrypt/live/example.com/fullchain.pem   # certificate plus chain
/etc/letsencrypt/live/example.com/privkey.pem     # private key
```

## Renewal

Let's Encrypt certificates are valid for 90 days at the time of writing, so renewal must be automated. Package and snap installs of certbot register a systemd timer or cron job that runs `certbot renew` for you. Confirm that it works and reload the server after each renewal:

```bash
sudo certbot renew --dry-run
sudo certbot renew --deploy-hook "systemctl reload nginx"
```

Set the deploy hook once with `certonly`/`renew`, or drop a script into `/etc/letsencrypt/renewal-hooks/deploy/`. A certificate that issues once and then expires in production is the most common ACME failure; the dry run belongs in your deployment checklist.

## Rate limits

Let's Encrypt enforces per-domain issuance limits. Test against the staging environment (`certbot --staging` or `--test-cert`) until the configuration works, then issue the real certificate. Current limits: https://letsencrypt.org/docs/rate-limits/

## Alternatives

- **ZeroSSL**: free certificates over ACME. Some clients need External Account Binding (EAB) credentials from the ZeroSSL dashboard; the acme.sh client registers with ZeroSSL by default.
- **acme.sh**: a dependency-light shell ACME client supporting many DNS providers, useful where certbot is unavailable. Install from the repository release rather than piping a downloaded script straight into a shell. https://github.com/acmesh-official/acme.sh
- **Caddy and Traefik**: obtain and renew certificates themselves with no external client; see [caddy.md](caddy.md) and [traefik.md](traefik.md). This is the lowest-effort correct option for new deployments.
- **Cloudflare origin certificates**: free and valid for long periods, but trusted only by Cloudflare's edge, so they are usable only behind the Cloudflare proxy; see [cloudflare.md](cloudflare.md).

## Verify

```bash
sudo certbot certificates                       # what is issued and when it expires
curl -sI https://example.com/                   # succeeds without -k
openssl s_client -connect example.com:443 -servername example.com </dev/null \
  | openssl x509 -noout -issuer -dates
```

A certificate alone does not protect anything: continue with the server guide for your stack and with [authentication.md](authentication.md).

## Sources (checked September 2026)

- Let's Encrypt documentation: https://letsencrypt.org/docs/
- Certbot instructions: https://certbot.eff.org/
- ZeroSSL: https://zerossl.com/
- acme.sh: https://github.com/acmesh-official/acme.sh
