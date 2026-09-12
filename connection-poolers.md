# Connection poolers: PgBouncer and pgpool-II

A connection pooler sits in front of PostgreSQL and becomes the thing clients actually connect to. Every control you configured on the database server ([postgresql.md](postgresql.md)) now applies to the pooler's connection, not to the client's, and the pooler's own defaults decide what happens on both hops. Two of those defaults fail open: PgBouncer disables client TLS entirely, and its server-side `prefer` mode silently drops to plain TCP when TLS is refused.

Default posture: bind the pooler to the interface the application uses and nothing wider, require TLS on the client hop, require a *verified* server certificate on the database hop, and leave the client's PostgreSQL role intact through the pooler.

## 1. What the pooler binds, and on which port

PgBouncer's bind default is the safe one and worth keeping: `listen_addr` is "not set" by default, and "when not set, only Unix socket connections are accepted". `listen_port` defaults to `6432`. Exposure is something you add.

```ini
; /etc/pgbouncer/pgbouncer.ini
[pgbouncer]
listen_addr = 10.0.0.5        ; the application-facing address; never * unless it is genuinely public
listen_port = 6432
unix_socket_dir = /var/run/postgresql
```

Pgpool-II binds `localhost` by default on `port` 9999, and runs a second listener for its control protocol on `pcp_port` 9898. Both are set at server start only.

```ini
# /etc/pgpool-II/pgpool.conf
listen_addresses = '10.0.0.5'   # default is 'localhost'
port = 9999
pcp_port = 9898                 # PCP administration; keep this off any public interface
```

PCP is an administration channel with its own credential file, so treat 9898 the way you would treat an admin UI rather than a database port, and keep it on loopback or a management address.

## 2. Client TLS is off by default, and the database server's TLS does not cover it

PgBouncer's own documentation is explicit: for `client_tls_sslmode`, "TLS connections are disabled by default." A database that requires `hostssl` for every remote client gains nothing from that requirement once a pooler is in front of it, because the only remote connection PostgreSQL sees is the pooler's. The clients are on a different, plaintext hop.

```ini
[pgbouncer]
client_tls_sslmode = require              ; default is disable
client_tls_key_file = /etc/pgbouncer/tls/pooler.key
client_tls_cert_file = /etc/pgbouncer/tls/pooler.crt
; client_tls_protocols defaults to `secure` (TLSv1.2 and TLSv1.3); leave it alone
```

To require client certificates as well, set `client_tls_sslmode = verify-full` and point `client_tls_ca_file` at the CA that issued them. Give the key file mode `600` and the `pgbouncer` user's ownership, as with any private key ([self-signed.md](self-signed.md), [free-certificates.md](free-certificates.md)).

Pgpool-II uses one switch for both hops: `ssl` is "off" by default, and setting it on "enables the SSL for both the frontend and backend communications". Its documentation notes that `ssl_key` and `ssl_cert` must also be configured for frontend connections to work.

```ini
ssl = on                        # default is off; covers frontend and backend
ssl_key = '/etc/pgpool-II/tls/pooler.key'
ssl_cert = '/etc/pgpool-II/tls/pooler.crt'
```

## 3. The database hop, where `prefer` fails open

`server_tls_sslmode` is the setting that decides what the pooler does on its way to PostgreSQL, and its default mode is `prefer`, which the documentation describes as: "TLS connection is always requested first from PostgreSQL. If refused, the connection will be established over plain TCP. Server certificate is not validated."

Two separate failures sit in that sentence. A server that stops offering TLS gets plain TCP instead of an error, and the certificate is not checked even when TLS succeeds. Raising the mode only fixes the first: `require` still says "Server certificate is not validated", and `verify-ca` still says "Server host name is not checked against certificate". Only `verify-full` requires both a valid certificate and a matching host name, which is what `sslmode=verify-full` bought you when the client spoke to PostgreSQL directly.

```ini
[pgbouncer]
server_tls_sslmode = verify-full          ; default is prefer
server_tls_ca_file = /etc/ssl/certs/postgres-ca.crt
```

Pgpool-II's `ssl_ca_cert` and `ssl_ca_cert_dir` are documented as CA files "which can be used to verify the backend server certificates". The documentation describes CA verification and does not document a host name check on the backend connection, so do not assume the two products' strictest modes are equivalent; where the host name match matters, PgBouncer's `verify-full` is the one that states it.

## 4. A forced `user=` collapses every client into one PostgreSQL role

In the `[databases]` section, the `user` key changes who the pooler is on the database server: "If `user=` is set, all connections to the destination database will be done with the specified user, meaning that there will be only one pool for this database. Otherwise, PgBouncer logs into the destination database with the client user name."

That single key undoes per-role access control. Every `GRANT` you wrote, every row-level policy keyed on `current_user`, and every per-user line in `pg_hba.conf` stops discriminating between clients, because there is only one role left. A forced user is a legitimate choice for a single-tenant service with one application account; it is a silent privilege merge anywhere else.

```ini
[databases]
; One pool per user, each client keeping its own role. Note the absent `user=`.
app = host=db.internal port=5432 dbname=app

; Compare: every client of this entry becomes `svc` on the server, whatever they
; authenticated as at the pooler.
; reports = host=db.internal port=5432 dbname=app user=svc
```

## 5. `pg_hba.conf` now matches the pooler, so the client rules move into the pooler

PgBouncer keeps its own pool of server connections and hands them out, so a server connection is not the client's connection and outlives it. The address that `pg_hba.conf` matches is the pooler's. A line such as `hostssl app app 10.0.0.0/24 scram-sha-256`, which used to restrict a range of clients, now restricts one host: the pooler. That is not a reason to loosen it. Narrow the database server's rules to the pooler's address alone, and put the client-facing restriction where the clients now arrive.

On the database server:

```
# TYPE     DATABASE  USER  ADDRESS        METHOD
hostssl    app       all   10.0.0.5/32    scram-sha-256    # the pooler, and only the pooler
```

At the pooler, `auth_type = hba` reads a `pg_hba`-style file so the same per-path distinctions apply to client connections. The documentation gives exactly this use: "This allows different authentication methods for different access paths, for example: connections over Unix socket use the peer authentication method, connections over TCP must use TLS."

```ini
[pgbouncer]
auth_type = hba
auth_hba_file = /etc/pgbouncer/pg_hba.conf
```

```
# /etc/pgbouncer/pg_hba.conf
local      all       all                  peer
hostssl    app       app   10.0.0.0/24    scram-sha-256
```

Because the server no longer sees the client, its logs no longer identify one either. `application_name_add_host` "adds the client host address and port to the application name setting set on connection start", and its default is `0`. Turn it on so a query traced in the database's own logs still names where it came from.

```ini
application_name_add_host = 1             ; default is 0
```

## 6. The admin console, and the authentication methods that are not authentication

PgBouncer reserves one database name for its control channel: "The database name 'pgbouncer' is reserved for the admin console and cannot be used as a key here." Access to it is governed by `admin_users` (full commands) and `stats_users` (read-only `SHOW` commands), both of which default to empty.

One `auth_type` value removes that gate entirely. For `admin_users`, the documentation says it is "Ignored when `auth_type` is `any`, in which case any user name is allowed in as admin." The other weak values are described just as plainly: `trust` is "No authentication is done", `any` is "Like the trust method, but the user name given is ignored", and `plain` sends "The clear-text password ... over the wire" and is marked deprecated. The default is `md5`.

```ini
[pgbouncer]
auth_type = scram-sha-256                 ; or hba, per section 5; never any, trust or plain
auth_file = /etc/pgbouncer/userlist.txt
admin_users = pgbadmin
stats_users = pgbmetrics
```

`auth_file` "may contain both MD5-encrypted and plain-text passwords", so it is a secret file regardless of what you put in it: mode `600`, owned by the pooler's user, and out of the repository ([secrets.md](secrets.md)). `auth_query` avoids the file for user passwords by reading them from the database, and the documentation warns that "Direct access to `pg_authid` requires admin rights. It's preferable to use a non-superuser that calls a SECURITY DEFINER function instead."

## 7. Verify

```bash
ss -tlnp | grep -E '6432|9999|9898'          # the pooler's binds, and pgpool's PCP port

# The client hop must refuse plaintext. This command has to FAIL.
psql "host=pooler.internal port=6432 dbname=app user=app sslmode=disable" -c 'SELECT 1;'

# The client hop must verify the pooler. This command has to SUCCEED.
psql "host=pooler.internal port=6432 dbname=app user=app sslmode=verify-full \
      sslrootcert=/etc/ssl/certs/ca.crt" -c 'SELECT current_user, ssl FROM pg_stat_ssl \
      JOIN pg_stat_activity USING (pid) WHERE pid = pg_backend_pid();'
```

The last query answers two questions at once. `current_user` must be the role the client authenticated as, not a shared service account, which is section 4; `ssl` reports the *database* hop as PostgreSQL sees it, which is section 3.

Ask the pooler what it actually negotiated, rather than what it was configured to prefer:

```bash
psql "host=/var/run/postgresql port=6432 dbname=pgbouncer user=pgbadmin" \
  -c 'SHOW SERVERS;' -c 'SHOW CLIENTS;' -c 'SHOW POOLS;'
```

The `tls` column is "A string with TLS connection information, or empty if not using TLS", on both `SHOW SERVERS` and `SHOW CLIENTS`. An empty `tls` on a server row is a plaintext database hop, whatever `server_tls_sslmode` says, and that is the `prefer` fallback in section 3 caught in the act. In `SHOW POOLS`, "A new pool entry is made for each couple of (database, user)": a database with many client roles but a single pool row is a forced `user=`.

Finally, the console must reject a user who is on neither list:

```bash
psql "host=/var/run/postgresql port=6432 dbname=pgbouncer user=app" -c 'SHOW FDS;'
```

That has to fail. If it succeeds, check `auth_type` for `any` before anything else.

## Common mistakes

- Configuring TLS carefully on PostgreSQL, then putting a pooler in front of it with `client_tls_sslmode` left at its default, so every client connection is plaintext and the database's `hostssl` rules only ever match the pooler.
- Leaving `server_tls_sslmode` at `prefer` and reading a successful connection as an encrypted one. It falls back to plain TCP without an error, and it does not validate the certificate in any case.
- Treating `require` or `verify-ca` as equivalent to the client-side `sslmode=verify-full` they replaced. Neither checks the host name.
- Widening the database server's `pg_hba.conf` because the old client ranges stopped matching. The pooler is the only client now; narrow the rule to its address and move the client rules into `auth_hba_file`.
- Setting `user=` on a `[databases]` entry for convenience, which merges every client into one role and disables per-role privileges on the server.
- Exposing pgpool-II's PCP port (9898) on the same interface as the database port because both are in the same configuration file.

## Sources (checked September 2026)

- PgBouncer configuration (`listen_addr`, `listen_port`, `client_tls_sslmode`, `server_tls_sslmode`, `auth_type`, `auth_file`, `auth_query`, `admin_users`, `stats_users`, `application_name_add_host`, the `[databases]` `user` key): https://www.pgbouncer.org/config.html
- PgBouncer usage, the admin console and its `SHOW` commands (`tls` column, `SHOW POOLS` per (database, user)): https://www.pgbouncer.org/usage.html
- PgBouncer features and pooling modes: https://www.pgbouncer.org/features.html
- Pgpool-II connection settings (`listen_addresses`, `port`, `pcp_port`): https://www.pgpool.net/docs/latest/en/html/runtime-config-connection.html
- Pgpool-II SSL settings (`ssl`, `ssl_cert`, `ssl_key`, `ssl_ca_cert`, `ssl_ca_cert_dir`): https://www.pgpool.net/docs/latest/en/html/runtime-ssl.html
- PostgreSQL pg_hba.conf: https://www.postgresql.org/docs/current/auth-pg-hba-conf.html
