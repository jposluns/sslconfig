# Elasticsearch and OpenSearch: keep security switched on

Open Elasticsearch instances produced some of the largest data leaks on record. Modern versions ship secure; the failure mode today is deliberately switching protection off to make an error message go away.

## Elasticsearch (8.0 and later)

- A fresh install auto-configures security on first start: authentication is enabled, TLS is set up for HTTP and transport, and a password is generated for the `elastic` superuser. Keep all of it.
- Never set `xpack.security.enabled: false`, and never expose a node where TLS (`xpack.security.http.ssl`) has been turned off. If a client cannot connect, fix the client's CA trust ([self-signed.md](self-signed.md)) or issue a real certificate ([free-certificates.md](free-certificates.md)); do not remove the lock.
- Bind stays local unless deliberately widened (`network.host`); remote access goes through the same decision as any database: private network, VPN or tunnel, TLS everywhere.
- Create least-privilege users and API keys per application instead of shipping `elastic` credentials ([authentication.md](authentication.md)).

## OpenSearch

- The security plugin provides authentication and TLS; never run with it disabled, including in Docker examples.
- Recent versions require an initial admin password at install (the `OPENSEARCH_INITIAL_ADMIN_PASSWORD` environment variable for the demo configuration; verify the exact mechanism for your version). Make it long and random.
- The demo configuration installs demo TLS certificates for evaluation; replace them with your own before any real deployment.

## Verify

```bash
curl -s https://search.example.com:9200/            # 401 without credentials
curl -s --cacert /path/http_ca.crt https://search.example.com:9200/ -u elastic
                                                    # prompts, then 200 with the right password. Verify the certificate
                                                    # against the CA your installer generated (Elasticsearch writes
                                                    # http_ca.crt on first start; the OpenSearch demo configuration
                                                    # installs its own) and never pass -k here: -k accepts a substituted
                                                    # certificate exactly as readily as yours, and this line sends
                                                    # credentials over whatever it accepted
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 http://search.example.com:9200/
                                                    # plaintext must NOT answer: expect a connection failure or a
                                                    # protocol error, never cluster JSON
ss -tlnp | grep 9200                                # loopback/private only, unless deliberate
```

An unauthenticated `GET /` returning cluster JSON is the classic finding; so is `_cat/indices` listing your data to the world.

## Sources (checked September 2026)

- Elasticsearch security configuration (current docs home for cluster security): https://www.elastic.co/docs/deploy-manage/security
- OpenSearch demo security configuration: https://docs.opensearch.org/latest/security/configuration/demo-configuration/
- Elasticsearch, automatic TLS setup for self-managed clusters (the generated `http_ca.crt` used to verify TLS from a client): https://www.elastic.co/docs/deploy-manage/security/self-auto-setup
