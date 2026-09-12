# Memcached: bind privately; authentication and TLS are optional builds

Memcached has no authentication by default, and its `-l` option defaults to `INADDR_ANY`, so a stock start listens on every interface on TCP 11211 and serves any client that connects. The project's own wording: memcached "does not spend much, if any, effort in ensuring its defensibility from random internet connections", so it "must not" be exposed to the internet or to untrusted users. The practical control is network isolation; SASL and TLS exist, but each needs a build compiled with that feature, and SASL alone sends credentials in the clear.

## 1. Bind to loopback or a private interface, UDP off

```bash
memcached -l 127.0.0.1 -p 11211 -U 0
```

`-l` accepts an address or `host:port`; the man page calls it "an important option to consider as there is no other way to secure the installation". `-U 0` keeps UDP disabled (the default since 1.5.6; UDP memcached was the amplifier in large reflection attacks). Put the same flags in your distribution's service configuration, and firewall 11211 per [cloud-firewalls.md](cloud-firewalls.md) or [host.md](host.md). For clients on other hosts, prefer a private network or a tailnet ([tailscale.md](tailscale.md)) over a public listener.

## 2. SASL authentication (binary protocol only)

If the build was configured with `--enable-sasl` (memcached 1.4.3 and later), `-S` turns SASL on. It enables the SASL commands, forces the binary protocol only, and requires a successful authentication before other commands on a connection. Credentials come from the Cyrus SASL password database:

```bash
saslpasswd2 -a memcached -c cacheuser
memcached -l 10.0.0.5 -U 0 -S
```

The documentation requires the password file to be owned by, and readable only by, the user running memcached. It also states that SASL "does not provide encryption, but can provide authentication" and is meant to protect against neighbours and accidents inside a mostly trusted network, not to face the internet. Without TLS (step 3), the credential crosses the network in the clear. The text protocol has a separate token authentication (`-Y` authfile, sent as a fake `set` command with `username password` as the value) with the same limitation.

## 3. TLS (1.5.13 and later, build with `--enable-tls`)

TLS requires a build configured with `--enable-tls` against OpenSSL 1.1.1 or later, and a client library that speaks TLS. It is off by default:

```bash
memcached -l 10.0.0.5 -U 0 -S -Z \
  -o ssl_chain_cert=/etc/memcached/tls/fullchain.pem,ssl_key=/etc/memcached/tls/privkey.pem
```

`-Z` (`--enable-ssl`) turns TLS on; `ssl_chain_cert` and `ssl_key` point at the PEM certificate chain and key ([free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md)). `-o ssl_verify_mode=2` with `-o ssl_ca_cert=/path/ca.pem` requires client certificates (mutual TLS), which is the strongest option memcached offers and the possession factor for machine clients ([machine-auth.md](machine-auth.md)). A `-l notls:127.0.0.1:11211` listener keeps a plaintext socket for local tooling only. `refresh_certs` reloads certificates without a restart, and `stats settings` shows the active `ssl_` values.

MFA: there is no login for a person, so no second factor applies; human access to the host goes behind MFA per [mfa.md](mfa.md).

## Verify

```bash
ss -tlnup | grep 11211                                    # 127.0.0.1 or the private address; no UDP line
printf 'stats\r\nquit\r\n' | nc 127.0.0.1 11211           # works locally
printf 'stats\r\nquit\r\n' | nc cache.example.com 11211   # from outside: connection refused or timeout
openssl s_client -connect 10.0.0.5:11211 -CAfile ca.pem -verify_ip 10.0.0.5 \
  -verify_return_error </dev/null
                                                          # prints Verification: OK when -Z is on. A bare
                                                          # handshake with no CA file shows TLS is enabled,
                                                          # not that the certificate is trusted
                                                          # -verify_ip binds the certificate to this
                                                          # address, so it needs an iPAddress SAN for
                                                          # 10.0.0.5; use -verify_hostname with the
                                                          # name instead where the certificate carries
                                                          # a DNS SAN. Chain checks alone accept any
                                                          # certificate that CA signed
                                                          # This matches the default, which does not require
                                                          # client certificates. With -o ssl_verify_mode=2, add
                                                          # -cert and -key: without them memcached refuses the
                                                          # connection and "Verification: OK" still prints.
```

With `-S`, a plain `stats` over the text protocol is rejected, because the binary protocol is enforced.

## Common mistakes

- A container or package that starts memcached without `-l`, so it listens on `INADDR_ANY` while a firewall rule is assumed but absent.
- `-S` on a distribution package built without SASL: the option is documented as meaningful only with SASL compiled in, so confirm it took effect rather than assuming.
- SASL without TLS across a shared network; the documentation is explicit that SASL adds no encryption.

## Sources (checked September 2026)

- memcached documentation, binary protocol SASL authentication: https://docs.memcached.org/protocols/binarysasl/
- memcached documentation, TLS: https://docs.memcached.org/features/tls/
- memcached documentation, configuring the server (`-l`, `-U`, exposure warning): https://docs.memcached.org/serverguide/configuring/
- memcached man page (`-l` default `INADDR_ANY`, `-U` default 0, `-S`): https://raw.githubusercontent.com/memcached/memcached/master/doc/memcached.1
- memcached protocol reference (`-Y` text protocol authentication): https://raw.githubusercontent.com/memcached/memcached/master/doc/protocol.txt
