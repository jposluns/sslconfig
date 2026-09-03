# MySQL and MariaDB: TLS and authentication

Default posture: keep the server on `127.0.0.1` (the packaged default on Debian/Ubuntu) and open it to remote clients only deliberately, with TLS required.

## 1. Server TLS

MySQL 8 generates a CA and server certificate in the data directory at initialization and enables TLS automatically; check with:

```sql
SHOW GLOBAL VARIABLES LIKE '%ssl%';
```

To use your own certificate ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)) and to refuse all cleartext connections, set in `/etc/mysql/mysql.conf.d/mysqld.cnf` (or the equivalent for your packaging):

```ini
[mysqld]
bind_address = 127.0.0.1          # widen deliberately
require_secure_transport = ON
tls_version = TLSv1.2,TLSv1.3
ssl_ca   = /etc/mysql/certs/ca.pem
ssl_cert = /etc/mysql/certs/server-cert.pem
ssl_key  = /etc/mysql/certs/server-key.pem
```

`require_secure_transport` rejects any TCP connection that is not TLS (Unix-socket connections remain allowed). Recent MariaDB versions support the same option; verify availability for your release.

## 2. Per-account requirements

Require TLS (or a client certificate) at the account level as a second control:

```sql
ALTER USER 'app'@'10.0.0.%' REQUIRE SSL;
-- or, for mutual TLS:
ALTER USER 'batch'@'10.0.0.%' REQUIRE X509;
```

Account hygiene per [authentication.md](authentication.md): keep the default `caching_sha2_password` plugin for new accounts (MySQL 8) rather than re-enabling `mysql_native_password`, remove anonymous accounts, and give the application a least-privilege user, never `root`.

MFA: MySQL 8.0.27 and later support up to 3 authentication factors per account, with factors 2 and 3 supplied by external plugins; the server-side FIDO plugin ships only in Enterprise Edition. On Community builds, treat `REQUIRE X509` client certificates as the practical second factor, and put human access paths behind MFA per [mfa.md](mfa.md).

## 3. Client side

Require identity verification of the server in addition to encryption:

```bash
mysql --host db.example.com --user app -p \
  --ssl-mode=VERIFY_IDENTITY --ssl-ca=/path/ca.pem
```

`--ssl-mode=REQUIRED` encrypts without identity verification; `VERIFY_CA`/`VERIFY_IDENTITY` verify the certificate (MySQL clients; MariaDB clients use `--ssl-verify-server-cert`). Connector options in application code follow the same distinction.

## 4. Verify

```sql
SHOW GLOBAL VARIABLES LIKE 'require_secure_transport';
SELECT user, host, ssl_type FROM mysql.user;      -- REQUIRE settings per account
\s                                                 -- in the client: the SSL line shows the cipher
```

```bash
ss -tlnp | grep 3306        # loopback only, unless remote access is deliberate
```

## Common mistakes

- Creating `'app'@'%'` with a weak password to fix a connection error, then never tightening the host mask.
- `require_secure_transport = ON` skipped because "the network is internal"; internal networks are where lateral movement happens.
- Shipping the client with `--ssl-mode=DISABLED` to silence certificate errors instead of installing the CA ([self-signed.md](self-signed.md)).

## Sources (checked September 2026)

- MySQL encrypted connections: https://dev.mysql.com/doc/refman/8.0/en/using-encrypted-connections.html
- MySQL multifactor authentication: https://dev.mysql.com/doc/refman/8.0/en/multifactor-authentication.html
- MariaDB TLS documentation: https://mariadb.com/kb/en/secure-connections-overview/
