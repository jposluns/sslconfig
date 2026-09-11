# PHP and Laravel: TLS and authentication

PHP normally runs behind a web server (Apache with php-fpm or mod_php, nginx or Caddy with php-fpm), so TLS terminates there: follow [apache.md](apache.md), [nginx.md](nginx.md), or [caddy.md](caddy.md) with a certificate from [free-certificates.md](free-certificates.md). The PHP-specific exposures are the php-fpm FastCGI socket (the PHP manual: "An exposed FastCGI endpoint allows arbitrary code execution"), session cookies that PHP ships without `Secure`, `HttpOnly`, or `SameSite` (all three default off), `APP_DEBUG=true` left on in production, and cURL calls with certificate checks turned off.

## 1. Keep php-fpm private

`listen` is mandatory per pool. Prefer a Unix socket when the web server is on the same host; with TCP, list the allowed clients, because `listen.allowed_clients` is unset by default and then accepts any address. In containers, never publish the FPM port on the host.

```ini
; /etc/php/*/fpm/pool.d/www.conf
listen = /run/php/php-fpm.sock        ; access controlled by listen.owner, listen.group, listen.mode (default 0660)
; listen = 127.0.0.1:9000 plus listen.allowed_clients = 127.0.0.1 for the TCP alternative, loopback only
```

## 2. Plain PHP: sessions, passwords, rate limiting

```ini
session.cookie_secure = 1        ; default 0
session.cookie_httponly = 1      ; default 0
session.cookie_samesite = Lax    ; default "" (no attribute); Lax or Strict
session.use_strict_mode = 1      ; default 0; the manual calls enabling it "mandatory for general session security"
```

Call `session_regenerate_id()` after login and on privilege change. Its `delete_old_session` parameter defaults to `false`; the manual advises against destroying the old session immediately (unstable networks, hijack detection), so expire it with a timestamp instead.

Hash with `password_hash($password, PASSWORD_DEFAULT)` (bcrypt at the time of writing; `PASSWORD_ARGON2ID` needs PHP built with Argon2), check with `password_verify()`, and upgrade old hashes when `password_needs_rehash()` says so. `PASSWORD_DEFAULT` is designed to change over time, so store the hash in a column that can grow past 60 bytes (the manual suggests 255). Plain PHP has no login rate limiter; apply one at the proxy or with fail2ban per [authentication.md](authentication.md). MFA in plain PHP means a TOTP library or an identity layer in front, per [mfa.md](mfa.md).

## 3. Laravel

```ini
APP_ENV=production              # .env stays out of source control
APP_DEBUG=false                 # true in production exposes configuration values to end users
APP_URL=https://app.example.com
APP_KEY=                        # php artisan key:generate; list old keys in APP_PREVIOUS_KEYS when rotating
SESSION_SECURE_COOKIE=true      # config/session.php 'secure' has no default
SESSION_HTTP_ONLY=true          # default true
SESSION_SAME_SITE=lax           # default lax; strict for admin-only apps
```

Behind a proxy, name it in `bootstrap/app.php` (Laravel 12.x docs; check the docs for your version) so `url()`, `request()->secure()`, and secure cookies see HTTPS:

```php
->withMiddleware(function (Middleware $middleware): void {
    $middleware->trustProxies(at: ['127.0.0.1', '10.0.0.0/8']);   // '*' only when the app is unreachable except through the proxy
})
```

Force HTTPS in generated URLs with `URL::forceHttps()` (or `URL::forceScheme('https')`) in a service provider's `boot()` method. Passwords: `Hash::make()` and `Hash::check()` use bcrypt by default; `HASH_DRIVER=argon2id` switches the driver, `Hash::needsRehash()` upgrades old hashes, and `Hash::check()` rejects hashes made with a different algorithm unless `HASH_VERIFY=false`. Rate-limit the login route in `AppServiceProvider::boot()` and attach it with the `throttle` middleware:

```php
RateLimiter::for('login', fn (Request $request) => Limit::perMinute(5)->by($request->email.$request->ip()));
Route::post('/login', ...)->middleware('throttle:login');
```

The 12.x starter kits (React, Vue, Svelte, Livewire) authenticate through Laravel Fortify, which throttles login by username plus IP, regenerates the session ID on login, and ships TOTP two-factor authentication with recovery codes: `Features::twoFactorAuthentication(['confirm' => true, 'confirmPassword' => true])` in `config/fortify.php`. Fortify alone (`composer require laravel/fortify`, `php artisan fortify:install`) gives the same backend without views. Laravel Socialite handles OAuth login for Google, GitHub, GitLab, Slack, and others; OpenID Connect providers come through the community Socialite Providers packages. After the callback, apply the allowlist and token checks in [oidc-integration.md](oidc-integration.md), and keep the `redirect` in `config/services.php` on `https://`.

## 4. Client-side TLS discipline

```php
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);                     // the default; never set false
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 2);                        // the default; keep 2 in production
curl_setopt($ch, CURLOPT_CAINFO, '/etc/ssl/certs/internal-ca.pem'); // internal CA instead of disabling checks
```

## Verify

```bash
ss -xlnp | grep php-fpm                                       # Unix socket; with TCP, ss -tlnp shows 127.0.0.1:9000 only
curl -sI https://app.example.com/                             # succeeds without -k
curl -sI https://app.example.com/login | grep -i set-cookie   # secure; httponly; samesite=lax
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/REPLACE_WITH_PROTECTED_PATH
                                                              # 401, 403, or a redirect to /login with no session cookie.
                                                              # TLS and cookie flags say nothing about whether a route
                                                              # actually refuses an unauthenticated request
```

## Sources (checked September 2026)

- PHP FPM configuration (`listen`, `listen.allowed_clients`, `listen.owner`): https://www.php.net/manual/en/install.fpm.configuration.php
- PHP session runtime configuration: https://www.php.net/manual/en/session.configuration.php
- PHP `session_regenerate_id()`: https://www.php.net/manual/en/function.session-regenerate-id.php
- PHP `password_hash()`: https://www.php.net/manual/en/function.password-hash.php
- PHP cURL constants (`CURLOPT_SSL_VERIFYPEER`, `CURLOPT_SSL_VERIFYHOST`, `CURLOPT_CAINFO`): https://www.php.net/manual/en/curl.constants.php
- Laravel 12.x encryption (`APP_KEY`, `key:generate`, `APP_PREVIOUS_KEYS`): https://laravel.com/docs/12.x/encryption
- Laravel 12.x requests (trusted proxies, trusted hosts): https://laravel.com/docs/12.x/requests
- Laravel 12.x `config/session.php` defaults: https://github.com/laravel/laravel/blob/12.x/config/session.php
- Laravel 12.x `UrlGenerator::forceHttps()` and `forceScheme()`: https://api.laravel.com/docs/12.x/Illuminate/Routing/UrlGenerator.html
- Laravel 12.x hashing: https://laravel.com/docs/12.x/hashing
- Laravel 12.x routing (rate limiting): https://laravel.com/docs/12.x/routing
- Laravel 12.x starter kits (Fortify, two-factor, rate limiting): https://laravel.com/docs/12.x/starter-kits
- Laravel 12.x Fortify: https://laravel.com/docs/12.x/fortify
- Laravel 12.x Socialite: https://laravel.com/docs/12.x/socialite
- Laravel 12.x deployment (nginx example, `APP_DEBUG`): https://laravel.com/docs/12.x/deployment
