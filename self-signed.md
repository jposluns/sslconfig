# Self-signed certificates

Use a self-signed certificate when the service has no public DNS name, when an ACME CA cannot reach it, and when [cloudflare.md](cloudflare.md) is not an option: internal tools, lab and development environments, and machine-to-machine links on private networks. For anything a browser user or external party reaches, prefer [free-certificates.md](free-certificates.md); self-signed certificates trigger browser warnings and every client must be configured to trust them.

Self-signed TLS still matters. It encrypts credentials and data in transit; without it, authentication tokens cross the network in cleartext.

## 1. Generate a certificate with OpenSSL

RSA, single command (OpenSSL 1.1.1 or later for `-addext`):

```bash
openssl req -x509 -newkey rsa:4096 -sha256 -days 365 -nodes \
  -keyout server.key -out server.crt \
  -subj "/CN=app.internal" \
  -addext "subjectAltName=DNS:app.internal,DNS:localhost,IP:127.0.0.1,IP:203.0.113.10"
```

ECDSA (smaller and faster; generate the key first, then the certificate):

```bash
openssl ecparam -name prime256v1 -genkey -noout -out server.key
openssl req -x509 -key server.key -sha256 -days 365 -out server.crt \
  -subj "/CN=app.internal" \
  -addext "subjectAltName=DNS:app.internal,IP:203.0.113.10"
```

Rules that make the certificate actually work:

- The `subjectAltName` list must contain every DNS name and IP address clients will use to reach the service. Modern clients validate SAN entries and ignore the CN.
- `-nodes` leaves the key unencrypted so services can start unattended; protect it with file permissions instead.
- Track the `-days` expiry. Nothing renews a self-signed certificate for you; put the date in your calendar or monitoring.

## 2. Protect the private key

```bash
chmod 600 server.key
chown <service-user> server.key
```

Never commit a private key to version control. Add `*.key` and `*.pem` to `.gitignore` before generating anything inside a repository, and treat any key that has ever been committed or pasted into a chat as compromised: regenerate it.

## 3. mkcert for local development

[mkcert](https://github.com/FiloSottile/mkcert) creates a local CA, installs it into your OS and browser trust stores, and issues certificates that your own machine trusts with no warnings:

```bash
mkcert -install
mkcert app.test localhost 127.0.0.1 ::1
```

This is for development machines only. The generated CA can sign for any name, so its key must never leave the developer's machine, and mkcert certificates must never serve real users.

## 4. Make clients trust the certificate; never disable verification

Distribute the certificate (or your internal CA certificate) to clients instead of turning verification off:

```bash
# Debian/Ubuntu system trust store
sudo cp server.crt /usr/local/share/ca-certificates/app-internal.crt
sudo update-ca-certificates

# RHEL/Fedora system trust store
sudo cp server.crt /etc/pki/ca-trust/source/anchors/app-internal.crt
sudo update-ca-trust

# Per-tool
curl --cacert server.crt https://app.internal/
export REQUESTS_CA_BUNDLE=/path/to/server.crt      # Python requests
export NODE_EXTRA_CA_CERTS=/path/to/server.crt     # Node.js
```

Do not ship `curl -k`, `verify=False`, `rejectUnauthorized: false`, or `NODE_TLS_REJECT_UNAUTHORIZED=0` in committed code. Each of these disables TLS validation entirely, for attacker-controlled certificates as much as for your own, and they reliably survive into production.

## 5. Verify

```bash
openssl x509 -in server.crt -noout -subject -dates -ext subjectAltName
openssl s_client -connect app.internal:443 -CAfile server.crt </dev/null
```

## Limits to plan around

Self-signed certificates have no revocation and no third-party accountability, and trust distribution is manual. When the audience grows beyond a small internal group, move to [free-certificates.md](free-certificates.md) or put the service behind [cloudflare.md](cloudflare.md). Authentication is still required either way: see [authentication.md](authentication.md).

## Sources (checked September 2026)

- OpenSSL documentation: https://www.openssl.org/docs/
- mkcert: https://github.com/FiloSottile/mkcert
