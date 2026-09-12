# RabbitMQ: users, TLS listener, and the guest account

RabbitMQ's default `guest`/`guest` account can only connect from localhost, which protects fresh installs exactly until someone "fixes" it. The documented recommendation is to create real users and delete `guest` or change its password.

## 1. Accounts

```bash
sudo rabbitmqctl add_user 'app' 'REPLACE_WITH_LONG_RANDOM_PASSWORD'
sudo rabbitmqctl set_permissions -p '/' 'app' '.*' '.*' '.*'   # configure, write, read; narrow per app
sudo rabbitmqctl add_user 'ops' '...'
sudo rabbitmqctl set_user_tags 'ops' administrator
sudo rabbitmqctl delete_user 'guest'
```

Scope the permission regexes to what each application actually uses, per [authentication.md](authentication.md). Do not loosen the guest account's localhost restriction.

## 2. TLS listener

`rabbitmq.conf`:

```
listeners.ssl.default = 5671
ssl_options.cacertfile = /etc/rabbitmq/tls/ca.pem
ssl_options.certfile   = /etc/rabbitmq/tls/server.pem
ssl_options.keyfile    = /etc/rabbitmq/tls/server.key
ssl_options.verify     = verify_peer
# mutual TLS; set false to allow password-only clients
ssl_options.fail_if_no_peer_cert = true

# once every client speaks TLS:
listeners.tcp = none
```

Certificates per [self-signed.md](self-signed.md) (internal CA fits brokers well) or [free-certificates.md](free-certificates.md). Mutual TLS gives a machine client a possession factor, a certificate held by the connecting host, stronger than a password alone but not MFA for a person ([mfa.md](mfa.md)).

## 3. Management UI

The management plugin's web UI is an admin panel: keep it off public interfaces and reach it per [admin-uis.md](admin-uis.md) (SSH forward, tailnet, or Access), with its own TLS when remote.

## 4. Verify

```bash
ss -tlnp | grep -E '5671|5672|15672'      # 5672 gone once listeners.tcp = none; UI private

# Positive: a client holding a certificate connects.
openssl s_client -connect mq.example.com:5671 -CAfile ca.pem \
  -cert client.pem -key client.key \
  -verify_hostname mq.example.com -verify_return_error </dev/null

# Negative, and this half is what discriminates: drop -cert and -key, and the broker must
# close the connection, because ssl_options.fail_if_no_peer_cert = true requires one.
openssl s_client -connect mq.example.com:5671 -CAfile ca.pem \
  -verify_hostname mq.example.com -verify_return_error </dev/null

# "Verification: OK" reports the SERVER certificate only, and it prints in BOTH runs. The
# pass condition is the pair: the first run reaches a session, the second ends in "peer did
# not return a certificate" on TLS 1.2 or a "certificate required" alert on TLS 1.3. Reading
# "Verification: OK" from the second run as a success is the mistake this pair exists to
# catch. Without -verify_return_error the handshake completes even when the server
# certificate fails to verify, so -CAfile alone proves only that TLS is on. If you set
# fail_if_no_peer_cert = false, the second run succeeds as well and the pair proves nothing,
# because a password is then the client's only identity.
# Remote login attempt as guest fails: "user 'guest' can only connect via localhost"
```

## Sources (checked September 2026)

- RabbitMQ TLS: https://www.rabbitmq.com/docs/ssl
- RabbitMQ access control (guest restrictions, user commands, recommendation): https://www.rabbitmq.com/docs/access-control
