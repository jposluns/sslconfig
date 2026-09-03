# PaaS platforms: what the platform does, what stays yours

On Render, Fly.io, Railway, Vercel, Heroku, and similar platforms, TLS is not your problem: the platform terminates HTTPS and manages certificates, including for custom domains. Do not bolt certbot or a reverse proxy onto a PaaS app, and do not apply this repository's server-TLS guides there. What stays yours:

## 1. Authentication: entirely yours

The platform authenticates nobody. Every non-public endpoint still needs login or keys per [authentication.md](authentication.md), MFA where viable per [mfa.md](mfa.md). "It is on Vercel" changes nothing about an open `/api/admin`.

## 2. Secrets: use the platform's store

Each platform provides environment/secret configuration. Set secrets there; never commit `.env` files ([secrets.md](secrets.md)). Rotate anything that ever appeared in the repository, build logs, or client bundles. Public frontend frameworks compile some env vars into the client (for example `NEXT_PUBLIC_`-prefixed values); only put genuinely public values in those.

## 3. Enforce HTTPS and correct proxy awareness

- Redirect HTTP to HTTPS where the platform offers a toggle, or in the app (checking the platform's forwarded-protocol header).
- Behind the platform proxy, configure the framework accordingly (`trust proxy` in Express per [nodejs.md](nodejs.md), `SECURE_PROXY_SSL_HEADER` in Django per [python.md](python.md)) so secure cookies and redirects behave.
- Bind to the port the platform injects (commonly a `PORT` variable) and nothing else; do not open extra listeners.

## 4. Databases attached to PaaS apps

Managed databases from these platforms come with TLS endpoints; require verified TLS in the connection string per the database guides ([postgresql.md](postgresql.md), [mysql.md](mysql.md)) and keep the credentials in the platform's secret store. Databases you run yourself elsewhere follow their own guides plus [cloud-firewalls.md](cloud-firewalls.md).

## 5. Verify

```bash
curl -sI http://app.example.com/          # platform redirects to https
curl -s  https://app.example.com/api/...  # 401/403 without credentials
# Repository scan per secrets.md comes back clean; client bundle contains no private keys.
```

## Sources (checked September 2026)

- Render: https://render.com/docs ; Fly.io: https://fly.io/docs ; Vercel: https://vercel.com/docs (each documents managed TLS and environment configuration; consult your platform's pages for the exact toggles)
