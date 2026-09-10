# Go: TLS and authentication with net/http

Preferred production layout: bind the Go server to `127.0.0.1` and terminate TLS in a reverse proxy ([caddy.md](caddy.md), [nginx.md](nginx.md)) or behind [cloudflare.md](cloudflare.md). `net/http` can also terminate TLS itself, shown below. Certificates: [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md).

## 1. HTTPS directly in Go

```go
go http.ListenAndServe(":80", http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {   // port 80 only redirects
    http.Redirect(w, r, "https://"+r.Host+r.URL.RequestURI(), http.StatusMovedPermanently)
}))
srv := &http.Server{
    Addr:              ":443",
    Handler:           mux,
    ReadHeaderTimeout: 10 * time.Second,
    TLSConfig:         &tls.Config{MinVersion: tls.VersionTLS12},
}
log.Fatal(srv.ListenAndServeTLS("/etc/ssl/certs/server.crt", "/etc/ssl/private/server.key"))   // cert file: leaf, then intermediates
```

crypto/tls already defaults to a TLS 1.2 minimum (as of September 2026); setting `MinVersion` keeps that true when a config is copied or a default shifts. Binding ports below 1024 needs root or `CAP_NET_BIND_SERVICE`, one more reason to prefer the proxy layout.

## 2. Behind a proxy

```go
srv := &http.Server{Addr: "127.0.0.1:8080", Handler: mux, ReadHeaderTimeout: 10 * time.Second}
log.Fatal(srv.ListenAndServe())
```

`http.Server` has no trusted-proxy setting: `r.RemoteAddr` is the proxy, and `X-Forwarded-For` and `X-Forwarded-Proto` are ordinary request headers that anyone who can reach the port could set. Read them only when the listener is loopback-only and the proxy overwrites them, and set `Strict-Transport-Security` and the other headers at the proxy per [headers.md](headers.md).

## 3. Authentication

Follow [authentication.md](authentication.md). Password hashing with `golang.org/x/crypto/bcrypt`:

```go
hash, err := bcrypt.GenerateFromPassword([]byte(password), 12)   // DefaultCost is 10; input above 72 bytes is rejected
err = bcrypt.CompareHashAndPassword(hash, []byte(password))     // nil on match
```

`golang.org/x/crypto/argon2` is the alternative: `argon2.IDKey(password, salt, time, memory, threads, keyLen)` returns raw bytes, so you store the random salt and the parameters next to the result. Its documentation carries the RFC 9106 parameter sets (`time=1, memory=2 GiB, threads=4`, or `time=3, memory=64 MiB, threads=4` where memory is short).

Session cookie with the flags set:

```go
http.SetCookie(w, &http.Cookie{
    Name: "session", Value: token, Path: "/",
    Secure: true, HttpOnly: true, SameSite: http.SameSiteLaxMode,
})
```

Rate-limit the login handler with `golang.org/x/time/rate` (one limiter here; key a map of limiters by the proxy-supplied client address for per-client limits):

```go
var loginLimiter = rate.NewLimiter(rate.Every(3*time.Second), 5)   // about 20 per minute, burst 5
if !loginLimiter.Allow() { http.Error(w, "too many requests", http.StatusTooManyRequests); return }
```

API keys and tokens come from the environment, never from literals in the source; generate them per [authentication.md](authentication.md). SSO: `github.com/coreos/go-oidc/v3/oidc` pairs with `golang.org/x/oauth2`; `oidc.NewProvider(ctx, issuer)` discovers the provider and `provider.Verifier(&oidc.Config{ClientID: clientID})` checks ID token signature, issuer, audience, and expiry. The allowlist checks that follow are in [oidc-integration.md](oidc-integration.md). MFA: app-level TOTP with [pquerna/otp](https://github.com/pquerna/otp), or a fronting identity layer; requirements in [mfa.md](mfa.md).

## 4. Client-side TLS discipline

Never set `InsecureSkipVerify: true`; the crypto/tls docs state it accepts any certificate and any host name, which is a machine-in-the-middle position for every connection through that config. For an internal CA, trust the CA instead (see [self-signed.md](self-signed.md) for producing the file): `SSL_CERT_FILE=/path/ca.crt` (or `SSL_CERT_DIR`) overrides the system locations that `x509.SystemCertPool` reads, or add it in code:

```go
pool, err := x509.SystemCertPool()
pem, err := os.ReadFile("/path/ca.crt")
pool.AppendCertsFromPEM(pem)   // returns false if nothing parsed
client := &http.Client{Transport: &http.Transport{TLSClientConfig: &tls.Config{RootCAs: pool}}}
```

## 5. Verify

```bash
curl -sI http://example.com/         # expect 301 with a https:// Location
curl -sI https://example.com/        # succeeds without -k
curl -sS -o /dev/null -w '%{http_code}\n' https://example.com/api   # 401 or 403 without credentials
ss -tlnp | grep REPLACE_WITH_BINARY_NAME   # behind a proxy: 127.0.0.1 only
```

## Sources (checked September 2026)

- net/http (Server, ListenAndServeTLS, Cookie, SameSite, Redirect, Transport.TLSClientConfig): https://pkg.go.dev/net/http
- crypto/tls (Config.MinVersion, InsecureSkipVerify, RootCAs): https://pkg.go.dev/crypto/tls
- crypto/x509 (SystemCertPool, SSL_CERT_FILE, AppendCertsFromPEM): https://pkg.go.dev/crypto/x509
- golang.org/x/crypto/bcrypt: https://pkg.go.dev/golang.org/x/crypto/bcrypt
- golang.org/x/crypto/argon2: https://pkg.go.dev/golang.org/x/crypto/argon2
- golang.org/x/time/rate: https://pkg.go.dev/golang.org/x/time/rate
- go-oidc: https://pkg.go.dev/github.com/coreos/go-oidc/v3/oidc
