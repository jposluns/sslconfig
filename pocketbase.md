# Self-hosted backends: PocketBase and Appwrite

Like Firebase and Supabase ([firebase-supabase.md](firebase-supabase.md)), these backends hand a
public API endpoint to your client code; the collection or resource rules you write are the only
gate between the internet and your data. Both also ship an admin console whose first user becomes
the operator account, so that bootstrap step has to happen before the instance is reachable by
anyone else.

## PocketBase

Create the superuser before opening access. The console command is
`./pocketbase superuser create EMAIL PASS`; the alternative is the web-based installer linked from
the server's own startup log. Do not leave a fresh instance open to the network while that account
is still unclaimed.

PocketBase has no native TLS listener beyond its own ACME integration: run
`./pocketbase serve yourdomain.com` and it issues and renews a Let's Encrypt certificate for that
domain automatically, or put it behind your own reverse proxy per [nginx.md](nginx.md) or
[caddy.md](caddy.md) and terminate TLS there instead.

PocketBase 0.38 and later can restrict superuser sessions by IP: set the allowed list under
Settings > Application > Superuser IPs, or from the console with
`./pocketbase superuser ips 127.0.0.1 10.0.0.0 --dir=/path/to/your/pb_data`. The same settings panel
can require an additional one-time code (email-delivered) when authenticating as a superuser. Both
are worth enabling for any instance reachable beyond your own machine.

None of that replaces the actual access control: every collection's API rules (`listRule`,
`viewRule`, `createRule`, `updateRule`, `deleteRule`) decide what non-superusers can do. A rule left
`null` is "locked", meaning only a superuser can perform that action; an empty string opens the
action to everyone, including unauthenticated guests. Superusers bypass API rules entirely, so
never hand a superuser account or token to a client application; use collection rules and scoped
auth for that.

## Appwrite (self-hosted)

Enforce HTTPS in production with `_APP_OPTIONS_FORCE_HTTPS`; Appwrite's own docs say to "always
prefer HTTPS over HTTP in production environments." Front it per [nginx.md](nginx.md) or
[caddy.md](caddy.md) and [fronting-auth.md](fronting-auth.md) if you are not terminating TLS at
Appwrite itself.

By default only the first user can register through the console; every account after that has to be
invited. Lock this down further with `_APP_CONSOLE_WHITELIST_ROOT` (only that first user can ever
self-register), `_APP_CONSOLE_WHITELIST_EMAILS`, or `_APP_CONSOLE_WHITELIST_IPS` to restrict who can
reach the console dashboard at all.

Project API keys are scoped rather than all-or-nothing; grant only the scopes a given key needs, and
treat any key with `keys.write` as equivalent to an admin credential, since it can change or delete
other keys' scopes. Keys are meant for server SDKs and CLI use, never for client-side code; store
them the way [secrets.md](secrets.md) describes, not in the repository or the client bundle.

## Verify

```bash
curl -sI https://backend.example.com/_/           # PocketBase admin UI: login page, not a dashboard
curl -sI https://backend.example.com/console       # Appwrite console: login page or 401, no open signup form
```

After bootstrap, confirm the console no longer offers public signup (only invitation), that a
collection or resource with no rule set denies every request from a non-admin client, and that the
key or token embedded in your client bundle is a scoped key, never a superuser token or an
admin/`keys.write` API key. Grep the client bundle for the string used by your admin credentials; it
should not appear.

## Sources (checked September 2026)

- PocketBase going to production: https://pocketbase.io/docs/going-to-production/
- PocketBase API rules and filters: https://pocketbase.io/docs/api-rules-and-filters/
- Appwrite self-hosting production security: https://appwrite.io/docs/advanced/self-hosting/production/security
- Appwrite project API keys: https://appwrite.io/docs/advanced/platform/api-keys
