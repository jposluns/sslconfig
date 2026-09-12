# Self-hosted identity providers: Keycloak and authentik

A self-hosted identity provider is the one service whose compromise is every other service's compromise. [identity-providers.md](identity-providers.md) covers choosing one and says plainly that running your own gives you a server to patch, back up, and keep available. This guide covers what that server exposes once it is running: an administration surface that does not move when you tell it to, a first-boot window in which anyone who reaches the box becomes the administrator, and a management port that, once you turn it on, answers without asking who you are.

## 1. Bind privately and front it

Neither product should answer the internet on the port it listens on. Put it behind the reverse proxy you already run ([nginx.md](nginx.md), [caddy.md](caddy.md), [traefik.md](traefik.md)) and bind the service itself to loopback or a private address ([host.md](host.md)).

authentik's Docker Compose deployment "listens internally on port 9000 for HTTP and 9443 for HTTPS". Those are the ports to keep off a public interface.

```yaml
# compose.yaml: REPLACE the existing ports list, do not add to it. Compose merges ports by
# address, target, published port and protocol, so a new mapping leaves an old one in place.
# The shipped file publishes BOTH 9000 and 9443 on every interface. Both lines have to go.
services:
  server:
    ports:
      - "127.0.0.1:9000:9000"
      - "127.0.0.1:9443:9443"
```

Keycloak in production requires a secure channel. Its production guide states that "all communication to and from Keycloak requires a secure communication channel", and "To prevent several attack vectors, you enable HTTP over TLS, or HTTPS, for that channel." Terminating TLS at the proxy is edge termination, not end-to-end encryption, and it is only acceptable where the hop from proxy to Keycloak cannot be observed: a loopback interface, or a private network segment you control ([free-certificates.md](free-certificates.md) for the public certificate, [host.md](host.md) for the host itself). Both products also keep everything they know in a database, which is inside this boundary and not outside it ([postgresql.md](postgresql.md)).

## 2. Tell Keycloak its hostname, in production mode

Keycloak runs in one of two profiles and they do not have the same defaults. The hostname guide states that "In production profile (`kc.sh|bat start`), either `--hostname` or `--hostname-strict false` must be explicitly configured", and that "This does not apply for dev profile (`kc.sh|bat start-dev`) where `--hostname-strict false` is the default value."

`hostname-strict` is what stops Keycloak building URLs out of whatever `Host` header a request carries. The vendor's own description: "Disables dynamically resolving the hostname from request headers. Should always be set to true in production, unless your reverse proxy overwrites the Host header."

```bash
kc.sh start \
  --hostname https://id.example.com \
  --hostname-admin https://id-admin.internal:8443 \
  --proxy-headers xforwarded \
  --http-enabled=true          # 8080 exists only when you ask for it. Only do this where
                               # the hop from the proxy is loopback or a private segment
```

`start-dev` is not a production deployment with a convenient default. It is a different profile whose default is the one you would otherwise have to ask for.

## 3. `hostname-admin` does not restrict the admin API

This is the control the product does not have, and it is the reason this guide exists.

Setting `--hostname-admin` moves the Administration Console to its own hostname. It does not close the old door. Keycloak states it outright:

> Using the `hostname-admin` option does not prevent accessing the Administration REST API endpoints via the frontend URL specified by the `hostname` option. If you want to restrict access to the Administration REST API, you need to do it on the reverse proxy level.

So the separation has to be enforced by you, at the proxy, on the public hostname. Keycloak's reverse proxy guide says the same thing about routing: "Exposed admin paths lead to an unnecessary attack vector", and lists `/admin/` as a path to expose "Only internally". The same table marks `/realms/master/` as "Only internally" and `/realms/` as exposed, which is why the rule above closes the administrative realm and not the realms your applications use.

```nginx
# In the server block for the PUBLIC hostname id.example.com.
# Applications need the realm endpoints. Nobody on the internet needs /admin/.
location /admin/ {
    return 404;
}

# The Admin Console AUTHENTICATES against this hostname even when hostname-admin moves its
# API calls elsewhere: Keycloak builds the console's auth URL from the FRONTEND base URL. So
# a blanket 404 here locks every administrator out. Restrict by SOURCE instead, which is what
# Keycloak asks for: "restrict access to the authentication protocol endpoints of the
# administrative realm from public IP addresses."
location /realms/master/ {
    allow 203.0.113.0/24;          # where your administrators connect from
    deny  all;

    proxy_pass         http://127.0.0.1:8080;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-For   $remote_addr;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_set_header   X-Forwarded-Host  $host;
    proxy_set_header   X-Forwarded-Port  $server_port;
    proxy_set_header   X-Forwarded-Prefix "";
}

location / {
    proxy_pass         http://127.0.0.1:8080;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-For   $remote_addr;   # overwrite, never append
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_set_header   X-Forwarded-Host  $host;
    proxy_set_header   X-Forwarded-Port  $server_port;
    proxy_set_header   X-Forwarded-Prefix "";
}
```

This is a fragment for the public hostname's existing `server` block, not a replacement for it. Two different things happen on two different hostnames and it is worth being precise about which. The console's API calls go to the admin hostname, because Keycloak states that the "Administration Console implicitly accesses the API using the URL as specified by the `hostname-admin` option". Its LOGIN does not: Keycloak builds the console's authentication URL from the frontend base URL, so the browser is sent to `id.example.com/realms/master/` to authenticate no matter where the console itself is served. That is why the rule above restricts that path by source address rather than refusing it, and why an earlier version of this guide that refused it outright would have locked out every administrator including the one who applied it. A denied source gets a 403 from nginx rather than a 404, which is what step 5 of the Verify section looks for; if you see a 404 there, the path is being refused outright rather than restricted, and your administrators are locked out along with everyone else.

The admin hostname is a separate `server` block on `id-admin.internal`, reached over a tailnet or an SSH forward per [admin-uis.md](admin-uis.md), and it must proxy `/admin/`, `/resources/` and `/.well-known/`. Add `/js/` as well if you run a version whose console still loads its adapter from there. Step 6 of the Verify section is the test, and it is the only step that checks something still WORKS rather than something is closed.

Overwriting rather than appending matters. Keycloak's reverse proxy guide: "Take extra precautions to ensure that the client address is properly set by your reverse proxy via the `Forwarded` or `X-Forwarded-For` headers. If these headers are incorrectly configured, rogue clients can inject false values and trick Keycloak into thinking the client is connecting from a different IP address than the actual one." An appended header lets a client choose the first value, which is the one most code reads.

Overwrite all five, not the two you were thinking of. `--proxy-headers xforwarded` parses "`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Forwarded-Port`, and `X-Forwarded-Prefix`", and nginx passes through any request header you do not set, so the three you leave alone arrive exactly as the client sent them. Keycloak also offers `--proxy-trusted-addresses`, which accepts forwarded headers only from the proxy's own addresses, and is honest about what that is worth: "this is only weak protection because IP addresses can be spoofed." It is worth setting and it is not a substitute for overwriting the headers.

Without `--proxy-headers`, requests through a proxy fail rather than fall back: "If you are using a reverse proxy for anything other than TLS passthrough and do not set the `proxy-headers` option, then by default you will see 403 Forbidden responses to requests via the proxy that perform origin checking."

## 4. The first-boot window

authentik's Compose install has no administrator until someone creates one. The install guide's instruction is "To start the initial setup, navigate to `http://<your server's IP or hostname>:9000`", after which "You are then prompted to set a password for the `akadmin` user (the default user)."

Nothing in that sequence asks who you are. If the host is reachable from the internet between `docker compose up` and the moment you finish that form, the administrator is whoever loads the page first. Complete the setup over loopback or a private address before the service is routable, as [deployment-lifecycle.md](deployment-lifecycle.md) describes for any service that is published before it is protected.

Keycloak's equivalent is a credential rather than a window, and it is meant to be thrown away. Its bootstrap admin documentation states that an account created this way "is **temporary**", that "the account should exist only for the duration necessary to perform operations needed to gain permanent and more secure admin access", and that afterwards "the account needs to be removed manually". Manually means it does not expire on its own. Create a real administrator, enrol MFA on it per [mfa.md](mfa.md), then delete the bootstrap account and treat its password as a secret that was on a command line ([secrets.md](secrets.md)).

## 5. The management port

Keycloak serves health and metrics on a second port. Its management interface documentation states that "Management endpoints such as `/metrics` and `/health` are exposed on the default management port `9000` when metrics and health are enabled", and that "Exposing health and metrics endpoints on the default server is not recommended for security reasons, and you should always use the management interface".

The page does document a control: `https-management-client-auth` "Configures the management interface to require/request client authentication", taking `none`, `request` or `required`, and inheriting from the HTTP options when it is not given. Inheriting is the problem, because nothing in this guide's topology sets client authentication on the HTTP options either, so the effective answer is usually `none`. Setting it to `required` is not a one-line change in this topology, either: client certificates authenticate a TLS connection, and the startup command above enables plain HTTP with no server credentials, so there is no TLS on the management interface to carry them. Giving that port its own certificate and trust store comes first. Whether or not you do, keep 9000 on a private interface, which is the control that works without any of it. Your orchestrator needs `/health/ready`; the internet does not.

authentik splits it the same way, on a different number. Its monitoring documentation states that "Both the core authentik server, worker and any outposts expose Prometheus metrics on a separate port (9300)", and that "The metrics require no authentication, as they are hosted on a separate, non-exposed port by default." Non-exposed by default is a property of the shipped Compose file, not of the port, so publishing 9300 to a public interface publishes unauthenticated metrics.

## 6. Enrolment is not enforcement

Every application behind this provider inherits its authentication, which means it inherits the administrator's authentication too. Enrol a phishing-resistant factor on the administrator account before you connect the first application, not after. Both products support TOTP and WebAuthn; [mfa.md](mfa.md) covers the enrolment and the reason to require a hardware key or passkey for administrators specifically.

Enrolling a factor is not the same as requiring one. In Keycloak the requirement lives in the realm's authentication flow, and in authentik in the stage bound to the flow. Neither follows from an administrator having a device registered. Test it the way [mfa.md](mfa.md) says to: open a fresh session, present only the password, and confirm you do not get in.

Two realm settings outlive everything above and neither is touched by it. Keycloak states that "Brute force detection is disabled by default. Enable this feature to protect against brute force attacks", and it is a realm setting rather than a deployment one, so a hardened deployment still accepts unlimited password guesses until you turn it on. And redirect URIs are worth a deliberate pass. Keycloak allows a wildcard at the end of a pattern, which is narrower than it sounds and still widens the set of destinations a token can be sent to; a bare `*` widens it to everything, for anyone who can reach the authorization endpoint, which is everyone. Register exact URIs per [oidc-integration.md](oidc-integration.md), and treat every wildcard as something you chose rather than something you inherited.

## 7. authentik has no equivalent to `hostname-admin`

Section 3 is Keycloak-specific because the control it describes is. authentik does not separate its administration interface onto its own hostname: the admin interface is served by the same process on the same port as everything else, and what protects it is authentik's own permission model rather than routing. Say that out loud rather than assuming the section above covers both products. If you want a network boundary around authentik's administration, you have to build it yourself at the proxy, by path, and you will be maintaining that list against a UI that is not designed around it.

authentik also reaches past this host. Its Compose file, by default, "mounts the Docker socket to the authentik worker container", which the vendor notes "comes with some inherent security risks", and which exists so authentik can deploy and manage outposts. A container with the socket of an ordinary rootful daemon has host-root-equivalent control; Docker also supports a rootless daemon, where the blast radius is the user rather than the host, so check which one you are running before you decide how bad this is. The vendor's own options are a Docker socket proxy or removing the mount and deploying outposts by hand. Whichever you choose, an outpost is another listener with its own exposure, and it is not necessarily elsewhere: authentik ships an embedded one in the server itself, and the ones it deploys for you may land on other hosts. Nothing in the Verify section below sees any of them.

## Verify

```bash
# Steps 2 to 5 and 7 must run from a host OUTSIDE every network you have allowed, against a
# system you are authorized to test. Neutralize the proxy settings first, all of them:
# curl reads ALL_PROXY and all_proxy as well as the per-scheme variables, and it reads
# ~/.curlrc too. A proxy whose egress sits inside an allowed range turns a blocked
# endpoint into a 200 while you are sitting somewhere that should have been refused.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy NO_PROXY no_proxy
# A function, not a variable: an unquoted $CURL would glob-expand the * against whatever is
# in the reader's current directory, and the command would quietly stop disabling the proxy.
# -q ignores ~/.curlrc, which can itself set a proxy or turn verification off.
probe() { curl -q --noproxy '*' -sS "$@"; }
# Every path below is KEYCLOAK's. authentik does not serve /realms/ or /admin/master/,
# so on authentik substitute its own application and administration URLs; step 2's job is
# to prove this host reaches that name at all, and any endpoint you expect to answer does it.

# 1. On the host itself: nothing listens on a public address. Keycloak serves 8080 or 8443
#    and management 9000; authentik serves 9000 and 9443, and metrics on 9300. Three more
#    are easy to forget because they are not the product's front door. 7800 and 57800 are
#    Keycloak's cache transport and failure detection, which carry the sessions and tokens
#    of a clustered deployment; TLS is on by default there for TCP stacks, so this is about
#    reachability rather than plaintext, and a reachable cluster port is still a cluster you
#    did not mean to offer. 6379 is Redis, which authentik used for caching, tasks, the
#    embedded outpost's session store and WebSocket connections. It moved tasks to
#    Postgres in 2025.8 and the rest in 2025.10, which "no longer uses Redis at all", so
#    whether this port matters depends on your version. Check it rather than assume.
ss -tlnp | grep -E ':(6379|7800|8080|8443|9000|9443|9300|57800)\b'    # 127.0.0.1 or an RFC 1918 address only
# ss on the HOST does not see a container's own namespace, and a published Docker port
# bypasses the host firewall besides, so cross-check what Compose actually published:
docker compose ps --format 'table {{.Service}}\t{{.Ports}}'
# no 0.0.0.0 or :: on the identity provider's OWN rows. A proxy in the same
# project publishing 443 is correct and expected. This also sees one Compose
# project, not every container on the host.

# 2. POSITIVE CONTROL, and the reason every check below means anything: the public
#    hostname answers from out here. Use the realm your APPLICATIONS use, not master:
#    section 3 restricts the master realm to your administrators' range, so probing it here
#    would test the wrong thing and tell you nothing about the realm your applications use.
probe https://id.example.com/realms/apps/.well-known/openid-configuration \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["issuer"])'
# It must print YOUR issuer URL. A 200 alone proves only that something answered: a wrong
# upstream or a generic responder satisfies it while the real provider sits exposed
# elsewhere. If this does not print the issuer you expect, stop reading and fix that first,
# because every check below will "pass" for the wrong reason.

# 3. The administration console is closed on the PUBLIC hostname.
probe -o /dev/null -w '%{http_code}\n' https://id.example.com/admin/master/console/
# 404 is the pass. A 302 to a login page is NOT a pass: it means the console answered
# and is offering to authenticate you. Any 2xx, any 3xx, 401 or 403 all mean the path
# was served by something.

# 4. The administration REST API is closed on that same hostname. hostname-admin does
#    not do this for you, so this is the step that proves your proxy rule does.
probe -o /dev/null -w '%{http_code}\n' https://id.example.com/admin/realms/master/users
# 404 is the pass. 401 means the API answered and asked for a token.

# 5. The administrative realm's login paths are RESTRICTED, not refused. Section 3 allows
#    them from your administrators' range and denies everything else, so from out here:
#    403 is the pass. nginx answers a denied source with 403, not 404.
#    200 means the allow rule covers the whole internet, or is not there at all.
#    404 means you used `return 404` rather than an allow rule, which closes the path for
#    your administrators too; see section 3 for why the console needs it on this hostname.
probe -o /dev/null -w '%{http_code}\n' \
  https://id.example.com/realms/master/.well-known/openid-configuration
# Steps 3 to 5 sample three routes and expect two different answers: 404 from the two
# /admin/ paths, which are refused outright, and 403 from the master realm, which is
# restricted by source. Either way they prove those three requests were handled as intended,
# not that the whole administration surface is. A more specific `location` elsewhere in the
# same server block can still serve one, so read the effective configuration too.

# 6. An administrator can still log in. This is the half the rule in section 3 can break and
#    the half nobody tests. From inside the network you allowed in that rule, complete a REAL
#    login to the console rather than just loading the page:
#    open https://id-admin.internal:8443/admin/master/console/ and authenticate.
#    Watch where the browser goes. It SHOULD be sent to id.example.com/realms/master/ to
#    authenticate, because Keycloak builds the console's auth URL from the frontend hostname,
#    and it should come back. If that request 403s, your allow rule does not cover the address
#    you are coming from. If it 404s instead, `return 404` is still in place on that path,
#    which is the state step 5 warns about and it locks out every administrator. If you are
#    testing from outside the allowed range it SHOULD fail, and that is the rule working
#    rather than a fault.

# 7. The management, metrics and application ports are not routable from out here. All of
#    them: a reader who remapped 9000 and left 9443 published passes every other step.
#    --connect-timeout is separate from -m so the two deadlines are distinguishable in the
#    output, not because it changes the exit code: a port that accepts the connection and
#    then stalls, and a port that was never reachable, both still end in exit 28. The
#    diagnostic below is what tells them apart, which is why it is printed whole.
for p in 8080 8443 9000 9300 9443; do
  err=$(probe --connect-timeout 3 -m 8 -o /dev/null -v "http://id.example.com:$p/" 2>&1 >/dev/null)
  rc=$?
  echo "=== $p: curl exit $rc"
  printf '%s\n' "$err"
done
# Exit 0 means it answered and exit 7 means nothing accepted the connection, which is the
# outcome you want. Exit 28 is a timeout and does NOT settle it on its own: a port that
# accepted you and then went quiet, and a port that was never reachable, both end there.
# The whole diagnostic is printed rather than filtered for that reason.
# Read it yourself. A line saying the connection was established, before a timeout, means
# something accepted you and then went quiet, which is an answer. Do not reduce this to a
# grep for a fixed phrase: curl has changed that wording more than once, and an earlier
# version of this guide matched a phrase current curl no longer prints and then read its
# absence as proof that nothing was listening. Absence of a line you were looking for is not
# evidence. If the output does not settle it, the result is inconclusive and has to be
# chased rather than accepted.

# 8. Keycloak's bootstrap admin is gone. It does not expire on its own. Ask for the name
#    rather than listing users: the users endpoint returns at most 100 by default, and a
#    bootstrap account on page two looks exactly like a deleted one.
#    kcadm.sh get users -r master -q exact=true -q "username=REPLACE_WITH_BOOTSTRAP_NAME" --fields username,id
#    exact=true matters: without it the filter is a substring match, and the result is capped
#    at 100 either way, so an unfiltered list proves nothing about what is not in it.
#    Order the -q flags this way round: an exactness flag placed after the filter it modifies
#    has been reported not to take effect, and the cost of ordering it defensively is nothing.
#    Check the master realm's service accounts too: a bootstrap SERVICE account is created
#    by the client-id form of the same mechanism and is not in the user list at all.
```

One name is not one address, and one address is not one origin. Repeat steps 2 to 5 and 7 for every public address the name carries and in both families, since a host filtered on IPv4 while it answers on IPv6 passes all of them. A CDN or load balancer answering on 443 also says nothing about whether the backend has its own reachable address, so check the origin directly as well. And nothing here tests `id-admin.internal`, the database, or the authentik outposts of section 7; those are separate surfaces with separate checks. The port list is the one this guide's own topology creates, not an inventory: scan the whole range if you want one.

## Sources (checked September 2026)

- Keycloak production configuration, including the TLS requirement and separating the admin REST API and console: https://www.keycloak.org/server/configuration-production
- Keycloak hostname options, including the production and dev profile defaults for `hostname-strict`, and the statement that `hostname-admin` does not restrict the Administration REST API: https://www.keycloak.org/server/hostname
- Keycloak reverse proxy configuration, including `proxy-headers`, `proxy-trusted-addresses`, the forwarded-header warning, and the exposed-paths table: https://www.keycloak.org/server/reverseproxy
- Keycloak bootstrap and recovery admin accounts, including that the account is temporary and must be removed manually: https://www.keycloak.org/server/bootstrap-admin-recovery
- Keycloak management interface and the default management port 9000: https://www.keycloak.org/server/management-interface
- authentik Docker Compose installation, including the default ports and the initial setup flow that sets the `akadmin` password: https://docs.goauthentik.io/install-config/install/docker-compose/
- authentik monitoring, including the separate metrics port 9300 and that the metrics carry no authentication: https://docs.goauthentik.io/sys-mgmt/ops/monitoring
- Keycloak server administration guide, brute force detection ("Brute force detection is disabled by default") and unspecific redirect URIs: https://www.keycloak.org/docs/latest/server_admin/index.html
- nginx `location` selection and the `return` directive: https://nginx.org/en/docs/http/ngx_http_core_module.html#location , https://nginx.org/en/docs/http/ngx_http_rewrite_module.html#return
- Keycloak configuring distributed caches, including the default cache ports 7800 (`cache-embedded-network-bind-port`, unicast data transmission) and 57800 (`jgroups.fd.port-offset`, failure detection), and that "Encryption using TLS is enabled by default for TCP-based transport stacks": https://www.keycloak.org/server/caching
- authentik 2025.10 release notes, removing the Redis dependency ("authentik no longer uses Redis at all"): https://docs.goauthentik.io/releases/2025.10/
