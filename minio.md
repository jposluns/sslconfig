# MinIO: root credentials and TLS

MinIO serves S3-compatible object storage; an exposed instance with weak or well-known credentials hands over every bucket. Both the S3 API port and the web console need the same care.

## 1. Set real root credentials

```bash
export MINIO_ROOT_USER="REPLACE_WITH_ADMIN_NAME"
export MINIO_ROOT_PASSWORD="REPLACE_WITH_LONG_RANDOM_VALUE"
```

Never run with the historic `minioadmin`/`minioadmin` pair; scanners try it constantly. Root credentials are for administration only: create per-application access keys with least-privilege policies (via the console or the `mc` client) so no app holds root ([authentication.md](authentication.md)).

## 2. Enable TLS

MinIO serves HTTPS automatically when it finds a PEM key pair named `public.crt` and `private.key` in `${HOME}/.minio/certs` (or the directory given with `--certs-dir`):

```bash
cp fullchain.pem ${HOME}/.minio/certs/public.crt
cp privkey.pem   ${HOME}/.minio/certs/private.key
```

Certificates per [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md); clients then use `https://` endpoints and, for self-signed, trust the CA rather than disabling verification.

## 3. Exposure posture

Loopback or private networks by default; public access only via the TLS endpoints above or behind a proxy/tunnel ([nginx.md](nginx.md), [cloudflare.md](cloudflare.md)). Keep the console off the public internet and give human logins MFA at the fronting layer ([mfa.md](mfa.md)). Buckets are private unless a policy says otherwise; audit anonymous/public bucket policies before exposing anything.

## 4. Verify

```bash
ss -tlnp | grep 9000                                   # private unless deliberate
curl -s https://s3.example.com:9000/                   # answers over TLS; anonymous access denied
mc alias set mys3 https://s3.example.com:9000 <access-key> <secret>   # app key works; root key stays unused by apps
```

## Sources (checked September 2026)

- MinIO network encryption (certs directory, public.crt/private.key, --certs-dir): https://docs.min.io/enterprise/aistor-object-store/installation/linux/network-encryption/
- MinIO: https://min.io/
