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
# client.pem and client.key are a CLIENT certificate and key issued by the CA in
# ssl_options.cacertfile, with TLS Web Client Authentication in its extended key usage.
# A serverAuth-only certificate signed by that same CA is NOT a substitute, and the
# reason is the extended key usage rather than the chain: the chain verifies either way,
# which is what makes this an easy mistake to make and a hard one to see. A certificate
# carrying both serverAuth and clientAuth does satisfy it, which RabbitMQ documents
# while still recommending separate certificates for the two purposes.
sleep 10 | openssl s_client -connect mq.example.com:5671 -CAfile ca.pem \
  -cert client.pem -key client.key \
  -verify_hostname mq.example.com -verify_return_error
echo "positive run exit $?"

# Negative, and this half is what discriminates: drop -cert and -key, and the broker must
# refuse the connection, because ssl_options.fail_if_no_peer_cert = true requires one.
sleep 10 | openssl s_client -connect mq.example.com:5671 -CAfile ca.pem \
  -verify_hostname mq.example.com -verify_return_error
echo "negative run exit $?"

# "Verification: OK" reports the SERVER certificate only, and it prints in BOTH runs. The
# pass condition is the pair: the first run exits 0 and the second does not. Do
# not match on a particular message. The broker rejects an empty client certificate list
# with a fatal alert. On TLS 1.3 the client can consider its own side finished before that
# alert arrives, and the exact wording comes from whichever TLS stack is reporting it.
# What you are looking for is a non-zero exit from the second run. Note the `sleep 10` on
# BOTH runs: with `</dev/null` s_client reaches end of input and exits before the rejection
# arrives, because on TLS 1.3 the server can only refuse the empty client certificate after
# the client's flight. Measured, that negative run exits 0 and prints a full session block
# four times in five, which is indistinguishable from the positive one. Holding stdin open
# is what makes the refusal observable, and the hold has to outlast the broker's own
# handshake timeout, not just the round trip: `sleep 10` starts at the same moment as
# s_client, before DNS, the TCP connect and the negotiation, so a short hold can be spent
# before the moment it was meant to cover. This check is timing-dependent and says so. If
# BOTH runs exit 0, treat that as inconclusive rather than as a pass, and read the broker
# log, which records the rejection regardless of what the client saw. The positive run
# needs it for the same reason in reverse: with `</dev/null` it exits 0 before a rejection
# of a WRONG client certificate can arrive, so a broken deployment reads as a working one.
# Reading "Verification: OK" from the second run as a success is the mistake this pair
# exists to catch. Without -verify_return_error the handshake completes even when the
# server certificate fails to verify, so -CAfile alone proves only that TLS is on. If you
# set fail_if_no_peer_cert = false, the second run succeeds as well and the pair proves
# nothing, because a password is then the client's only identity.
# Remote login attempt as guest fails: "user 'guest' can only connect via localhost"
```

## Sources (checked September 2026)

- RabbitMQ TLS: https://www.rabbitmq.com/docs/ssl
- RabbitMQ access control (guest restrictions, user commands, recommendation): https://www.rabbitmq.com/docs/access-control
