# ClickHouse: listen address, the default user, and TLS ports

ClickHouse listens on localhost only until you set `listen_host`, but it ships with a `default` user that has an empty password, may connect from any address (`<ip>::/0</ip>`), and holds `access_management`, so widening `listen_host` to `::` or `0.0.0.0` publishes a passwordless administrator on plaintext HTTP 8123 and native TCP 9000. Widen only after steps 2 and 3.

## 1. Keep `listen_host` narrow

The shipped `config.xml` comments out every `listen_host` example and says the default is to "try listen localhost on IPv4 and IPv6". For remote clients, name the one private address rather than `::`. Every port then binds there: `http_port` 8123, `tcp_port` 9000, `mysql_port` 9004, `postgresql_port` 9005, and `interserver_http_port` 9009 (replica traffic). Firewall them per [cloud-firewalls.md](cloud-firewalls.md) or [host.md](host.md).

```xml
<listen_host>127.0.0.1</listen_host>
<listen_host>203.0.113.10</listen_host>
```

## 2. Put a password on `default`, and create real users

In `users.xml` the `default` user is `<password></password>`. Replace that with a hash (the shipped file documents `echo -n "$PASSWORD" | sha256sum | tr -d '-'`) and restrict where it may connect from. `password_double_sha1_hex` exists for MySQL-protocol clients; plain `<password>` is documented but stores the secret in clear.

```xml
<users>
  <default>
    <password_sha256_hex>REPLACE_WITH_THE_SHA256_HEX_OF_A_LONG_RANDOM_PASSWORD</password_sha256_hex>
    <networks>
      <ip>::1</ip>
      <ip>127.0.0.1</ip>
    </networks>
    <profile>default</profile>
    <quota>default</quota>
    <access_management>1</access_management>
  </default>
</users>
```

Because `default` holds `access_management`, use it once to create per-application users with SQL, each limited to its source network and its database ([authentication.md](authentication.md)). `IDENTIFIED WITH bcrypt_password BY '...'` (72-character maximum) is also available and stores a slower hash. The access-control documentation recommends disabling `default` in production once a SQL admin user exists and inter-node credentials are configured, since `default` is what nodes use to talk to each other; until then, the loopback-only `<networks>` above keeps it off the network.

```sql
CREATE USER app HOST IP '10.0.0.0/8' IDENTIFIED WITH sha256_password BY 'REPLACE_WITH_LONG_RANDOM_VALUE';
GRANT SELECT, INSERT ON appdb.* TO app;
```

## 3. TLS listeners, plaintext ports off

Get a certificate ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)), enable the secure ports, and comment out the plaintext ones, as the vendor's TLS guide does. Treat `mysql_port`, `postgresql_port`, and `interserver_http_port` the same way: remove them or keep them on a private address (`interserver_https_port` 9010 is the TLS variant). Users can also be identified by client certificate (`IDENTIFIED WITH ssl_certificate CN 'name'`), the possession factor for machine clients ([machine-auth.md](machine-auth.md)). MFA: ClickHouse has no second-factor dialogue of its own; human paths to the host and to any dashboard in front of it go behind MFA per [mfa.md](mfa.md).

```xml
<https_port>8443</https_port>
<tcp_port_secure>9440</tcp_port_secure>
<!-- <http_port>8123</http_port> -->
<!-- <tcp_port>9000</tcp_port> -->
<openSSL>
  <server>
    <certificateFile>/etc/clickhouse-server/certs/server.crt</certificateFile>
    <privateKeyFile>/etc/clickhouse-server/certs/server.key</privateKeyFile>
    <disableProtocols>sslv2,sslv3</disableProtocols>
    <preferServerCiphers>true</preferServerCiphers>
  </server>
</openSSL>
```

## Verify

Clients use `clickhouse-client --secure` on 9440, or HTTPS on 8443 with HTTP basic auth or the `X-ClickHouse-User` and `X-ClickHouse-Key` headers; the documentation discourages `user` and `password` URL parameters because proxies log them.

```bash
ss -tlnp | grep -E '8123|9000|8443|9440'          # only 8443 and 9440, on the intended address
curl -s http://ch.example.com:8123/                # connection refused
curl -s 'https://ch.example.com:8443/?query=SELECT%201'   # no credentials = default with empty password: authentication error
curl -u app:REPLACE_WITH_LONG_RANDOM_VALUE 'https://ch.example.com:8443/?query=SELECT%201'   # 1
clickhouse-client --host ch.example.com --port 9440 --secure --user app --password
```

## Common mistakes

- `<listen_host>::</listen_host>` uncommented to reach the server from a laptop, with `default` still passwordless.
- A password set on `default` while `<networks>` still says `::/0`, so the one administrator account is guessable from anywhere.
- `https_port` added while `http_port` 8123 stays open beside it.

## Sources (checked September 2026)

- Server configuration parameters (ports, `listen_host`, `openSSL`): https://clickhouse.com/docs/reference/settings/server-settings/settings
- Shipped `config.xml` (`listen_host` default comment, `openSSL` block): https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/programs/server/config.xml
- User settings (`password_sha256_hex`, `networks`, `access_management`): https://clickhouse.com/docs/concepts/features/configuration/settings/settings-users
- Shipped `users.xml` (default user, empty password, `::/0`): https://raw.githubusercontent.com/ClickHouse/ClickHouse/master/programs/server/users.xml
- Access control and account management: https://clickhouse.com/docs/concepts/features/security/access-rights
- CREATE USER: https://clickhouse.com/docs/reference/statements/create/user
- GRANT: https://clickhouse.com/docs/reference/statements/grant
- Configuring SSL-TLS: https://clickhouse.com/docs/concepts/features/security/tls/configuring-tls
- HTTP interface (ports, authentication): https://clickhouse.com/docs/concepts/features/interfaces/http
