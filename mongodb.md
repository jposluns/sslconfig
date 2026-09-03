# MongoDB: TLS and authorization

MongoDB's history of mass data leaks comes from 2 settings: binding to all interfaces and running with authorization off. Fix both before anything else, then add TLS. Applies to MongoDB 4.2 and later (`tls` options; earlier versions used `ssl` names).

## 1. Enable authorization and create the admin user

In `/etc/mongod.conf`:

```yaml
net:
  port: 27017
  bindIp: 127.0.0.1        # widen deliberately, e.g. 127.0.0.1,10.0.0.5
security:
  authorization: enabled
```

Restart, then use the localhost exception to create the first administrator (connect from the server itself with `mongosh`):

```javascript
use admin
db.createUser({
  user: "admin",
  pwd: passwordPrompt(),
  roles: [ { role: "userAdminAnyDatabase", db: "admin" } ]
})
```

Create a separate least-privilege user per application (for example `readWrite` on its own database), per [authentication.md](authentication.md). Modern MongoDB authenticates with SCRAM-SHA-256 by default.

MFA: the wire protocol has no TOTP dialogue in Community edition; x.509 client-certificate authentication is the second factor for direct connections, and human paths to the host (SSH, admin UIs) go behind MFA per [mfa.md](mfa.md).

## 2. Enable TLS

Get a certificate ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)), concatenate certificate and key into one PEM, and require TLS:

```bash
cat server.crt server.key > /etc/ssl/mongodb/server.pem
chmod 600 /etc/ssl/mongodb/server.pem
```

```yaml
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/ssl/mongodb/server.pem
    CAFile: /etc/ssl/mongodb/ca.crt     # needed when clients or cluster members present certificates
```

`requireTLS` rejects plain connections outright; the transitional modes (`allowTLS`, `preferTLS`) exist for rolling upgrades only.

## 3. Client side

```bash
mongosh "mongodb://admin@db.example.com:27017/?authSource=admin&tls=true" \
  --tlsCAFile /path/ca.crt
```

Driver connection strings take the same `tls=true` and CA options. Do not ship `tlsAllowInvalidCertificates`; install the CA instead ([self-signed.md](self-signed.md)).

## 4. Verify

```bash
ss -tlnp | grep 27017                       # loopback only, unless remote access is deliberate
mongosh --host db.example.com               # without credentials/TLS: refused once hardened
mongosh "mongodb://db.example.com/?tls=true" --tlsCAFile ca.crt   # connects, then requires auth
```

From an unauthenticated session, `show dbs` must fail with an authorization error.

## Common mistakes

- `bindIp: 0.0.0.0` set to fix a connection problem, with `authorization` still unset; this is the classic leaked-database configuration.
- Authorization enabled but every service sharing the `admin` account.
- TLS on the server while the connection string still says `tls=false` because a container healthcheck was easier that way.

## Sources (checked September 2026)

- MongoDB security checklist: https://www.mongodb.com/docs/manual/administration/security-checklist/
- Configure TLS/SSL for mongod: https://www.mongodb.com/docs/manual/tutorial/configure-ssl/
- Enable access control: https://www.mongodb.com/docs/manual/tutorial/enable-authentication/
