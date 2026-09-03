# Mosquitto (MQTT): no anonymous clients, TLS listener

MQTT brokers back IoT and agent projects, and open brokers leak live telemetry and accept injected commands. Mosquitto's defaults are sane (with listeners defined, anonymous access is off; without any listener it serves the local machine only); the job is to keep them sane while adding real listeners.

## 1. Credentials per device

```bash
sudo mosquitto_passwd -c /etc/mosquitto/passwd device-01     # -c only the first time
sudo mosquitto_passwd /etc/mosquitto/passwd device-02
```

`/etc/mosquitto/conf.d/secure.conf`:

```
per_listener_settings false
allow_anonymous false
password_file /etc/mosquitto/passwd
```

One credential per device, so a leaked unit can be revoked alone; add an `acl_file` to limit each identity to its own topics.

## 2. TLS listener

```
listener 8883
cafile   /etc/mosquitto/tls/ca.pem
certfile /etc/mosquitto/tls/server.pem
keyfile  /etc/mosquitto/tls/server.key
# require_certificate true      # mutual TLS: clients must present certificates
```

Port 8883 is the conventional MQTT-over-TLS port. Certificates per [self-signed.md](self-signed.md) (an internal CA suits device fleets) or [free-certificates.md](free-certificates.md). `require_certificate true` turns client certificates into the second factor for machines ([mfa.md](mfa.md)). Remove or firewall any plaintext `listener 1883` that is not strictly local.

## 3. Verify

```bash
mosquitto_sub -h mq.example.com -p 8883 --cafile ca.pem -t 'test' -u device-01 -P '...'   # works
mosquitto_sub -h mq.example.com -p 8883 --cafile ca.pem -t 'test'                          # refused (no credentials)
ss -tlnp | grep -E '1883|8883'                                                             # no public 1883
```

## Sources (checked September 2026)

- mosquitto.conf manual (allow_anonymous defaults, password_file, listener, certfile/keyfile/cafile, require_certificate): https://mosquitto.org/man/mosquitto-conf-5.html
