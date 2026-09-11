# Self-hosted tunnels: frp and WireGuard

Both expose a private host to the internet without a public IP, the same job [cloudflare.md](cloudflare.md) and [tailscale.md](tailscale.md) do, but with no vendor edge: you run and secure both ends yourself, on a host still hardened per [host.md](host.md). frp with a weak or absent token lets anyone bind proxies through your server; WireGuard has no login at all, only key pairs and the traffic scoping you configure.

## frp

`frps` (the server) listens for client connections on `bindPort`, default `7000`. Authentication is token-based by default: set the identical `auth.token` in `frps.toml` and every `frpc.toml`, since "client needs to set the same value to pass authentication":

```toml
# frps.toml
bindPort = 7000
auth.token = "REPLACE_WITH_LONG_RANDOM_VALUE"
```

```toml
# frpc.toml
serverAddr = "203.0.113.10"
serverPort = 7000
auth.token = "REPLACE_WITH_LONG_RANDOM_VALUE"
```

frp also supports `auth.method = "oidc"`, authenticating both sides against an OIDC provider's Client Credentials Grant instead of a shared token, useful for centralizing frp auth behind an identity provider.

Enable TLS between `frpc` and `frps` and set `tls.force = true` on the server so it only accepts TLS-enabled client connections; without it, the token and all tunneled traffic cross the network in the clear.

The `auth` block is schema-optional, and the frp documentation does not state what a server does when it is left out entirely. Treat an unconfigured token as an open door rather than assuming a safe default: always set `auth.token` (or OIDC) before exposing `bindPort` to the internet, and never rely on frp for anything without one.

## WireGuard

WireGuard has no username or password; identity is a base64-encoded key pair, generated per peer:

```bash
wg genkey | tee privatekey | wg pubkey > publickey
```

The private key never leaves the peer that generated it; only the public key goes into the other side's configuration. A peer is added to an interface with its public key, an endpoint, and `AllowedIPs`:

```bash
wg set wg0 listen-port 51820 private-key /path/to/private-key peer "REPLACE_WITH_PEER_PUBLIC_KEY" allowed-ips 192.168.88.0/24 endpoint 203.0.113.10:51820
```

`AllowedIPs` is dual-purpose "Cryptokey Routing": on the sending side it "behaves as a sort of routing table," picking which peer a destination IP goes to; on the receiving side it "behaves as a sort of access control list," dropping a decrypted packet whose source IP does not match that peer's `AllowedIPs`. Scope it to exactly the address or subnet a peer should reach or be reached from, never `0.0.0.0/0` unless that peer is genuinely meant to be a full-tunnel gateway.

By default WireGuard "tries to be as silent as possible when not being used," so the only inbound port a firewall needs to open is the single WireGuard UDP `ListenPort`; everything else on the host stays closed per [host.md](host.md).

## Verify

```bash
# frp: a client with the wrong token is rejected, not connected
frpc -c frpc-wrongtoken.toml   # expect an authentication failure, no proxy registered

ss -ulnp | grep 51820          # WireGuard: only the one UDP port listening
sudo ufw status verbose        # no other inbound rule added for the tunneled service
ping -c1 203.0.113.20   # from that peer, an address outside its AllowedIPs: unreachable
```

## Sources (checked September 2026)

- frp documentation (setup, server reference): https://gofrp.org/en/docs/
- frp server configuration reference (`bindPort`, `auth.token`, `tls.force`): https://gofrp.org/en/docs/reference/server-configures/
- frp authentication (`auth.token`, `auth.method = "oidc"`): https://gofrp.org/en/docs/features/common/authentication/
- WireGuard quickstart (`wg genkey`, `wg pubkey`, `wg set`, silent-protocol behavior): https://www.wireguard.com/quickstart/
- WireGuard Cryptokey Routing (`AllowedIPs` on send and receive): https://www.wireguard.com/
