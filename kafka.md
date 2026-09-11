# Apache Kafka: SASL_SSL listeners, SCRAM credentials, and ACLs

Kafka's broker defaults are `listeners=PLAINTEXT://:9092`, `security.inter.broker.protocol=PLAINTEXT`, and no authorizer, so anyone who reaches port 9092 can read every topic, produce to it, and create or delete topics with no credential and no encryption. Property names below come from the Kafka 4.x documentation (KRaft mode).

## 1. Replace the plaintext listener

In `server.properties`, publish one `SASL_SSL` listener and use it between brokers too. Remove `PLAINTEXT://:9092`; if local tooling still needs it, bind it to `127.0.0.1` and never advertise it. KRaft controllers use their own listener (`controller.listener.names`); map it to `SASL_SSL` in `listener.security.protocol.map` (the documentation's example is `BROKER:SASL_SSL,CONTROLLER:SASL_SSL`) or keep it on a private interface.

```properties
listeners=SASL_SSL://0.0.0.0:9093
advertised.listeners=SASL_SSL://kafka.example.com:9093
security.inter.broker.protocol=SASL_SSL
```

## 2. TLS on the broker

Get a certificate ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md); an internal CA fits a cluster) and point the broker at it. Kafka 2.7.0 and later also take PEM: `ssl.keystore.type=PEM` with `ssl.keystore.certificate.chain` and `ssl.keystore.key` (PKCS#8), and `ssl.truststore.type=PEM` with `ssl.truststore.certificates`. Hostname verification (`ssl.endpoint.identification.algorithm`) is on by default since 2.0.0; the documentation discourages blanking it.

```properties
ssl.keystore.location=/var/private/ssl/server.keystore.jks
ssl.keystore.password=REPLACE_WITH_LONG_RANDOM_VALUE
ssl.key.password=REPLACE_WITH_LONG_RANDOM_VALUE
ssl.truststore.location=/var/private/ssl/server.truststore.jks
ssl.truststore.password=REPLACE_WITH_LONG_RANDOM_VALUE
# Client certificates on the SASL_SSL listener: none (default), requested (optional), or required (mutual TLS).
# The unprefixed ssl.client.auth applies only to SSL listeners, so a SASL_SSL listener needs the listener prefix.
listener.name.sasl_ssl.ssl.client.auth=none
```

## 3. SASL/SCRAM credentials

The documentation says SCRAM should be used only with TLS, hence `SASL_SSL` rather than `SASL_PLAINTEXT`. In KRaft the inter-broker credential must exist before the brokers first start, so create it while formatting storage. Once the cluster is up, give each application its own credential ([authentication.md](authentication.md)) with `kafka-configs.sh`, authenticating as the admin through a properties file like the one in step 5.

```bash
bin/kafka-storage.sh format -t $(bin/kafka-storage.sh random-uuid) -c config/server.properties \
  --add-scram 'SCRAM-SHA-512=[name="admin",password="REPLACE_WITH_LONG_RANDOM_VALUE"]'
# after the brokers are running:
bin/kafka-configs.sh --bootstrap-server kafka.example.com:9093 --command-config admin.properties \
  --alter --add-config 'SCRAM-SHA-512=[password=REPLACE_WITH_LONG_RANDOM_VALUE]' \
  --entity-type users --entity-name app
```

```properties
sasl.enabled.mechanisms=SCRAM-SHA-512
sasl.mechanism.inter.broker.protocol=SCRAM-SHA-512
listener.name.sasl_ssl.scram-sha-512.sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="admin" password="REPLACE_WITH_LONG_RANDOM_VALUE";
```

## 4. Authorization

Without an authorizer every authenticated user can do everything. Enable the KRaft authorizer on every node, keep deny-by-default, and name only the admin as a super user; then grant each principal what it uses (`--producer` and `--consumer` add the matching operation sets).

```properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
allow.everyone.if.no.acl.found=false
super.users=User:admin
```

```bash
bin/kafka-acls.sh --bootstrap-server kafka.example.com:9093 --command-config admin.properties \
  --add --allow-principal User:app --producer --topic orders
bin/kafka-acls.sh --bootstrap-server kafka.example.com:9093 --command-config admin.properties \
  --add --allow-principal User:app --consumer --topic orders --group app-workers
```

## 5. Client side

`client.properties`, kept out of the repository ([secrets.md](secrets.md)). MFA: the Kafka protocol has no second-factor dialogue; `listener.name.sasl_ssl.ssl.client.auth=required` (mutual TLS; the unprefixed `ssl.client.auth` applies only to `SSL` listeners, and Kafka logs a warning when it is set without the prefix on a `SASL_SSL` broker) is the possession factor for machine clients ([machine-auth.md](machine-auth.md)), and each client then presents its own keystore as in the last three lines below; human paths to the brokers or a management UI go behind MFA per [mfa.md](mfa.md).

```properties
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="app" password="REPLACE_WITH_LONG_RANDOM_VALUE";
ssl.truststore.location=/var/private/ssl/client.truststore.jks
ssl.truststore.password=REPLACE_WITH_LONG_RANDOM_VALUE
# only when the listener requires client certificates
ssl.keystore.location=/var/private/ssl/client.keystore.jks
ssl.keystore.password=REPLACE_WITH_LONG_RANDOM_VALUE
ssl.key.password=REPLACE_WITH_LONG_RANDOM_VALUE
```

## 6. Redpanda (and other Kafka-API-compatible systems)

Redpanda implements the Kafka wire protocol, so the client-side and protocol-level controls above carry over: SASL/SCRAM authentication, TLS, and ACL management through the Kafka API all work the same way against a Redpanda cluster, and the same fronting rules apply too. What does not carry over is how you wire that up on the broker: Redpanda configures brokers through `redpanda.yaml` and the `rpk` CLI, not Kafka's `server.properties`, JAAS configuration files, or `kafka-storage.sh`. Redpanda Console, its bundled web UI, ships without its own login screen: it only gains one once you configure OIDC or basic authentication, so until then anyone who reaches Console reaches the cluster behind it. Front Console the same way as any other admin panel: never public, reached through SSH forwarding, a tailnet, or an access proxy, with MFA at that layer. See the [Redpanda security documentation](https://docs.redpanda.com/streaming/current/manage/security/).

## Verify

```bash
ss -tlnp | grep -E '9092|9093'                                # 9093 only, or 9092 on 127.0.0.1
openssl s_client -connect kafka.example.com:9093 </dev/null   # TLS handshake with your certificate
# wrong.properties: a copy of client.properties (security.protocol=SASL_SSL) with a deliberately wrong SCRAM password
bin/kafka-console-consumer.sh --bootstrap-server kafka.example.com:9093 --consumer.config wrong.properties \
  --group app-workers --topic orders --from-beginning --max-messages 1   # must fail with an authentication error (SaslAuthenticationException)
bin/kafka-console-consumer.sh --bootstrap-server kafka.example.com:9093 --consumer.config client.properties \
  --group app-workers --topic orders --from-beginning --max-messages 1   # authorized app credential (group from the ACL in step 4): reads one message
bin/kafka-acls.sh --bootstrap-server kafka.example.com:9093 --command-config admin.properties --list --topic orders
```

## Common mistakes

- `SASL_SSL` added as a second listener while `PLAINTEXT://:9092` stays advertised, so clients quietly keep using it.
- Authorizer enabled with `allow.everyone.if.no.acl.found=true` "temporarily". The flag opens only resources that have no ACL at all; existing ACLs are still enforced. That still means every new topic is world-readable and world-writable until someone adds its first ACL, so keep it `false`.

## Sources (checked September 2026)

- Kafka documentation, Security: https://kafka.apache.org/documentation/#security
- Listener configuration (source): https://raw.githubusercontent.com/apache/kafka/trunk/docs/security/listener-configuration.md
- Encryption and authentication using SSL (source): https://raw.githubusercontent.com/apache/kafka/trunk/docs/security/encryption-and-authentication-using-ssl.md
- Authentication using SASL, SCRAM section (source): https://raw.githubusercontent.com/apache/kafka/trunk/docs/security/authentication-using-sasl.md
- Authorization and ACLs (source): https://raw.githubusercontent.com/apache/kafka/trunk/docs/security/authorization-and-acls.md
- Broker configuration reference (defaults for `listeners`, `sasl.enabled.mechanisms`): https://kafka.apache.org/40/generated/kafka_config.html
- SSL client authentication on `SASL_SSL` listeners needs the listener prefix (source, `ChannelBuilders.java`): https://raw.githubusercontent.com/apache/kafka/trunk/clients/src/main/java/org/apache/kafka/common/network/ChannelBuilders.java
- Redpanda security documentation: https://docs.redpanda.com/streaming/current/manage/security/
