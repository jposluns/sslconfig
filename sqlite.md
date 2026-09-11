# SQLite in deployment: the file is the exposure (plus Turso and Litestream)

SQLite has no server process, no network listener, and no built-in authentication: its documented security model rests entirely on the filesystem, warning that "any database file which might have ever been writable by an agent in a different security domain should be treated as suspect." In deployment this means the exposure is never SQLite itself, it is wherever the `.db` file ends up: under a web root, inside a git repository, world-readable, or replicated to a public bucket.

## 1. Keep the file out of anything that serves it

A `.db` or `.sqlite` file inside a directory a web server or static host points at is downloadable by URL like any other file under the web root; treat it with the same deny rules as backups and dumps ([web-exposure.md](web-exposure.md)). Keep the database path outside the document root entirely, for example `/var/lib/myapp/app.db`, never `public/app.db` or `static/app.db`.

## 2. Keep the file out of git

A committed `.db` file ships every row to anyone who clones the repository, permanently, even after a later commit deletes it. Add `*.db`, `*.sqlite`, `*.sqlite3`, and the WAL/SHM sidecar files (`*.db-wal`, `*.db-shm`) to `.gitignore` before the first commit, and scan for a copy that already leaked per [secrets.md](secrets.md).

## 3. File permissions

Restrict the database file and its containing directory to the app's own user (for example `chmod 600` on the file, `chmod 700` on the directory); any other local account or process on the host can otherwise open the file directly and read or write it, since there is no SQLite-side access control to stop it.

## 4. libSQL and Turso: the file becomes an HTTP endpoint

Turso serves libSQL databases over HTTP, replacing the local file with a network service authenticated by a bearer token against a URL of the form `https://[databaseName]-[organizationSlug].turso.io`. Applications read `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` from the environment; the token is a secret exactly like an API key, never in the client bundle, never committed ([secrets.md](secrets.md)).

```bash
turso db tokens create example-db --read-only --expiration 7d
```

`turso db tokens create` supports `-r`/`--read-only` to scope a token away from writes, and `-e`/`--expiration` to give it a lifetime (`never`, or a duration such as `7d3h`); issue a scoped, expiring token for anything that does not need full write access rather than reusing one long-lived full-access token everywhere.

## 5. Litestream and LiteFS: the replica destination is now part of the exposure

Litestream continuously replicates the SQLite file to S3, Google Cloud Storage, Azure Blob Storage, and other supported destinations, authenticating to S3 the same way any AWS client does, with `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in the environment. Litestream's own S3 guide scopes the IAM policy to the one bucket and prefix it needs rather than granting broad S3 access, which limits the damage if the credential leaks. The replica bucket needs the same private-by-default posture as any other bucket: see [object-storage.md](object-storage.md) for keeping it non-public and restoring through scoped credentials rather than a public URL.

LiteFS replicates a SQLite file across a cluster's nodes rather than to object storage directly; its docs note the project is pre-1.0 and recommend regular off-site backups as a separate measure, and that backup destination should get the same bucket-privacy treatment as a Litestream replica.

## Verify

```bash
curl -sI https://app.example.com/app.db      # 404, never 200
git check-ignore -v app.db                    # prints a matching .gitignore rule
stat -c '%a %U' /var/lib/myapp/app.db         # 600, owned by the app user, not world-readable
grep -rn "REPLACE_WITH_ACTUAL_TOKEN_VALUE" build dist .next/static; echo "exit: $?"                             # search for the literal token value copied from the secret store, not the env-var name a bundler already inlined away; exit 1 is the goal
grep -rnE "eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}" build dist .next/static; echo "exit: $?"                  # a JWT-shaped token (Turso/libSQL tokens are JWTs) is a finding wherever it turns up; exit 2 means a path did not exist, not a clean result
```

A clean result here is evidence, not proof: it means neither pattern matched in the paths searched, not that the token cannot be present in some other form. A bundler could split, encode, or otherwise transform it, and a missing or misspelled directory can produce the same silence as a genuinely clean scan, so check the exit code and confirm the directories exist, not just the absence of output.

## Sources (checked September 2026)

- SQLite security: https://www.sqlite.org/security.html
- Turso HTTP API quickstart (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`): https://docs.turso.tech/sdk/http/quickstart
- Turso CLI `db tokens create` (`--read-only`, `--expiration`): https://docs.turso.tech/cli/db/tokens/create
- Litestream guides (supported replica destinations): https://litestream.io/guides/
- Litestream S3 guide (credentials, scoped IAM policy): https://litestream.io/guides/s3/
- LiteFS overview (cluster replication, pre-1.0 status, backup recommendation): https://fly.io/docs/litefs/
