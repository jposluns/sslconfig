# Neo4j: listen address, initial password, and TLS on Bolt and HTTPS

Neo4j 5 listens on `localhost` only by default and ships with authentication on, but with the well-known `neo4j`/`neo4j` credential, Bolt TLS at `DISABLED`, and plaintext HTTP enabled instead of HTTPS. Setting `server.default_listen_address=0.0.0.0` to "make it reachable" therefore exposes a database with a guessable password over plaintext. Setting names below are Neo4j 5; Neo4j 4.x names differ.

## 1. Set the initial password before first start

```bash
neo4j-admin dbms set-initial-password REPLACE_WITH_LONG_RANDOM_VALUE --require-password-change=false
```

This command is for use once, before the database's first start; the default minimum length is 8 characters (`dbms.security.auth_minimum_password_length`). The documentation warns against typing the password on the command line where it lands in shell history; prompt for it instead. Leave `dbms.security.auth_enabled` at its default `true`; the documentation reserves turning it off for recovery with all network access blocked.

## 2. Bind deliberately

`server.default_listen_address` supplies the host part for every connector (`server.bolt.listen_address` defaults to `:7687`, `server.http.listen_address` to `:7474`, `server.https.listen_address` to `:7473`). Keep the default `localhost` unless remote clients are deliberate, then prefer a specific private address over `0.0.0.0`. The documentation notes that changing it may expose cluster ports and recommends overriding the cluster `listen_address` settings to `localhost` when clustering is not in use; the backup port (`server.backup.listen_address`, default `127.0.0.1:6362`) must stay off external interfaces. Firewall per [cloud-firewalls.md](cloud-firewalls.md) or [host.md](host.md), and widen only after steps 3 and 4.

```properties
server.default_listen_address=203.0.113.10
```

## 3. TLS on Bolt and HTTPS, HTTP off

Put a PKCS#8 PEM private key and certificate ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)) under the policy directory, owned by `neo4j:neo4j`, key mode `0400`, certificate `0644`; legacy PKCS#1 keys (the PEM header that names an RSA key) are deprecated and must be converted. `server.bolt.tls_level=REQUIRED` refuses unencrypted Bolt (`OPTIONAL` keeps accepting it); `server.http.enabled=false` removes the plaintext 7474 endpoint. For machine clients that can hold certificates, `dbms.ssl.policy.bolt.client_auth=REQUIRE` adds mutual TLS.

```properties
dbms.ssl.policy.bolt.enabled=true
dbms.ssl.policy.bolt.base_directory=certificates/bolt
dbms.ssl.policy.bolt.private_key=private.key
dbms.ssl.policy.bolt.public_certificate=public.crt
dbms.ssl.policy.bolt.client_auth=NONE
server.bolt.tls_level=REQUIRED

dbms.ssl.policy.https.enabled=true
dbms.ssl.policy.https.base_directory=certificates/https
dbms.ssl.policy.https.private_key=private.key
dbms.ssl.policy.https.public_certificate=public.crt
dbms.ssl.policy.https.client_auth=NONE
server.https.enabled=true
server.http.enabled=false
```

## 4. Users and roles

Create a user per application instead of sharing `neo4j` ([authentication.md](authentication.md)). Role-based access control (built-in roles `reader`, `editor`, `publisher`, `architect`, `admin`, plus custom roles) is documented for Enterprise Edition; Community Edition has native users and passwords but no role management, so it cannot give an application read-only access and the network boundary carries more weight. Failed logins lock an account for `dbms.security.auth_lock_time` (default `5s`) after `dbms.security.auth_max_failed_attempts` (default `3`).

```cypher
CREATE USER app SET PASSWORD 'REPLACE_WITH_LONG_RANDOM_VALUE' CHANGE NOT REQUIRED;
GRANT ROLE reader TO app;    // Enterprise Edition; editor or publisher for writers
```

MFA: native login has no second factor. Enterprise Edition can delegate authentication to LDAP or an OIDC provider, where MFA is enforced at the identity provider ([mfa.md](mfa.md), [oidc-integration.md](oidc-integration.md)); otherwise mutual TLS is the possession factor for services and every human path to the host sits behind MFA.

## Verify

Clients and drivers connect with `neo4j+s://`, which verifies the certificate; `neo4j+ssc://` accepts a self-signed certificate without verification and belongs in development only.

```bash
ss -tlnp | grep -E '7474|7473|7687'                             # 7473 and 7687 only, on the intended address
openssl s_client -connect neo4j.example.com:7687 -verify_hostname neo4j.example.com \
  -verify_return_error -CAfile ca.pem </dev/null                 # prints Verification: OK. Point -CAfile
                                                                 # at the CA that signed the server
                                                                 # certificate; omit it only for a
                                                                 # publicly trusted one, since a
                                                                 # self-signed or internal CA is not in
                                                                 # the system store and the check would
                                                                 # fail on a correct deployment. Without
                                                                 # the verify flags the handshake succeeds
                                                                 # against any certificate
curl -sI http://neo4j.example.com:7474/                          # connection refused
cypher-shell -a neo4j://neo4j.example.com:7687 -u app -p '...'   # unencrypted: refused with tls_level=REQUIRED
cypher-shell -a neo4j+s://neo4j.example.com:7687 -u neo4j -p neo4j   # default credential: authentication failure
cypher-shell -a neo4j+s://neo4j.example.com:7687 -u app -p 'REPLACE_WITH_LONG_RANDOM_VALUE'   # works
```

## Common mistakes

- `server.default_listen_address=0.0.0.0` set during installation "to test", with `neo4j`/`neo4j` still in place.
- Bolt TLS configured but left at `server.bolt.tls_level=OPTIONAL`, so `neo4j://` clients keep connecting in plaintext.
- HTTPS enabled while `server.http.enabled` stays `true`, leaving 7474 open beside 7473.

## Sources (checked September 2026)

- Configure network connectors: https://neo4j.com/docs/operations-manual/current/configuration/connectors/
- Ports: https://neo4j.com/docs/operations-manual/current/configuration/ports/
- Set an initial password: https://neo4j.com/docs/operations-manual/current/configuration/set-initial-password/
- SSL framework: https://neo4j.com/docs/operations-manual/current/security/ssl-framework/
- Authentication and authorization: https://neo4j.com/docs/operations-manual/current/authentication-authorization/
- Manage users: https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-users/
- Manage roles: https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-roles/
- Built-in roles: https://neo4j.com/docs/operations-manual/current/authentication-authorization/built-in-roles/
- Cypher Shell: https://neo4j.com/docs/operations-manual/current/cypher-shell/
