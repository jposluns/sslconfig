# NATS and JetStream: authentication, TLS, and the monitoring port

NATS accepts client connections on 4222 with no authentication configured by default, and a separately enabled HTTP monitoring endpoint (conventionally 8222) that reveals connected clients, subjects, and traffic with no login of its own. Both need explicit configuration. JetStream (the persistence layer for streams and consumers) is a feature of the same server process: it adds no listening port of its own, and its state surfaces through the same monitoring endpoint (`/jsz`) rather than a dedicated one.

## 1. Require authentication

Inside an `authorization { }` block in the server config, pick one mechanism: a shared token, per-user password, or NKEYS (public-key identity, no password on the wire):

```
authorization {
  users: [
    { user: app, password: "REPLACE_WITH_LONG_RANDOM_PASSWORD" }
    { nkey: UAPZQH4MNJCOVEJFERB3NFSIROQ5RE7CGBEPKAZSB6QB7IQHBKXHZPVP }
  ]
}
```

Decentralized JWT-based auth (accounts and users signed by an operator, for multi-tenant deployments) is documented separately. Do not set `no_auth_user`, which names a user that unauthenticated connections are admitted as, unless an anonymous path is deliberate; it is easy to leave in place after testing and forget it grants access.

## 2. Scope what each user can do

A user with no `permissions` block is unrestricted. Give each identity subject-level allow lists so a compromised credential cannot publish or subscribe everywhere:

```
authorization {
  users: [
    {
      user: order-svc
      password: "REPLACE_WITH_LONG_RANDOM_PASSWORD"
      permissions: {
        publish:   { allow: ["orders.>"] }
        subscribe: { allow: ["_INBOX.>"] }
      }
    }
  ]
}
```

The moment a `permissions` block writes an `allow` list, every subject not on it is denied; `deny` entries take precedence over `allow` when both are present.

## 3. Enable TLS

```
tls {
  cert_file: "/etc/nats/certs/server-cert.pem"
  key_file:  "/etc/nats/certs/server-key.pem"
  ca_file:   "/etc/nats/certs/ca.pem"
  verify: true
}
```

Certificates per [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md). `verify: true` requires and verifies a client certificate against `ca_file` (mutual TLS). `verify_and_map: true` does the same and also derives the connecting user's identity from the certificate (email, DNS, or URI SANs, or the distinguished name); use one or the other, not both.

## 4. Keep the monitoring port private

The HTTP monitoring endpoint is off unless configured (`http_port: 8222` in the config file, or `-m 8222` on the command line; `https_port` serves the same data over TLS). It answers `/varz`, `/connz`, `/routez`, and, with JetStream enabled, `/jsz`, as JSON, and the documentation is direct about the risk: "anyone who can reach `:8222` can read `/connz` and see your users, subjects, and traffic." Bind it to loopback or a private network, or place it behind an authenticating proxy; do not publish it.

## Verify

```bash
ss -tlnp | grep -E ':(4222|8222) '                                                                                                                          # 4222 as intended, 8222 loopback/private only
nats pub orders.created hello --tlsca /etc/nats/certs/ca.pem --tlscert REPLACE_WITH_CLIENT_CERT_FILE --tlskey REPLACE_WITH_CLIENT_KEY_FILE --user order-svc --password REPLACE_WITH_LONG_RANDOM_PASSWORD   # allowed subject, valid credentials: succeeds
nats pub other.subject hello --tlsca /etc/nats/certs/ca.pem --tlscert REPLACE_WITH_CLIENT_CERT_FILE --tlskey REPLACE_WITH_CLIENT_KEY_FILE --user order-svc --password REPLACE_WITH_LONG_RANDOM_PASSWORD     # subject outside the allow list: fails
nats pub orders.created hello --tlsca /etc/nats/certs/ca.pem --tlscert REPLACE_WITH_CLIENT_CERT_FILE --tlskey REPLACE_WITH_CLIENT_KEY_FILE                                                                  # no --user/--password: fails
curl -s http://monitor.example.com:8222/connz                                                                                                               # connection refused/timeout from outside
```

## Common mistakes

- Leaving `no_auth_user` set after testing, which quietly readmits anonymous clients.
- Exposing 8222 (or `https_port`) on a public interface because it "is just monitoring."
- A user with no `permissions` block, which is unrestricted rather than denied.

## Sources (checked September 2026)

- Securing NATS overview: https://docs.nats.io/running-a-nats-service/configuration/securing_nats
- Authentication basics (token, user/password, nkeys, no_auth_user): https://docs.nats.io/learn/security/authentication-basics
- Authorization (subject permissions, allow/deny) and Encryption/TLS (tls block): https://docs.nats.io/learn/security/authorization and https://docs.nats.io/learn/security/encryption
- TLS Authentication (verify vs verify_and_map): https://docs.nats.io/running-a-nats-service/configuration/securing_nats/auth_intro/tls_mutual_auth
- Monitoring (http_port/https_port, /varz, /connz, /routez, /jsz): https://docs.nats.io/running-a-nats-service/configuration/monitoring
- JetStream concepts: https://docs.nats.io/nats-concepts/jetstream
