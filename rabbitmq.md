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
ssl_options.fail_if_no_peer_cert = true   # mutual TLS; set false to allow password-only clients

# once every client speaks TLS:
listeners.tcp = none
```

Certificates per [self-signed.md](self-signed.md) (internal CA fits brokers well) or [free-certificates.md](free-certificates.md). Mutual TLS doubles as the second factor for machine clients ([mfa.md](mfa.md)).

## 3. Management UI

The management plugin's web UI is an admin panel: keep it off public interfaces and reach it per [admin-uis.md](admin-uis.md) (SSH forward, tailnet, or Access), with its own TLS when remote.

## 4. Verify

```bash
ss -tlnp | grep -E '5671|5672|15672'      # 5672 gone once listeners.tcp = none; UI private
openssl s_client -connect mq.example.com:5671 -CAfile ca.pem </dev/null   # TLS handshake
# Remote login attempt as guest fails: "user 'guest' can only connect via localhost"
```

## Sources (checked September 2026)

- RabbitMQ TLS: https://www.rabbitmq.com/docs/ssl
- RabbitMQ access control (guest restrictions, user commands, recommendation): https://www.rabbitmq.com/docs/access-control
