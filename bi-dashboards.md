# BI dashboards: Metabase, Superset, Redash

These tools hold live connections to your production databases and cache query results in their own
storage. An exposed instance, or one still running default or example credentials, leaks both the
dashboards themselves and the databases behind them. One rule dominates everything tool-specific
below, the same as [admin-uis.md](admin-uis.md): **never public.** Reach it over SSH port
forwarding, a tailnet ([tailscale.md](tailscale.md)), or Cloudflare Access ([cloudflare.md](cloudflare.md)),
with MFA enforced at that fronting layer ([mfa.md](mfa.md)), and connect it to the database with a
least-privilege, read-only account wherever the dashboards do not need to write back.

## Metabase

The first account created during setup becomes the admin account, so an instance reachable on the
network before you finish the setup wizard lets whoever gets there first claim admin. Complete
setup before the instance is reachable from anywhere but you.

Public links and public embeds are enabled by default and let admins share a question, dashboard,
or document with anyone holding the URL; visitors get view-only results with no login. Metabase's
own docs warn that the public link URL is recoverable from a public embed, so an embed is not a
stronger boundary than a plain public link. Row and column security (per-user sandboxing of the
underlying data) is a Pro/Enterprise feature, not available on the open-source edition, so on the
free tier a public link or a shared question exposes whatever rows and columns the question already
queries. Disable public sharing in Admin Settings unless you specifically need it, and treat every
public link as a permanent, unauthenticated data release.

## Apache Superset

Superset ships a `SECRET_KEY` that signs session cookies; its own docs call it "very important to
keep the `SECRET_KEY` secret and set to a secure unique complex random value." Set it, and change
the admin password created at first run, before the instance is reachable by anyone else. Anonymous
visitors are assigned the Public role only when `AUTH_ROLE_PUBLIC` is configured; leave it unset
unless you intend anonymous dashboard access, and if you do, scope that role's permissions with
`PUBLIC_ROLE_LIKE` rather than granting it broadly. Superset's own `docker-compose.yml` states
plainly that the stack is not supported for production and that a real deployment needs its own
environment file with unique passwords and `SECRET_KEY`; do not run the example or dev compose file
against a production database.

## Redash

Setup creates the admin account on first run: "it will ask you to create your admin account. Once
this is done, you can start using Redash." Redash's own setup guidance calls out HTTPS as something
you add, not something it does for you: "If this is a production setup, you should enforce HTTPS."
Front it the same as the other tools here rather than relying on anything Redash provides natively.

## Verify

```bash
ss -tlnp | grep -E ':3000|:8088|:5000'   # Metabase / Superset / Redash bound to loopback only, ports vary by install
curl -sI https://bi.example.com/         # 401/403 or a login redirect, never a dashboard
```

Confirm from outside your network that each tool's URL never renders a dashboard without a login,
that no default admin/admin or example credentials still work, and that the database role each tool
connects with is read-only where the dashboards do not need write access; check the connection
string or data source config, not just the tool's own login.

## Sources (checked September 2026)

- Metabase documentation home: https://www.metabase.com/docs/latest/
- Metabase setting up Metabase (first account is admin): https://www.metabase.com/docs/latest/configuring-metabase/setting-up-metabase
- Metabase public links and embeds: https://www.metabase.com/docs/latest/embedding/public-links
- Metabase data permissions (row and column security is Pro/Enterprise): https://www.metabase.com/docs/latest/permissions/data
- Superset security: https://superset.apache.org/admin-docs/security/
- Superset docker-compose.yml (production warning): https://github.com/apache/superset/blob/master/docker-compose.yml
- Redash help center: https://redash.io/help/
- Redash setting up a Redash instance: https://redash.io/help/open-source/setup/
