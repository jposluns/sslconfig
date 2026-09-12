# Connection poolers: PgBouncer and pgpool-II

A connection pooler sits in front of PostgreSQL and becomes the thing clients actually connect to. The pooler opens its own connections to the database and reuses them, so every control you configured on the database server ([postgresql.md](postgresql.md)) now governs the pooler's connection rather than the client's, and the pooler's own defaults decide what happens on both hops. Two of those defaults fail open: PgBouncer disables client TLS entirely, and its server-side `prefer` mode drops to plain TCP without an error when TLS is refused.

Default posture: bind the pooler to the interface the application uses and nothing wider, require TLS on the client hop, require a verified server certificate on the database hop, and leave the client's PostgreSQL role intact through the pooler.

Run a current PgBouncer. 1.25.2 fixes four advisories, and they need different things of an attacker. CVE-2026-6664 is the one an unauthenticated remote client can reach on its own: an integer overflow in packet parsing that crashes the process from a malformed SCRAM packet. CVE-2026-6665 needs a malicious PostgreSQL server, and CVE-2026-6666 a server that returns an error response with no SQLSTATE, so both are about what the pooler trusts on the database side rather than the client side. CVE-2026-6667 needs console access, which the vendor notes "itself requires authorization", and it let any console user run `KILL_CLIENT`. That last one matters to section 6 below, which treats `stats_users` as read-only; on an older build it is not.

## 1. What the pooler binds, and on which port

A comment in `pgbouncer.ini` must start its own line. The vendor is explicit: "The characters “;” and “#” are not recognized as special when they appear later in the line." A trailing comment therefore becomes part of the value and the setting is not what it looks like.

```ini
; /etc/pgbouncer/pgbouncer.ini
[pgbouncer]
; The application-facing address. Never * unless this is genuinely public.
; Unset is the default, and it means Unix socket connections only.
listen_addr = 10.0.0.5
listen_port = 6432
unix_socket_dir = /var/run/postgresql
```

Pgpool-II binds `localhost` by default on `port` 9999, and runs a separate control listener whose address is its own setting. Widening `listen_addresses` does not move PCP, and narrowing `listen_addresses` does not confine it either: `pcp_listen_addresses` is independent and also defaults to `localhost`. Both are set at server start only.

```ini
# /etc/pgpool-II/pgpool.conf
listen_addresses = '10.0.0.5'      # default is 'localhost'
port = 9999
pcp_listen_addresses = 'localhost' # independent of the line above; keep it here
pcp_port = 9898
```

PCP is an administration channel with its own credential file, `pcp.conf`, so treat 9898 the way you would treat an admin UI rather than a database port.

## 2. Client TLS is off by default, and the database server's TLS does not cover it

PgBouncer's documentation is explicit: for `client_tls_sslmode`, "TLS connections are disabled by default." A database that requires `hostssl` for every remote client gains nothing from that requirement once a pooler is in front of it, because the only remote connection PostgreSQL sees is the pooler's. The clients are on a different, plaintext hop.

```ini
[pgbouncer]
; The default is disable. Over TCP, `require` makes PgBouncer refuse a client
; that will not negotiate TLS; connections over the Unix socket are exempt.
client_tls_sslmode = require
client_tls_key_file = /etc/pgbouncer/tls/pooler.key
client_tls_cert_file = /etc/pgbouncer/tls/pooler.crt
; client_tls_protocols defaults to `secure`, which is TLSv1.2 and TLSv1.3. Leave it.
```

To require client certificates as well, set `client_tls_sslmode = verify-full` and point `client_tls_ca_file` at the CA that issued them. Give the key file mode `600` and the pooler user's ownership, as with any private key ([self-signed.md](self-signed.md), [free-certificates.md](free-certificates.md)).

Pgpool-II uses one switch for both hops: `ssl` is "off" by default, and setting it on "enables the SSL for both the frontend and backend communications". Its documentation notes that `ssl_key` and `ssl_cert` must also be configured for frontend connections to work.

Turning it on makes TLS available and does not require it. A client that declines TLS still connects, because a `pool_hba.conf` `host` record "match[es] either SSL or non-SSL connection attempts". Requiring it means `hostssl` records, and those have their own trap in the other direction: "SSL must be enabled by setting the `ssl` configuration parameter. Otherwise, the `hostssl` record is ignored." A rule you wrote to require TLS is then simply not the rule being applied, and whichever other record matches decides instead. Section 5 has the file.

```ini
ssl = on                        # default is off; covers frontend and backend
ssl_key = '/etc/pgpool-II/tls/pooler.key'
ssl_cert = '/etc/pgpool-II/tls/pooler.crt'
```

## 3. The database hop, where `prefer` fails open

`server_tls_sslmode` decides what the pooler does on its way to PostgreSQL, and its default mode is `prefer`, which the documentation describes as: "TLS connection is always requested first from PostgreSQL. If refused, the connection will be established over plain TCP. Server certificate is not validated."

Two separate failures sit in that sentence. A server that stops offering TLS gets plain TCP instead of an error, and the certificate is not checked even when TLS succeeds. Raising the mode only fixes the first: `require` still says "Server certificate is not validated", and `verify-ca` still says "Server host name is not checked against certificate". Only `verify-full` requires both a valid certificate and a matching host name, which is what `sslmode=verify-full` bought you when the client spoke to PostgreSQL directly.

```ini
[pgbouncer]
; The default is prefer, which falls back to plain TCP and validates nothing.
; require and verify-ca each leave one half of that open.
server_tls_sslmode = verify-full
server_tls_ca_file = /etc/ssl/certs/postgres-ca.crt
```

Pgpool-II's `ssl_ca_cert` and `ssl_ca_cert_dir` are documented as CA files "which can be used to verify the backend server certificates", and with neither set there is nothing to verify against, so set one:

```ini
ssl_ca_cert = '/etc/ssl/certs/postgres-ca.crt'
```

The documentation describes CA verification and does not document a host name check on the backend connection, so do not assume the two products' strictest modes are equivalent: where a host name match matters, PgBouncer's `verify-full` is the one that states it.

One more thing is not established for pgpool-II, and this guide will not claim it. A CA file decides what happens when TLS is negotiated; it does not decide what happens when the backend declines TLS altogether. pgpool-II documents no setting equivalent to PgBouncer's `server_tls_sslmode = require`, and the upstream implementation of the backend handshake, read on `master` rather than on a release tag, continues without SSL when the server answers that it will not do it. So treat the backend hop here the way section 3 treats `prefer`: test it rather than assume it, by refusing TLS at the PostgreSQL end and confirming pgpool-II fails instead of connecting. If it connects, the encryption on that hop is the server's choice rather than yours.

## 4. A forced `user=` collapses every client into one PostgreSQL role

In the `[databases]` section, the `user` key changes who the pooler is on the database server: "If `user=` is set, all connections to the destination database will be done with the specified user, meaning that there will be only one pool for this database. Otherwise, PgBouncer logs into the destination database with the client user name, meaning that there will be one pool per user."

That single key undoes per-role access control. Every `GRANT` you wrote, every row-level policy keyed on `current_user`, and every per-user line in `pg_hba.conf` stops discriminating between clients, because there is only one role left. A forced user is a legitimate choice for a single-tenant service with one application account; it is a silent privilege merge anywhere else.

```ini
[databases]
; One pool per user, each client keeping its own role. Note the absent user=.
app = host=db.internal port=5432 dbname=app

; Compare. Every client of this entry becomes svc on the server, whatever they
; authenticated as at the pooler:
;   reports = host=db.internal port=5432 dbname=app user=svc
```

`SHOW DATABASES` reports this directly in its `force_user` column, which is what section 7 checks rather than counting pools.

## 5. `pg_hba.conf` now matches the pooler, so the client rules move into the pooler

PgBouncer opens its own server connections and reuses them across clients, so a server connection is not the client's connection and outlives it. PostgreSQL matches an address-based `pg_hba.conf` record against "the client machine address(es) that this record matches", and the address it sees is the source address of the pooler's backend connection, after any NAT on the way. That need not equal the pooler's listening address, so read it from the database rather than assuming it:

```sql
SELECT inet_client_addr();   -- run through the pooler, on the database server
```

Over a Unix socket the function returns NULL and the `local` rules apply instead.

A line such as `hostssl app app 10.0.0.0/24 scram-sha-256`, which used to restrict a range of clients, now matches whatever the pooler's backend connections come from. Narrowing it to that address is right, and it is worth being exact about what it buys: an address is not an identity. A `/24` still admits its whole range, and even a `/32` can be several workloads sharing one NAT egress, so the rule says where a connection came from and never which process opened it. Installing a pooler also does not stop anything else in the old range connecting directly. Narrow the database server's rules to the address you actually read, put the client-facing restriction where the clients now arrive, and treat the two as separate jobs rather than one moved.

On the database server:

```
# TYPE     DATABASE  USER  ADDRESS        METHOD
hostssl    app       all   10.0.0.5/32    scram-sha-256    # the address the pooler's backend connections come from
```

At the pooler, `auth_type = hba` reads a `pg_hba`-style file so the same per-path distinctions apply to client connections. The documentation gives exactly this use: "This allows different authentication methods for different access paths, for example: connections over Unix socket use the peer authentication method, connections over TCP must use TLS."

```ini
[pgbouncer]
auth_type = hba
auth_hba_file = /etc/pgbouncer/pg_hba.conf
auth_file = /etc/pgbouncer/userlist.txt
```

```
# /etc/pgbouncer/pg_hba.conf
local      all       all                  peer
hostssl    app       app   10.0.0.0/24    scram-sha-256
```

Pgpool-II has the same file and does not read it by default: `enable_pool_hba` is documented as "Default is false", and with it off "the client authentication method is completely managed by PostgreSQL". That does not merge your clients into one role the way a forced `user=` does, because pgpool-II pools per user and database and the backend still authenticates each one. What it means is narrower and still worth fixing: pgpool-II applies no client-facing policy of its own, so it will not refuse a plaintext connection or a client from an address you never meant to serve.

```ini
enable_pool_hba = on            # default is false
pool_passwd = 'pool_passwd'     # a path, relative to the directory holding this file
```

Setting that path does not create the entries. For `scram-sha-256` the vendor's steps are to "Create pool_passwd file entry for database user and password in plain text or AES encrypted format", where `pg_enc` writes the AES form, and it warns that "User name and password must be identical to those registered in the PostgreSQL server". An `md5`-format entry cannot serve SCRAM. AES also needs an OpenSSL-enabled build and a decryption key the service can read, normally `.pgpoolkey`. Reload after changing either side.

```
# /etc/pgpool-II/pool_hba.conf
# `host` matches SSL and non-SSL alike, so requiring TLS means hostssl rather than host.
# The two reject lines are not redundant with the default: an unmatched connection is denied
# anyway, but a later permissive rule would match first, and these stop that silently.
local      all       all                        scram-sha-256
hostssl    all       app   10.0.0.0/24          scram-sha-256
hostnossl  all       all   0.0.0.0/0            reject
hostnossl  all       all   ::/0                 reject
```

Three things about that file are easy to get wrong. `local ... trust` is the tempting first line and it is a hole: the vendor says `trust` admits a client under "whatever database user name they specify", and the Unix socket lives in `unix_socket_directories`, which defaults to `/tmp`, so any local account can claim any database identity. Authenticate the local path too, or move the socket somewhere only the application user can reach. The setting is `unix_socket_directories`, which takes a comma-separated list, so restricting it means covering every directory in that list rather than one. The `0.0.0.0/0` rejection covers IPv4 only, which is why the second one is there. And records are read in order, so a permissive rule above these wins; the rejections protect against what comes after them, not before.

A `hostssl` record is ignored entirely while `ssl` is off. That does not by itself open the plaintext path, because "if no record matches, access is denied"; what it means is that the rule you wrote to require TLS is not the rule being applied, so whichever other record does match is deciding instead. Set `ssl = on` first and confirm it took effect.

Because the server no longer sees the client, its logs no longer identify one either. `application_name_add_host` adds "the client host address and port to the application name setting set on connection start", and its default is `0`. It is diagnostic metadata rather than an audit trail: the same page says the value applies "only at the start of a connection" and that after a later `SET application_name` "PgBouncer does not change it again", so a client can overwrite it. PostgreSQL's `log_line_prefix` defaults to `'%m [%p] '`, which carries no application name at all, so turning the setting on changes nothing in the log until `%a` is in the prefix.

```ini
; The default is 0.
application_name_add_host = 1
```

```
# postgresql.conf, on the database server
log_line_prefix = '%m [%p] %a '
```

## 6. The admin console, and the authentication methods that are not authentication

PgBouncer reserves one database name for its control channel: "The database name 'pgbouncer' is reserved for the admin console and cannot be used as a key here." Access is governed by `admin_users` for full commands and `stats_users` for read-only `SHOW` commands, both of which default to empty.

`auth_type = any` removes that gate, and the vendor's two pages disagree about how far. The configuration page says `admin_users` is "Ignored when `auth_type` is `any`, in which case any user name is allowed in as admin". The usage page says "Only users listed in the configuration parameters `admin_users` or `stats_users` are allowed to log in to the console. (Except when `auth_type=any`, then any user is allowed in as a `stats_user`.)" The released 1.25.2 source agrees with the usage page: admin status is granted to names matching `admin_users`, and an `any` connection that matches neither list is admitted without it. Either way `any` is unsafe, because an unauthenticated stranger gets console read access and can also simply claim a listed administrator's name, and this guide states the disagreement rather than picking the reading that suits it. The practical consequence matters for section 7: under `any`, a command with no administrator gate of its own, such as `SHOW VERSION`, SUCCEEDS for a user on neither list. A probe that expects a rejection has to tell one at login from one at the command, because only the first means the console is closed.

The other weak values are described plainly by the vendor: `trust` is "No authentication is done", `any` is "Like the trust method, but the user name given is ignored", and `plain` sends "The clear-text password ... over the wire" and is marked deprecated. The default is `md5`.

Keep `auth_type = hba` from section 5. Setting `auth_type = scram-sha-256` here instead would be a downgrade rather than an upgrade, because `auth_hba_file` is only consulted under `hba`, so the client-range restriction you wrote in section 5 would stop applying. Put the method in the HBA file:

```
# /etc/pgbouncer/pg_hba.conf
hostssl    pgbouncer  pgbadmin    10.0.0.0/24   scram-sha-256
hostssl    app        app         10.0.0.0/24   scram-sha-256
local      all        all                       peer
```

```ini
[pgbouncer]
admin_users = pgbadmin
stats_users = pgbmetrics
```

One account bypasses all of this by design, and it is worth knowing about: the documentation states that "the user name `pgbouncer` is allowed to log in without password, if the login comes via the Unix socket and the client has same Unix user UID as the running process". Anyone who can run a process as the pooler's Unix user already has the console.

The `local ... peer` line above has the same shape and the same requirement. `peer` takes the identity from the operating system, so `user=pgbadmin` in a connection string does not supply it: the command has to run as an OS user that maps to `pgbadmin`, or it is rejected whatever password it carries.

`auth_file` "may contain both MD5-encrypted and plain-text passwords", so it is a secret file regardless of what you put in it: mode `600`, owned by the pooler's user, and out of the repository ([secrets.md](secrets.md)). Choosing `scram-sha-256` in the HBA file constrains what has to be in there: the documented format is `"username" "password"` where the second field is "either a plain-text, a MD5-hashed password, or a SCRAM secret", and a SCRAM secret is `SCRAM-SHA-256$<iterations>:<salt>$<storedkey>:<serverkey>`. Copying a stored secret across means copying it exactly, salt and iteration count included, or the two sides do not agree. `auth_query` avoids the file for user passwords by reading them from the database, and the documentation warns that "Direct access to `pg_authid` requires admin rights. It's preferable to use a non-superuser that calls a SECURITY DEFINER function instead."

## 7. Verify

```bash
ss -tlnp | grep -E '6432|9999|9898'
```

Read that as an inventory rather than a pass. Every address printed is one the pooler answers on, so an entry showing `0.0.0.0:9898` or `[::]:9898` is section 1 not applied, whatever `listen_addresses` says.

The client hop takes three commands, not one. A single failing connection proves nothing, because a wrong password fails the same way as a refused plaintext connection; and a passing pair proves less than it looks, because a `trust` method in the HBA file lets any password through. Put the real password in `~/.pgpass` at mode `600` rather than the environment, which PostgreSQL says is "not recommended for security reasons" because some systems expose a process's environment to other users.

```bash
# ~/.pgpass, mode 600: hostname:port:database:username:password
# pooler.internal:6432:app:app:REPLACE_WITH_THE_APP_PASSWORD

TLS="sslmode=verify-full sslrootcert=/etc/ssl/certs/ca.crt"

# 1. Must FAIL, and the error must name TLS rather than authentication.
psql -X "host=pooler.internal port=6432 dbname=app user=app sslmode=disable" -c 'SELECT 1;'

# 2. Must SUCCEED. The control: the credential is good, so the failure above was
#    the TLS requirement and not a bad password.
psql -X "host=pooler.internal port=6432 dbname=app user=app $TLS" -c 'SELECT 1;'

# 3. Must FAIL on authentication. Without this, a `trust` method in auth_hba_file
#    passes both commands above while checking no password at all.
PGPASSWORD=definitely-not-the-password psql -X "host=pooler.internal port=6432 dbname=app user=app $TLS" -c 'SELECT 1;'
```

Run the same three against pgpool-II on port 9999 where that is the pooler in front, because nothing above tests its listener.

Three commands from one address prove one path. They say nothing about a second `hostssl` line further down the file that ends in `trust`, and nothing at all if `auth_type` is not `hba`, because `auth_hba_file` is then never read and the client-range restriction you wrote is inert while still sitting in the repository looking applied. So read the effective configuration as well as probing it:

```bash
psql -X "host=/var/run/postgresql port=6432 dbname=pgbouncer user=pgbadmin" \
  -c 'RELOAD;' -c 'SHOW CONFIG;' | grep -E 'auth_type|auth_hba_file|client_tls_sslmode|server_tls_sslmode'
grep -vE '^\s*(#|$)' /etc/pgbouncer/pg_hba.conf
```

`auth_type` must read `hba` for the file below it to matter. Read the rules in order: the first match wins, so a `trust` line decides for every path that reaches it before something stricter does, while one sitting below a rejection that already covers the same path is unreachable. Judge each line by what reaches it, not by its presence.

The `RELOAD` is not decoration. `SHOW CONFIG` reports the running settings and the file read reports the disk, and those are two different things: PgBouncer evaluates the HBA rules it parsed at load, so an edited file that has not been reloaded leaves the old rules deciding while the clean file sits on disk looking correct. A probe run against that state passes and certifies nothing. Reload first, or treat the file read as evidence about the next restart rather than about now.

For the database hop, know what the probe can and cannot tell you:

```bash
psql -X "host=pooler.internal port=6432 dbname=app user=app sslmode=verify-full sslrootcert=/etc/ssl/certs/ca.crt" -c "SELECT current_user, inet_client_addr(), ssl FROM pg_stat_ssl JOIN pg_stat_activity USING (pid) WHERE pid = pg_backend_pid();"
```

`ssl` reports whether the pooler-to-PostgreSQL connection uses SSL. It does not report whether the pooler validated the certificate, so a `t` here is consistent with `server_tls_sslmode = require`, which validates nothing. Certificate validation cannot be observed from the client at all: the only test is to present the pooler with a certificate that should fail, one signed by an untrusted CA and one valid but issued for a different host name, and confirm that it refuses both. It has to be a fresh BACKEND connection rather than a fresh client one: a new client is routinely handed a server connection that was opened earlier, under the old certificate. `inet_client_addr()` is the address section 5 tells you to write into `pg_hba.conf`.

Ask the pooler what it negotiated, and what identity it forces:

```bash
psql -X "host=/var/run/postgresql port=6432 dbname=pgbouncer user=pgbadmin" -c 'SHOW SERVERS;' -c 'SHOW DATABASES;'
```

The `tls` column is "A string with TLS connection information, or empty if not using TLS". An empty `tls` on a server row is a plaintext database hop happening right now, which is section 3 caught in the act; it does not by itself distinguish the `prefer` fallback from TLS being disabled outright or from a Unix-socket backend. A non-empty one is weaker still: it says this connection negotiated TLS, not that a plaintext one would have been refused. These are snapshots of established connections, and enforcement is what the configuration file says.

`SHOW DATABASES` answers section 4 directly through its `force_user` column, which names the forced identity where one is set. That is a better test than counting pools, because a pool count only reflects which users have happened to connect.

Finally, the console must reject a user on neither list, and it must reject it at login:

```bash
psql -X "host=pooler.internal port=6432 dbname=pgbouncer user=app $TLS" -c 'SHOW VERSION;'
```

That has to fail while connecting, with `not allowed`. `SHOW VERSION` is chosen because it has no administrator gate of its own, so it cannot fail for the wrong reason: if the connection is accepted, the command succeeds and prints a version, which is exactly what `auth_type = any` produces. Read the outcome in three ways rather than two. A refusal at login is the pass. A version printed is a failure, and `auth_type` is the first thing to check. Anything else, a DNS failure, a TLS failure, a refused connection, is inconclusive and has to be resolved before the probe means anything.

None of this tests the privileged name, and testing an unlisted one only proves the list is consulted. `admin_users` is an allowlist of names and says nothing about whether those names have to prove anything, so run the pair against the console itself rather than reusing the application query:

```bash
psql -X "host=pooler.internal port=6432 dbname=pgbouncer user=pgbadmin $TLS" -c 'SHOW VERSION;'
PGPASSWORD=definitely-not-the-password psql -X "host=pooler.internal port=6432 dbname=pgbouncer user=pgbadmin $TLS" -c 'SHOW VERSION;'
```

The first must succeed and the second must be refused at login. Both have to name `dbname=pgbouncer`: changing only the user name on the application probe leaves it asking the `app` database for `SELECT 1`, which tests nothing about the console.

The console commands over the Unix socket are a different path with a different requirement, and `peer` there takes the identity from the operating system.

MFA: neither pooler adds a factor of its own, and the PostgreSQL wire protocol has no TOTP dialogue, so there is nothing here to turn on and the honest answer is that this is not where a second factor goes.

The hooks that exist come with conditions worth knowing before you reach for them. PgBouncer's `auth_type` accepts `pam` and `ldap`, and `ldap` arrived in 1.25.0. Only `ldap` can be named inside `auth_hba_file`; selecting `pam` means setting it globally, which stops the HBA file being consulted and takes the client-range restriction of section 5 with it. PAM is also not an interactive one-time-password conversation here: the released implementation answers a hidden prompt with the same password the client already supplied, so it forwards a credential rather than conducting a challenge.

For a possession factor, `client_tls_sslmode = verify-full` with `client_tls_ca_file` requires a client certificate while leaving `auth_type = hba` and SCRAM in place, which is usually what you want. On that client-facing setting `verify-full` and `verify-ca` are the same thing; taking the user name from the certificate is what `auth_type = cert` does, and that, like `pam`, replaces HBA selection rather than adding to it.

Put the human paths to the host behind MFA per [mfa.md](mfa.md).

## Common mistakes

- Writing a trailing `;` or `#` comment on a `pgbouncer.ini` line. The vendor does not treat either as special after the start of a line, so the comment becomes part of the value and the setting silently is not what it reads as.
- Configuring TLS carefully on PostgreSQL, then putting a pooler in front of it with `client_tls_sslmode` left at its default, so every client connection is plaintext and the database's `hostssl` rules only ever match the pooler.
- Leaving `server_tls_sslmode` at `prefer` and reading a successful connection as an encrypted one. It falls back to plain TCP without an error, and it validates no certificate in any case.
- Treating `require` or `verify-ca` as equivalent to the client-side `sslmode=verify-full` they replaced. Neither checks the host name.
- Widening the database server's `pg_hba.conf` because the old client ranges stopped matching, or assuming that narrowing it to the pooler stops anything else in the old range connecting directly.
- Setting `user=` on a `[databases]` entry for convenience, which merges every client into one role and disables per-role privileges on the server.
- Switching `auth_type` from `hba` to `scram-sha-256` to "tighten" it, which stops `auth_hba_file` being read and drops the client-range restriction with it.
- Writing a `hostssl` rule in `pool_hba.conf` while `ssl` is still off. The record is ignored, so the rule you wrote to require TLS is not the rule being applied; whichever other record matches decides instead, and an unmatched connection is denied.
- Putting a database password in `PGPASSWORD` in a shell you are pasting commands into. Use `~/.pgpass` at mode `600`.
- Setting `listen_addresses` in `pgpool.conf` and expecting PCP to follow. `pcp_listen_addresses` is a separate setting, and `enable_pool_hba` is off by default, so pgpool-II authenticates nobody of its own until you turn it on.

## Sources (checked September 2026)

- PgBouncer configuration, including the ini comment rule, `listen_addr`, `listen_port`, `client_tls_sslmode`, `server_tls_sslmode`, `auth_type`, `auth_file`, `auth_query`, `admin_users`, `stats_users`, `application_name_add_host`, and the `[databases]` `user` key: https://www.pgbouncer.org/config.html
- PgBouncer usage, the admin console and its `SHOW` commands, including who `auth_type=any` admits and the passwordless Unix-socket login: https://www.pgbouncer.org/usage.html
- PgBouncer changelog, for CVE-2026-6664, CVE-2026-6665, CVE-2026-6666 and CVE-2026-6667, all fixed in 1.25.2: https://www.pgbouncer.org/changelog.html
- PgBouncer features and pooling modes: https://www.pgbouncer.org/features.html
- Pgpool-II connection settings (`listen_addresses`, `port`, `pcp_listen_addresses`, `pcp_port`, `enable_pool_hba`): https://www.pgpool.net/docs/latest/en/html/runtime-config-connection.html
- Pgpool-II SSL settings (`ssl`, `ssl_cert`, `ssl_key`, `ssl_ca_cert`, `ssl_ca_cert_dir`): https://www.pgpool.net/docs/latest/en/html/runtime-ssl.html
- Pgpool-II pool_hba.conf: https://www.pgpool.net/docs/latest/en/html/auth-pool-hba-conf.html
- Pgpool-II pcp.conf: https://www.pgpool.net/docs/latest/en/html/configuring-pcp-conf.html
- PostgreSQL pg_hba.conf, for what an address record matches: https://www.postgresql.org/docs/current/auth-pg-hba-conf.html
- PostgreSQL connection information functions (`inet_client_addr`): https://www.postgresql.org/docs/current/functions-info.html
- PostgreSQL statistics views, for what `pg_stat_ssl.ssl` does and does not report: https://www.postgresql.org/docs/current/monitoring-stats.html
- PostgreSQL logging configuration (`log_line_prefix`): https://www.postgresql.org/docs/current/runtime-config-logging.html
- PostgreSQL peer authentication, for why a console user name is not an OS identity: https://www.postgresql.org/docs/current/auth-peer.html
- PostgreSQL environment variables, on `PGPASSWORD` being "not recommended for security reasons": https://www.postgresql.org/docs/current/libpq-envars.html
- PostgreSQL password file, for the `~/.pgpass` format and its permission requirement: https://www.postgresql.org/docs/current/libpq-pgpass.html
- psql, for what `-c` accepts and what `-X` suppresses: https://www.postgresql.org/docs/current/app-psql.html
- PgBouncer 1.25.2 console source, which is what settles the `auth_type = any` disagreement above: https://raw.githubusercontent.com/pgbouncer/pgbouncer/pgbouncer_1_25_2/src/admin.c
- PgBouncer 1.25.2 PAM source, for what `pam` does with the supplied password: https://raw.githubusercontent.com/pgbouncer/pgbouncer/pgbouncer_1_25_2/src/pam.c
- Pgpool-II parameter syntax, which unlike pgbouncer.ini does treat a trailing `#` as a comment: https://www.pgpool.net/docs/latest/en/html/config-setting.html
- Pgpool-II authentication methods: https://www.pgpool.net/docs/latest/en/html/auth-methods.html
