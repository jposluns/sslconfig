# Spring Boot: TLS and authentication

Preferred production layout: bind the embedded server to `127.0.0.1` and terminate TLS in a reverse proxy ([caddy.md](caddy.md), [nginx.md](nginx.md)) or behind [cloudflare.md](cloudflare.md). Spring Boot can also terminate TLS itself, shown below. Certificates: [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md).

## 1. HTTPS directly in Spring Boot

PEM certificate and key, or a PKCS12 keystore (the PEM properties are in the current Spring Boot how-to; on an older release, confirm your version's reference lists `server.ssl.certificate` before relying on it):

```properties
server.port=8443
server.ssl.certificate=file:/etc/ssl/certs/server.crt
server.ssl.certificate-private-key=file:/etc/ssl/private/server.key
server.ssl.enabled-protocols=TLSv1.2,TLSv1.3
# PKCS12 keystore instead of the two PEM lines:
# server.ssl.key-store=file:/etc/ssl/private/server.p12
# server.ssl.key-store-password=REPLACE_WITH_LONG_RANDOM_VALUE
# server.ssl.key-store-type=PKCS12
```

Spring Boot configures one connector from properties, HTTP or HTTPS, not both; the how-to recommends HTTPS in properties and an HTTP connector added in code if a port 80 redirect is needed. With Spring Security 6.5 or later, `http.redirectToHttps(withDefaults())` in the `SecurityFilterChain` sends requests that arrive over HTTP to HTTPS, and Spring Security writes `Strict-Transport-Security` by default. In the proxy layout, let the proxy do the redirect and skip the second connector.

## 2. Behind a proxy

```properties
server.address=127.0.0.1
server.port=8080
server.forward-headers-strategy=NATIVE
```

`NATIVE` lets the embedded server (Tomcat by default) honour `X-Forwarded-For` and `X-Forwarded-Proto`; `FRAMEWORK` uses Spring's `ForwardedHeaderFilter` instead; the default outside supported cloud platforms is `NONE`. With Tomcat, `server.tomcat.remoteip.internal-proxies` restricts which proxy addresses those headers are accepted from, and `server.tomcat.redirect-context-root=false` keeps redirects on HTTPS when TLS ends at the proxy.

## 3. Authentication

Follow [authentication.md](authentication.md). With `spring-boot-starter-security` on the classpath, every endpoint requires authentication, form login and HTTP Basic are on, CSRF protection and security headers are on, and a single user `user` with a generated password is logged at startup. That user is for development only; `spring.security.user.name` and `spring.security.user.password` replace it for local use, and production needs a real `UserDetailsService` with this encoder:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();   // bcrypt by default, stored as {bcrypt}...
}
```

`BCryptPasswordEncoder(strength)` defaults to strength 10; the docs say to tune it to about 1 second per verification. `Argon2PasswordEncoder.defaultsForSpringSecurity_v5_8()` is the alternative.

Session cookie flags and lifetime:

```properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=30m
```

The Spring Security reference pages checked document no built-in login rate limiter: limit `/login` at the reverse proxy ([nginx.md](nginx.md), [caddy.md](caddy.md)), or count failures and lock the account in your own `UserDetailsService`.

SSO: `spring-boot-starter-oauth2-client` plus properties and `http.oauth2Login(withDefaults())`:

```properties
spring.security.oauth2.client.registration.sso.client-id=REPLACE_WITH_CLIENT_ID
spring.security.oauth2.client.registration.sso.client-secret=${SSO_CLIENT_SECRET}
spring.security.oauth2.client.registration.sso.provider=sso
spring.security.oauth2.client.registration.sso.scope=openid,profile,email
spring.security.oauth2.client.provider.sso.issuer-uri=https://idp.example.com/
```

The `issuer-uri` drives OpenID Connect discovery, and the `openid` scope is what makes the registration an OpenID Connect login that returns an ID token; without it the login is plain OAuth2. Allowlist and token checks are in [oidc-integration.md](oidc-integration.md), providers in [identity-providers.md](identity-providers.md). MFA: enforce it at the identity provider, or front the app per [mfa.md](mfa.md).

## 4. Client-side TLS discipline

- Never install a trust-all `TrustManager` or hostname verifier, and never copy one from an answer that "fixes" a certificate error; it disables validation for the whole JVM client.
- For an internal CA, either import it into the JDK truststore, `keytool -importcert -cacerts -alias internal-ca -file /path/ca.crt` (the `cacerts` password defaults to `changeit`; change it), or declare an SSL bundle, `spring.ssl.bundle.pem.internal.truststore.certificate=file:/path/ca.crt`, and apply it to the client: `restClientBuilder.apply(ssl.fromBundle("internal"))` with an injected `RestClientSsl` (`WebClientSsl` for `WebClient`). See [self-signed.md](self-signed.md).

## 5. Verify

```bash
curl -sI https://example.com/        # succeeds without -k; shows Strict-Transport-Security
curl -sS -o /dev/null -w '%{http_code}\n' https://example.com/api   # 401, or 302 to the login page, without credentials
ss -tlnp | grep java                 # behind a proxy: 127.0.0.1 only
grep -c "Using generated security password" app.log   # must be 0: otherwise the default user is still active
```

## Sources (checked September 2026)

- Spring Boot how-to, embedded web servers (Configure SSL, forward headers, Tomcat proxy settings): https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot SSL bundles: https://docs.spring.io/spring-boot/reference/features/ssl.html ; REST clients (applying a bundle): https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Boot javadoc, Ssl: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/server/Ssl.html ; ServerProperties (address, forwardHeadersStrategy, servlet.session): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/ServerProperties.html
- Spring Boot javadoc, session Cookie: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/server/Cookie.html ; Spring Boot and Spring Security defaults: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Spring Boot OAuth2 client properties: https://docs.spring.io/spring-boot/reference/security/oauth2.html ; Spring Security OAuth2 login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security getting started (Boot defaults): https://docs.spring.io/spring-security/reference/servlet/getting-started.html ; password storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html ; redirect to HTTPS and HSTS: https://docs.spring.io/spring-security/reference/servlet/exploits/http.html
- keytool (importcert, cacerts): https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html
