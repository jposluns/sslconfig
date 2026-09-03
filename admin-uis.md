# Admin panels: phpMyAdmin, pgAdmin, mongo-express, Grafana, Prometheus

Database and monitoring panels are the most-scanned targets on the internet, and several ship with known default credentials. One rule dominates everything tool-specific below: **an admin panel is never reachable from the public internet.** Bind it to loopback and reach it through SSH port forwarding, a VPN or tailnet ([tailscale.md](tailscale.md)), or Cloudflare Access ([cloudflare.md](cloudflare.md)); anything public sits behind a TLS proxy with its own authentication ([nginx.md](nginx.md), [caddy.md](caddy.md)) plus MFA ([mfa.md](mfa.md)).

## mongo-express

Ships with basic auth `admin`:`pass` by default; its own README calls this unsafe. Set your own credentials and keep it private:

```
ME_CONFIG_BASICAUTH_USERNAME=<your-admin>
ME_CONFIG_BASICAUTH_PASSWORD=<long random value>
```

These control only the web login; MongoDB credentials go in `ME_CONFIG_MONGODB_URL` ([mongodb.md](mongodb.md) hardens the database itself).

## Grafana

- First sign-in uses `admin`/`admin` and prompts for a new password; set a strong one immediately and create individual accounts for everyone else.
- Disable anonymous access if it was enabled, and prefer SSO with MFA enforced at the identity provider.
- Native HTTPS in `grafana.ini`:

```ini
[server]
protocol = https
cert_file = /etc/grafana/grafana.crt
cert_key  = /etc/grafana/grafana.key
```

## Prometheus

No authentication at all by default. Give it a web configuration file and start with `--web.config.file=web.yml`:

```yaml
basic_auth_users:
  admin: $2b$12$REPLACE_WITH_BCRYPT_HASH    # htpasswd -nB admin, hash part
```

The same file carries TLS (`tls_server_config` with `cert_file` and `key_file`; see the Prometheus TLS guide below). Validate with `promtool check web-config web.yml`. Exporters and Alertmanager need the same treatment.

## phpMyAdmin and pgAdmin

Neither belongs on a public vhost. Serve them only behind the proxy-level TLS and authentication of your web server guide, restrict by source IP where the proxy supports it, and keep them updated; both are perennial exploit targets. pgAdmin in server mode has its own login; treat its accounts per [authentication.md](authentication.md).

## RedisInsight and similar tools

Keep them on loopback or a private network and reach them through the tunnels above. When in doubt, apply the generic pattern: loopback bind, TLS proxy, proxy or SSO authentication, MFA.

## Verify

```bash
ss -tlnp                                      # panels bound to 127.0.0.1 only
curl -sI https://panel.example.com/           # 401/403 or a login redirect, never a dashboard
```

Test each panel's URL from outside your network; a dashboard that renders without a login is a finding.

## Sources (checked September 2026)

- mongo-express README (defaults and variables): https://github.com/mongo-express/mongo-express
- Grafana configuration and HTTPS: https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/ and https://grafana.com/docs/grafana/latest/setup-grafana/set-up-https/
- Prometheus basic auth and TLS guides: https://prometheus.io/docs/guides/basic-auth/ and https://prometheus.io/docs/guides/tls-encryption/
- phpMyAdmin documentation: https://www.phpmyadmin.net/docs/ and pgAdmin documentation: https://www.pgadmin.org/docs/
