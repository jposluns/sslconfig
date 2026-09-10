# ASP.NET Core and Kestrel: TLS and authentication

Preferred production layout: bind Kestrel to loopback and terminate TLS in a reverse proxy ([caddy.md](caddy.md), [nginx.md](nginx.md)) or behind [cloudflare.md](cloudflare.md). Kestrel can also terminate TLS itself, shown below. Certificates: [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md).

## 1. HTTPS directly in Kestrel

`appsettings.json` with a PKCS12 file (for PEM files, `Path` is the certificate and `KeyPath` the private key; the docs warn against a plaintext `Password` here, so supply it from the environment or a secret store):

```json
{ "Kestrel": { "Endpoints": {
    "Http":  { "Url": "http://*:80" },
    "Https": { "Url": "https://*:443",
               "Certificate": { "Path": "/etc/ssl/private/server.pfx", "Password": "REPLACE_WITH_LONG_RANDOM_VALUE" } }
} } }
```

```csharp
builder.WebHost.ConfigureKestrel(serverOptions =>
    serverOptions.ConfigureHttpsDefaults(listenOptions =>
        listenOptions.SslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13));   // default SslProtocols.None = OS defaults
builder.Services.AddHsts(options => { options.MaxAge = TimeSpan.FromDays(365); options.IncludeSubDomains = true; });
if (!app.Environment.IsDevelopment()) { app.UseHsts(); }   // browsers cache HSTS; keep it out of development
app.UseHttpsRedirection();                                  // needs the HTTPS port: ASPNETCORE_HTTPS_PORT=443 or options.HttpsPort
```

## 2. Behind a proxy

```csharp
builder.WebHost.ConfigureKestrel(o => o.ListenLocalhost(5000));   // or ASPNETCORE_URLS=http://localhost:5000
builder.Services.Configure<ForwardedHeadersOptions>(o => {
    o.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    o.KnownProxies.Add(IPAddress.Parse("127.0.0.1")); });   // only listed proxies are trusted
app.UseForwardedHeaders();   // first in the pipeline
```

When the proxy already redirects to HTTPS and sends HSTS, leave `UseHttpsRedirection` and `UseHsts` out of the app; per the docs, redirect middleware behind a proxy without forwarded headers loops. Set the remaining security headers at the proxy per [headers.md](headers.md).

## 3. Authentication

Follow [authentication.md](authentication.md). ASP.NET Core Identity hashes passwords with PBKDF2 (`PasswordHasherOptions.IterationCount`, default 100,000); keep its hasher rather than writing one. Lockout and cookie settings:

```csharp
builder.Services.AddDefaultIdentity<IdentityUser>(options => {
    options.Lockout.MaxFailedAccessAttempts = 5;
    options.Lockout.DefaultLockoutTimeSpan = TimeSpan.FromMinutes(5);
    options.Lockout.AllowedForNewUsers = true; }).AddEntityFrameworkStores<ApplicationDbContext>();
builder.Services.ConfigureApplicationCookie(options => {
    options.Cookie.HttpOnly = true;
    options.Cookie.SecurePolicy = CookieSecurePolicy.Always;
    options.Cookie.SameSite = SameSiteMode.Lax;   // Strict breaks OAuth2 and OIDC callbacks
    options.ExpireTimeSpan = TimeSpan.FromHours(8); });
```

Without Identity, the same `Cookie.*` options go on `AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie(options => ...)`; call `app.UseAuthentication()` then `app.UseAuthorization()` before the `Map*` calls. Deny by default with `AddAuthorizationBuilder().SetFallbackPolicy(new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build())` and mark public pages `[AllowAnonymous]`.

Rate-limit the login route with the built-in middleware (`Microsoft.AspNetCore.RateLimiting`, .NET 7 and later):

```csharp
builder.Services.AddRateLimiter(options => {
    options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
    options.AddFixedWindowLimiter("login", o => { o.PermitLimit = 20; o.Window = TimeSpan.FromMinutes(15); o.QueueLimit = 0; }); });
app.UseRateLimiter();   // after UseRouting when policies are per endpoint
app.MapPost("/login", LoginHandler).RequireRateLimiting("login");
```

SSO: the `Microsoft.AspNetCore.Authentication.OpenIdConnect` package adds `.AddOpenIdConnect(options => { options.Authority = ...; options.ClientId = ...; options.ClientSecret = ...; options.ResponseType = OpenIdConnectResponseType.Code; })` next to `.AddCookie()`, with the cookie as `DefaultScheme` and OIDC as `DefaultChallengeScheme`; keep the secret out of `appsettings.json`. Validation and allowlist checks are in [oidc-integration.md](oidc-integration.md), providers in [identity-providers.md](identity-providers.md). MFA: enforce it at the identity provider, or front the app per [mfa.md](mfa.md).

## 4. Client-side TLS discipline

- Never assign `HttpClientHandler.DangerousAcceptAnyServerCertificateValidator` or a `ServerCertificateCustomValidationCallback` that returns `true`; both accept any certificate for every request through that handler.
- On Linux, .NET reads trusted roots through OpenSSL, so an internal CA is trusted by adding it to the distribution's CA bundle or by pointing `SSL_CERT_FILE` (or `SSL_CERT_DIR`) at a PEM file that starts with `BEGIN CERTIFICATE` (see [self-signed.md](self-signed.md)).

## 5. Verify

```bash
curl -sI http://example.com/         # expect 307 or 308 with a https:// Location
curl -sI https://example.com/        # succeeds without -k; shows Strict-Transport-Security
curl -s  https://example.com/api     # expect 401/403 without credentials
ss -tlnp | grep dotnet               # behind a proxy: 127.0.0.1 and ::1 only
```

## Sources (checked September 2026)

- Enforce HTTPS (UseHttpsRedirection, UseHsts, HttpsPort): https://learn.microsoft.com/en-us/aspnet/core/security/enforcing-ssl ; Kestrel endpoints (certificate config, ListenLocalhost, SslProtocols): https://learn.microsoft.com/en-us/aspnet/core/fundamentals/servers/kestrel/endpoints ; proxy servers (ForwardedHeadersOptions, KnownProxies): https://learn.microsoft.com/en-us/aspnet/core/host-and-deploy/proxy-load-balancer
- Introduction to Identity (lockout, ConfigureApplicationCookie): https://learn.microsoft.com/en-us/aspnet/core/security/authentication/identity ; PasswordHasherOptions: https://learn.microsoft.com/en-us/dotnet/api/microsoft.aspnetcore.identity.passwordhasheroptions
- Cookie authentication without Identity: https://learn.microsoft.com/en-us/aspnet/core/security/authentication/cookie ; CookieSecurePolicy: https://learn.microsoft.com/en-us/dotnet/api/microsoft.aspnetcore.http.cookiesecurepolicy
- Rate limiting middleware: https://learn.microsoft.com/en-us/aspnet/core/performance/rate-limit ; OpenID Connect web authentication: https://learn.microsoft.com/en-us/aspnet/core/security/authentication/configure-oidc-web-authentication
- DangerousAcceptAnyServerCertificateValidator: https://learn.microsoft.com/en-us/dotnet/api/system.net.http.httpclienthandler.dangerousacceptanyservercertificatevalidator ; trusted roots on Linux: https://learn.microsoft.com/en-us/dotnet/standard/security/cross-platform-cryptography
