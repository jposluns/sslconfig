# Self-hosted identity providers: Keycloak and authentik

A self-hosted identity provider is the one service whose compromise is every other service's compromise. [identity-providers.md](identity-providers.md) covers choosing one and says plainly that running your own gives you a server to patch, back up, and keep available. This guide covers what that server exposes once it is running: an administration surface that does not move when you tell it to, a first-boot window in which anyone who reaches the box becomes the administrator, and a management port that answers without asking who you are.

## 1. Bind privately and front it

Neither product should answer the internet on the port it listens on. Put it behind the reverse proxy you already run ([nginx.md](nginx.md), [caddy.md](caddy.md), [traefik.md](traefik.md)) and bind the service itself to loopback or a private address ([host.md](host.md)).

authentik's Docker Compose deployment "listens internally on port 9000 for HTTP and 9443 for HTTPS". Those are the ports to keep off a public interface.

```yaml
# compose.yaml: publish to loopback only, and let the proxy hold the public certificate
services:
  server:
    ports:
      - "127.0.0.1:9000:9000"
```

Keycloak in production requires TLS end to end. Its production guide states that "all communication to and from Keycloak requires a secure communication channel", and "To prevent several attack vectors, you enable HTTP over TLS, or HTTPS, for that channel." Terminating TLS at the proxy satisfies this only if the hop to Keycloak is itself private ([free-certificates.md](free-certificates.md) for the public certificate, [host.md](host.md) for keeping the hop off the network).

## 2. Tell Keycloak its hostname, in production mode

Keycloak runs in one of two profiles and they do not have the same defaults. The hostname guide states that "In production profile (`kc.sh start`), either `--hostname` or `--hostname-strict false` must be explicitly configured", and that "This does not apply for dev profile (`kc.sh|bat start-dev`) where `--hostname-strict false` is the default value."

`hostname-strict` is what stops Keycloak building URLs out of whatever `Host` header a request carries. The vendor's own description: "Disables dynamically resolving the hostname from request headers. Should always be set to true in production, unless your reverse proxy overwrites the Host header."

```bash
kc.sh start \
  --hostname https://id.example.com \
  --hostname-admin https://id-admin.internal:8443 \
  --proxy-headers xforwarded
```

`start-dev` is not a production deployment with a convenient default. It is a different profile whose default is the one you would otherwise have to ask for.

## 3. `hostname-admin` does not restrict the admin API

This is the control the product does not have, and it is the reason this guide exists.

Setting `--hostname-admin` moves the Administration Console to its own hostname. It does not close the old door. Keycloak states it outright:

> Using the `hostname-admin` option does not prevent accessing the Administration REST API endpoints via the frontend URL specified by the `hostname` option. If you want to restrict access to the Administration REST API, you need to do it on the reverse proxy level.

So the separation has to be enforced by you, at the proxy, on the public hostname. Keycloak's reverse proxy guide says the same thing about routing: "Exposed admin paths lead to an unnecessary attack vector", and lists `/admin/` as a path to expose "Only internally".

```nginx
# In the server block for the PUBLIC hostname id.example.com.
# Applications need the realm endpoints. Nobody on the internet needs /admin/.
location /admin/ {
    return 404;
}

location / {
    proxy_pass         http://127.0.0.1:8080;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-For   $remote_addr;   # overwrite, never append
    proxy_set_header   X-Forwarded-Proto $scheme;
}
```

This is a fragment for the public hostname's existing `server` block, not a replacement for it. The admin hostname is a separate `server` block, reached over a tailnet or an SSH forward per [admin-uis.md](admin-uis.md), and `return 404` there would defeat the point.

Overwriting rather than appending matters. Keycloak's reverse proxy guide: "Take extra precautions to ensure that the client address is properly set by your reverse proxy via the `Forwarded` or `X-Forwarded-For` headers. If these headers are incorrectly configured, rogue clients can inject false values and trick Keycloak into thinking the client is connecting from a different IP address than the actual one." An appended header lets a client choose the first value, which is the one most code reads.

Without `--proxy-headers`, requests through a proxy fail rather than fall back: "If you are using a reverse proxy for anything other than TLS passthrough and do not set the `proxy-headers` option, then by default you will see 403 Forbidden responses to requests via the proxy that perform origin checking."

## 4. The first-boot window

authentik's Compose install has no administrator until someone creates one. The install guide's instruction is "To start the initial setup, navigate to `http://<your server's IP or hostname>:9000`", after which "You are then prompted to set a password for the `akadmin` user (the default user)."

Nothing in that sequence asks who you are. If the host is reachable from the internet between `docker compose up` and the moment you finish that form, the administrator is whoever loads the page first. Complete the setup over loopback or a private address before the service is routable, as [deployment-lifecycle.md](deployment-lifecycle.md) describes for any service that is published before it is protected.

Keycloak's equivalent is a credential rather than a window, and it is meant to be thrown away. Its bootstrap admin documentation states that an account created this way "is **temporary**", that "the account should exist only for the duration necessary to perform operations needed to gain permanent and more secure admin access", and that afterwards "the account needs to be removed manually". Manually means it does not expire on its own. Create a real administrator, enrol MFA on it per [mfa.md](mfa.md), then delete the bootstrap account and treat its password as a secret that was on a command line ([secrets.md](secrets.md)).

## 5. The management port

Keycloak serves health and metrics on a second port. Its management interface documentation states that "Management endpoints such as `/metrics` and `/health` are exposed on the default management port `9000`", and that "Exposing health and metrics endpoints on the default server is not recommended for security reasons, and you should always use the management interface".

The page describes network isolation as the control. It does not describe authentication on that port, so treat 9000 as reachable by anyone who can route to it and keep it on a private interface. Your orchestrator needs `/health/ready`; the internet does not.

authentik splits it the same way, on a different number. Its monitoring documentation states that "Both the core authentik server, worker and any outposts expose Prometheus metrics on a separate port (9300)", and that "The metrics require no authentication, as they are hosted on a separate, non-exposed port by default." Non-exposed by default is a property of the shipped Compose file, not of the port, so publishing 9300 to a public interface publishes unauthenticated metrics.

## 6. MFA on the administrator, first

Every application behind this provider inherits its authentication, which means it inherits the administrator's authentication too. Enrol a phishing-resistant factor on the administrator account before you connect the first application, not after. Both products support TOTP and WebAuthn; [mfa.md](mfa.md) covers the enrolment and the reason to require a hardware key or passkey for administrators specifically.

## Verify

```bash
# Steps 2 to 5 must run from a host OUTSIDE every network you have allowed, against a
# system you are authorized to test. Clear the proxy variables first: curl honours them,
# and a proxy whose egress sits inside an allowed range turns a blocked endpoint into a
# 200 while you are sitting somewhere that should have been refused.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy

# 1. On the host itself: nothing listens on a public address. Keycloak serves 8080 or
#    8443 and management 9000; authentik serves 9000 and 9443, and metrics on 9300.
ss -tlnp | grep -E ':(8080|8443|9000|9443|9300)\b'    # 127.0.0.1 or an RFC 1918 address only

# 2. POSITIVE CONTROL, and the reason every check below means anything: the public
#    hostname answers from out here. If this fails, the rest of the steps "pass" for the
#    wrong reason, because nothing you send is arriving at all.
curl -sS -o /dev/null -w '%{http_code}\n' \
  https://id.example.com/realms/master/.well-known/openid-configuration
# 200 expected. Applications need this endpoint, so the proxy rule must not break it.

# 3. The administration console is closed on the PUBLIC hostname.
curl -sS -o /dev/null -w '%{http_code}\n' https://id.example.com/admin/master/console/
# 404 is the pass. A 302 to a login page is NOT a pass: it means the console answered
# and is offering to authenticate you. Any 2xx, any 3xx, 401 or 403 all mean the path
# was served by something.

# 4. The administration REST API is closed on that same hostname. hostname-admin does
#    not do this for you, so this is the step that proves your proxy rule does.
curl -sS -o /dev/null -w '%{http_code}\n' https://id.example.com/admin/realms/master/users
# 404 is the pass. 401 means the API answered and asked for a token.

# 5. The management and metrics ports are not routable from out here. Step 2 already
#    proved this host can reach that name, so a timeout here is about the port.
for p in 9000 9300; do
  curl -sS -m 5 -o /dev/null "http://id.example.com:$p/" 2>/dev/null
  echo "$p: curl exit $?"   # 7 (refused) or 28 (timed out) is the pass; 0 means it answered
done

# 6. Keycloak's bootstrap admin is gone. It does not expire on its own, so this is
#    something you look at rather than something a command proves. On the admin
#    hostname, open Users in the master realm, or from an authenticated kcadm session:
#    kcadm.sh get users -r master --fields username
```

One name is not one address. Step 2 through step 5 test whatever `id.example.com` resolves to first, so repeat them against every public address the name carries and against both address families, not just the one your resolver happened to return. A provider that answers on IPv6 while IPv4 is filtered passes all five checks and is still reachable.

## Sources (checked September 2026)

- Keycloak production configuration, including the TLS requirement and separating the admin REST API and console: https://www.keycloak.org/server/configuration-production
- Keycloak hostname options, including the production and dev profile defaults for `hostname-strict`, and the statement that `hostname-admin` does not restrict the Administration REST API: https://www.keycloak.org/server/hostname
- Keycloak reverse proxy configuration, including `proxy-headers`, the forwarded-header warning, and the exposed-paths table: https://www.keycloak.org/server/reverseproxy
- Keycloak bootstrap and recovery admin accounts, including that the account is temporary and must be removed manually: https://www.keycloak.org/server/bootstrap-admin-recovery
- Keycloak management interface and the default management port 9000: https://www.keycloak.org/server/management-interface
- authentik Docker Compose installation, including the default ports and the initial setup flow that sets the `akadmin` password: https://docs.goauthentik.io/install-config/install/docker-compose/
- authentik monitoring, including the separate metrics port 9300 and that the metrics carry no authentication: https://docs.goauthentik.io/sys-mgmt/ops/monitoring
