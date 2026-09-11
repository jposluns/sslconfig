# Files a web server must never serve: dotfiles, .git, dumps, backups, and client secrets

Scanners request `/.env`, `/.git/config`, `/config.php.bak`, and `/db.sql` continuously, and any of these
under a web root hands over credentials or source regardless of what the application itself authenticates.
Anything a deploy step leaves inside the document root is served too, unless the server is told otherwise.

## nginx

Deny dotfiles by regex location, with the ACME challenge path carved out first, because `.well-known` also
starts with a dot:

```nginx
location ^~ /.well-known/acme-challenge/ {
    allow all;
}

location ~ /\. {
    deny all;
}
```

Once nginx picks the `^~` location as the longest matching prefix, it skips regex locations entirely, so the
challenge path is served before the dotfile deny is reached (`allow`/`deny`: `ngx_http_access_module`;
`location` order and `^~`: `ngx_http_core_module`).

## Apache

```apache
<DirectoryMatch "/\.(?!well-known)">
    Require all denied
</DirectoryMatch>

<FilesMatch "(^\.|\.sql$|\.dump$|\.bak$)">
    Require all denied
</FilesMatch>
```

`<FilesMatch>` matches the request's basename, not its full path, so it alone does not catch
`/.git/config`: the matched name is `config`, which does not start with a dot (per the core module
documentation). The `<DirectoryMatch>` rule above matches any dot-prefixed path segment (`.git`, `.svn`,
and similar), with a negative lookahead that carves out `.well-known` so the ACME challenge path still
resolves; keep the `<FilesMatch>` rule as a backstop for `.sql`, `.dump`, and `.bak` basenames and for
top-level dotfiles like `/.env`.

## Caddy

```caddyfile
respond /.git/* 404
respond /.env 404
respond /.env.* 404
```

If a broader matcher replaces this list, carve out `/.well-known/*` first: legitimate things live there
(ACME challenges, `security.txt`), and Caddy already serves its own ACME challenges outside the file server.

## Keep dumps and backups out of the served directory

`.sql`, `.dump`, and backup archives should never land inside a directory a web root points at; the deny rules above are a backstop, not the control. Write exports and backups outside the document root, or to object storage ([object-storage.md](object-storage.md)), never `/var/www/html`.

## Client bundles: secrets compiled into the browser

`NEXT_PUBLIC_`-prefixed variables in Next.js and `VITE_`-prefixed variables in Vite are inlined into the
browser JavaScript at build time; Create React App's `REACT_APP_` prefix does the same (Create React App is
deprecated as of this writing, but the convention persists in older projects). An LLM provider key pasted
into frontend code under one of these prefixes ships to every visitor's browser, not just your server. Only
genuinely public values belong behind these prefixes; call the provider from a backend route and keep the
key server-side. See [secrets.md](secrets.md) and [paas.md](paas.md) for the platform version of this. A
production source map (`.map` files, or an inline `//# sourceMappingURL` comment) reconstructs original
source too; do not ship one to a public origin for code not already meant to be public.

## Verify

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/.env
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/.git/config
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/config.php.bak
curl -s -o /dev/null -w '%{http_code}\n' https://example.com/db.sql
# each line above must print 403 or 404, never the file's content

grep -rn "sk-\|AKIA\|-----BEGIN" .next/static build dist 2>/dev/null
# must print nothing when run against the built client bundle, not the source;
# a variable that never compiled in cannot leak
```

Any backup path known to have existed on the server should also 404 at the deployed URL.

## Sources (checked September 2026)

- nginx core module (`location`, `^~` modifier, matching order): https://nginx.org/en/docs/http/ngx_http_core_module.html
- nginx access module (`allow`, `deny`): https://nginx.org/en/docs/http/ngx_http_access_module.html
- Apache mod_authz_core (`Require all denied`): https://httpd.apache.org/docs/2.4/mod/mod_authz_core.html
- Apache core module (`<FilesMatch>`, `<DirectoryMatch>`): https://httpd.apache.org/docs/2.4/mod/core.html#filesmatch, https://httpd.apache.org/docs/2.4/mod/core.html#directorymatch
- Caddy `respond` directive: https://caddyserver.com/docs/caddyfile/directives/respond
- Caddy matchers: https://caddyserver.com/docs/caddyfile/matchers
- Next.js environment variables (`NEXT_PUBLIC_`): https://nextjs.org/docs/pages/guides/environment-variables
- Vite env variables (`VITE_`): https://vite.dev/guide/env-and-mode
- Create React App environment variables (`REACT_APP_`, deprecation notice): https://create-react-app.dev/docs/adding-custom-environment-variables/
