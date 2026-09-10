# Ruby on Rails and Puma: TLS and authentication

Puma's default bind is `tcp://[::]:9292` (or `tcp://0.0.0.0:9292` without IPv6): every interface, plain HTTP. Rails encrypts its session cookie but still sends it in clear unless HTTPS is enforced. Preferred layout: bind Puma to loopback and terminate TLS in a reverse proxy ([nginx.md](nginx.md), [caddy.md](caddy.md), [apache.md](apache.md)) or behind [cloudflare.md](cloudflare.md), with a certificate from [free-certificates.md](free-certificates.md). Puma can also terminate TLS itself, shown below.

## 1. Bind Puma privately

```ruby
# config/puma.rb
bind "tcp://127.0.0.1:3000"
# or: bind "unix:///var/run/puma.sock"
# Puma terminating TLS itself (only when no proxy is in front):
# bind "ssl://0.0.0.0:8443?key=/etc/ssl/private/server.key&cert=/etc/ssl/certs/server.crt"
```

`bind` accepts only `tcp://`, `unix://`, and `ssl://` URIs. The `ssl://` query string also takes `ca=` and `verify_mode=` for client certificates ([machine-auth.md](machine-auth.md)).

## 2. Rails behind the proxy

```ruby
# config/environments/production.rb
config.force_ssl = true      # ActionDispatch::SSL: HTTPS redirect, HSTS per config.ssl_options (default hsts: { subdomains: true })
config.assume_ssl = true     # Rails 7.1+: the proxy terminated TLS and forwards plain HTTP
config.hosts << "app.example.com"   # Host header allowlist (DNS rebinding)
config.session_store :cookie_store, key: "_app_session", secure: true, httponly: true, same_site: :lax, expire_after: 14.days
```

`config.action_dispatch.trusted_proxies` already covers loopback, private, and link-local ranges, so a same-host proxy needs nothing more. A proxy on a public address must be listed as an enumerable, for example `config.action_dispatch.trusted_proxies = [IPAddr.new("203.0.113.10")]`; a single value is not supported. Without any proxy, `X-Forwarded-For` is client-controlled, so do not trust `request.remote_ip` for rate limits or allowlists. `config.action_dispatch.cookies_same_site_protection` defaults to `:lax` from `load_defaults 6.1`.

## 3. Authentication

Follow [authentication.md](authentication.md). Rails specifics:

- Rails 8.0 and later: `bin/rails generate authentication` "Generates a basic authentication system with users, sessions, and password reset", built on `has_secure_password`. Prefer it to hand-rolled login code.
- `has_secure_password` needs `gem "bcrypt", "~> 3.1.7"` and a `password_digest` column; `user.authenticate(password)` returns the user or `false`. It validates presence and the 72-byte bcrypt limit; add your own minimum length.
- Rate-limit login in the controller (needs an `ActiveSupport::Cache` store; defaults to `config.action_controller.cache_store`):

```ruby
class SessionsController < ApplicationController
  rate_limit to: 10, within: 3.minutes, only: :create
end
```

- For path-level throttles and blocklists, [Rack::Attack](https://github.com/rack/rack-attack) (`gem "rack-attack"`, configured in `config/initializers/rack_attack.rb`; its railtie adds the middleware in Rails).
- Secrets live in `config/credentials.yml.enc`, edited with `bin/rails credentials:edit`; the decryption key is `config/master.key` (Rails adds it to `.gitignore`) or `ENV["RAILS_MASTER_KEY"]`, which takes precedence. Set `config.require_master_key = true` so a deployment without the key refuses to boot instead of running half-configured.
- MFA: Rails has no built-in second factor. Add TOTP in the app or front it with an identity layer; options in [mfa.md](mfa.md). OIDC login follows [oidc-integration.md](oidc-integration.md).

## 4. Client-side TLS discipline

```ruby
Net::HTTP.start("api.example.com", 443, use_ssl: true) do |http|   # verify_mode defaults to OpenSSL::SSL::VERIFY_PEER
  http.ca_file = "/etc/ssl/certs/internal-ca.pem"                  # internal CA; or set SSL_CERT_FILE in the environment
  http.request(Net::HTTP::Get.new("/"))
end
```

Never set `verify_mode = OpenSSL::SSL::VERIFY_NONE`. Ruby's default SSL context loads the system store through `set_default_paths`, and OpenSSL reads `SSL_CERT_FILE` and `SSL_CERT_DIR` to locate that store, so an internal CA goes there (see [self-signed.md](self-signed.md)) rather than into a disabled check.

## Verify

```bash
ss -tlnp | grep -E 'puma|ruby'                                   # 127.0.0.1:3000 only
curl -sI http://app.example.com/                                 # 301 to https:// (force_ssl)
curl -sI https://app.example.com/ | grep -iE 'strict-transport|set-cookie'   # HSTS; secure; httponly; samesite=lax
curl -s -o /dev/null -w '%{http_code}\n' https://app.example.com/dashboard    # 302 to login, or 401
git ls-files config/master.key                                   # prints nothing
```

## Sources (checked September 2026)

- Puma README (binding): https://github.com/puma/puma/blob/master/README.md
- Puma DSL (`bind`, `ssl_bind`, default bind): https://github.com/puma/puma/blob/master/lib/puma/dsl.rb
- Puma configuration defaults (`tcp://[::]:9292`): https://github.com/puma/puma/blob/master/lib/puma/configuration.rb
- Rails configuring guide (`force_ssl`, `assume_ssl`, `ssl_options`, `hosts`, `session_store`, `cookies_same_site_protection`, `require_master_key`): https://guides.rubyonrails.org/configuring.html
- Action Pack 7.1 changelog (`ActionDispatch::AssumeSSL`): https://github.com/rails/rails/blob/7-1-stable/actionpack/CHANGELOG.md
- `ActionDispatch::RemoteIp` (trusted proxies, spoofing warning): https://api.rubyonrails.org/classes/ActionDispatch/RemoteIp.html
- `ActionDispatch::Session::CookieStore` options: https://api.rubyonrails.org/classes/ActionDispatch/Session/CookieStore.html
- Rails security guide (authentication generator, `has_secure_password`, `rate_limit`, credentials): https://guides.rubyonrails.org/security.html
- `has_secure_password`: https://api.rubyonrails.org/classes/ActiveModel/SecurePassword/ClassMethods.html
- `ActionController::RateLimiting`: https://api.rubyonrails.org/classes/ActionController/RateLimiting/ClassMethods.html
- `bin/rails credentials:help` text (`master.key`, `RAILS_MASTER_KEY`): https://github.com/rails/rails/blob/main/railties/lib/rails/commands/credentials/USAGE
- Rack::Attack README: https://github.com/rack/rack-attack
- Net::HTTP source (`verify_mode`, `ca_file`, `VERIFY_PEER` default): https://github.com/ruby/net-http/blob/master/lib/net/http.rb
- Ruby OpenSSL `SSLContext` defaults (`DEFAULT_CERT_STORE.set_default_paths`, `VERIFY_PEER`): https://github.com/ruby/openssl/blob/master/lib/openssl/ssl.rb
- OpenSSL environment variables (`SSL_CERT_FILE`, `SSL_CERT_DIR`): https://docs.openssl.org/master/man7/openssl-env/
