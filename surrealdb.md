# SurrealDB: authentication and TLS

The quickest ways to start SurrealDB skip authentication or bind it to every interface, fine for a
laptop demo and a real exposure the moment the same command runs on a routable server.

## 1. Root user and authenticated mode

`surreal start` takes `--user`/`-u` and `--pass`/`-p` (also `SURREAL_USER`/`SURREAL_PASS`) to set
"the initial database root user, applied only if no other root user exists":

```bash
surreal start --user root --pass REPLACE_WITH_LONG_RANDOM_VALUE rocksdb:/data/mydb.db
```

The `--unauthenticated` flag (`SURREAL_UNAUTHENTICATED`) allows unauthenticated access instead; a
guest connecting under it gets permissions equivalent to the `OWNER` role. Do not run it, or carry it
from a local demo, on anything reachable beyond your own machine.

## 2. Bind privately

`--bind`/`-b` (`SURREAL_BIND`) sets the listening address and defaults to `127.0.0.1:8000`, loopback
only. Widen it deliberately, and only to a private address, for example `--bind 10.0.0.5:8000`; never
bind an unauthenticated or root-only instance to `0.0.0.0`. SurrealDB's own security guidance says
that if the database should only be reachable by other internal services, "expose SurrealDB
exclusively to the internal network instead of deploying the service with a publicly addressable
network interface."

## 3. User levels and access control

System users (`DEFINE USER`) exist at three levels: root (visibility across every namespace and
database), namespace, and database, each assigned a role of `OWNER`, `EDITOR`, or `VIEWER`. The docs
warn plainly that "a root system user is not restricted by permissions at all, so it is the wrong
credential to put in an application"; give an application its own namespace or database level user
scoped to what it needs.

Record users are different: they are rows in your own tables, authenticated through
`DEFINE ACCESS ... TYPE RECORD` with custom `SIGNUP` and `SIGNIN` logic, and they "have no
permissions" beyond what a `PERMISSIONS` clause on a table or field grants them, the same
rules-are-the-security model as Firebase and Supabase ([firebase-supabase.md](firebase-supabase.md)):
a table with no `PERMISSIONS` clause for a record user grants nothing by default. `DEFINE ACCESS`
also supports `TYPE JWT` (trusting an external identity provider's tokens) and `TYPE BEARER`
(per-client keys) for system-to-system authentication.

## 4. TLS

`--web-crt` and `--web-key` serve SurrealDB's own interfaces over HTTPS directly. SurrealDB's own
guidance also endorses delegating TLS termination to a load balancer or reverse proxy, per
[nginx.md](nginx.md) or [caddy.md](caddy.md), or reaching the instance only over a tailnet
([tailscale.md](tailscale.md)).

## Verify

```bash
ss -tlnp | grep 8000                          # loopback or private address only, never 0.0.0.0
curl -sI http://127.0.0.1:8000/health          # process is up
surreal sql --endpoint http://127.0.0.1:8000 --namespace test --database test
```

The last command, run with no `--username`/`--password` against an instance started without
`--unauthenticated`, must be refused rather than dropping into a session. A connection from outside
the bound address must fail at the network layer, not just the application layer, and `curl -vI
https://` should show a valid certificate chain wherever TLS terminates.

## Sources (checked September 2026)

- SurrealDB CLI, `surreal start`: https://surrealdb.com/docs/surrealdb/cli/start
- SurrealDB CLI, `surreal sql`: https://surrealdb.com/docs/surrealdb/cli/sql
- SurrealDB security overview: https://surrealdb.com/docs/surrealdb/security
- SurrealDB authentication overview: https://surrealdb.com/docs/learn/security/authentication/overview
- SurrealDB security best practices: https://surrealdb.com/docs/learn/security/best-practices/security-best-practices
