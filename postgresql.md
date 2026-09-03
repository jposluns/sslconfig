# PostgreSQL: TLS and authentication

Default posture: PostgreSQL should not listen on public interfaces at all. Widen `listen_addresses` only for genuine remote clients, and then require both TLS and SCRAM authentication as below.

## 1. Server TLS

Get a certificate ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)), give the key to the `postgres` user with mode `600`, then in `postgresql.conf`:

```
listen_addresses = 'localhost'            # widen deliberately, e.g. 'localhost,10.0.0.5'
ssl = on
ssl_cert_file = '/etc/ssl/certs/server.crt'
ssl_key_file  = '/etc/ssl/private/server.key'
ssl_min_protocol_version = 'TLSv1.2'      # PostgreSQL 12 and later
password_encryption = scram-sha-256       # default from PostgreSQL 14; set explicitly on older versions
```

Reload with `SELECT pg_reload_conf();` or `systemctl reload postgresql`.

## 2. Require TLS per connection in pg_hba.conf

`hostssl` matches only TLS connections; plain `host` lines accept cleartext. Remote entries should all be `hostssl` with `scram-sha-256`:

```
# TYPE     DATABASE  USER  ADDRESS        METHOD
local      all       all                  peer
hostssl    app       app   10.0.0.0/24    scram-sha-256
# No 'host ... 0.0.0.0/0 trust' or 'password' lines. Ever.
```

Passwords set before `password_encryption = scram-sha-256` remain MD5-hashed; re-set them (`\password app`) so SCRAM applies.

For machine-to-machine links, add certificate verification on top of SCRAM: set `ssl_ca_file` in `postgresql.conf` and append `clientcert=verify-full` to the `hostssl` line (PostgreSQL 12 and later).

## 3. Client side

Require identity verification in the connection settings, in addition to encryption:

```
psql "host=db.example.com dbname=app user=app sslmode=verify-full sslrootcert=/path/ca.crt"
```

`sslmode=require` encrypts but does not verify the server's identity; `verify-full` does both. Application connection strings take the same parameters.

## 4. Verify

```bash
psql -h db.example.com -U app -c "SELECT version();" \
  "dbname=app sslmode=verify-full sslrootcert=/path/ca.crt"
sudo -u postgres psql -c "SELECT ssl, count(*) FROM pg_stat_ssl JOIN pg_stat_activity USING (pid) GROUP BY ssl;"
ss -tlnp | grep 5432       # loopback only, unless remote access is deliberate
```

A connection attempt without TLS from a remote host must fail once only `hostssl` lines cover remote addresses.

## Common mistakes

- `listen_addresses = '*'` plus a permissive `host all all 0.0.0.0/0 md5` line pasted from a tutorial.
- `trust` authentication left enabled for remote addresses.
- The superuser (`postgres`) used as the application account; create a least-privilege role instead ([authentication.md](authentication.md)).

## Sources (checked September 2026)

- Secure TCP/IP connections with SSL: https://www.postgresql.org/docs/current/ssl-tcp.html
- pg_hba.conf: https://www.postgresql.org/docs/current/auth-pg-hba-conf.html
- libpq SSL support (sslmode): https://www.postgresql.org/docs/current/libpq-ssl.html
