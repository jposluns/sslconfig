# DevOps panels: Portainer, Coolify, Dokploy, Nginx Proxy Manager, Vaultwarden, Kubernetes Dashboard, Jenkins, Gitea, Uptime Kuma, and the Docker API

These panels control hosts, containers, clusters, deploy keys, and secrets; a login to one of them is a login to everything it manages. One rule dominates everything tool-specific below: **a DevOps panel is never reachable from the public internet.** Bind it to loopback or a private interface and reach it through SSH port forwarding, a tailnet ([tailscale.md](tailscale.md)), or Cloudflare Access ([cloudflare.md](cloudflare.md)); anything that must be public sits behind a TLS proxy with its own authentication ([nginx.md](nginx.md), [caddy.md](caddy.md)) and the admin login gets MFA ([mfa.md](mfa.md)). Several of these tools create their administrator on first visit, so whoever reaches a fresh install first owns it: create the account before the port is reachable by anyone else.

## Portainer

- Serves the UI over HTTPS on `9443` (self-signed by default; supply your own certificate or front it per [nginx.md](nginx.md)). `9000` is the legacy HTTP port and stays unpublished; `8000` is the Edge agent tunnel and is only published when Edge Compute is in use.
- New instances require a setup token to complete first-time setup; it is in the server logs on the `setup_token=` line. The first user is an administrator, and its password must be at least 12 characters.
- Authentication is internal, LDAP, Active Directory, or OAuth (Microsoft, Google, GitHub, or a custom provider). Portainer's own login has no second factor in its documentation; use OAuth against a provider that enforces MFA ([identity-providers.md](identity-providers.md)).
- The container mounts `/var/run/docker.sock`, which is root on the host; a Portainer admin is a host root user ([docker.md](docker.md)).

## Coolify and Dokploy

Both are one-script installs that hold your servers' SSH private keys, Git provider credentials, and application secrets, and both create their administrator on first visit.

- Coolify's dashboard answers on `8000` over plain HTTP after install. Its documentation says to create the admin account immediately, because whoever reaches the registration page first can gain full control of the server. Set the instance a custom domain on the `/settings` page; the integrated proxy (Traefik by default, or Caddy) then issues and renews a Let's Encrypt certificate, and the firewall guide says ports `8000`, `6001`, and `6002` can be closed once the dashboard is reached through that domain. Docker's iptables rules bypass UFW, so restrict these ports with the cloud provider's firewall ([cloud-firewalls.md](cloud-firewalls.md)). Coolify requires the server SSH key to have no passphrase, so the key material inside Coolify is the whole secret.
- Dokploy's UI answers on `3000`; ports `80` and `443` belong to its Traefik. The first visit is the setup page that creates the admin account. Configure a domain with a Let's Encrypt or custom certificate for the panel under Domains, then remove the published `3000` binding so the panel is reachable only through the proxy.

## Nginx Proxy Manager

The admin UI is on port `81`; the proxy itself is on `80`/`443`. Port `81` is never published to the internet: bind it to `127.0.0.1` in the compose file (`'127.0.0.1:81:81'`) and reach it through a tunnel. A default admin user is created on the first run; change the initial admin credentials on first login, before anything else. Since it terminates TLS for every site behind it, treat its login like a root password.

## Vaultwarden

- The web vault needs HTTPS (browsers expose the crypto APIs it uses only in secure contexts). The wiki recommends a reverse proxy for TLS ([caddy.md](caddy.md), [nginx.md](nginx.md)) and rates the built-in `ROCKET_TLS` as not recommended. Set `DOMAIN=https://vault.example.com`.
- `SIGNUPS_ALLOWED=false` (the default is `true`, letting anyone who reaches the instance register). Organization owners and admins can still invite users while `INVITATIONS_ALLOWED=true`; `SIGNUPS_DOMAINS_WHITELIST` admits specific email domains.
- The admin page is disabled unless `ADMIN_TOKEN` is set. Store it as an argon2id PHC string generated with `vaultwarden hash` (or `docker run --rm -it vaultwarden/server /vaultwarden hash`), never plaintext; in a compose `environment:` block every `$` in the hash becomes `$$`. Enable HTTPS before enabling the admin page. Admin sessions expire after 20 minutes by default.
- Inside a container it listens on `80` (`8000` outside Docker); publish it only to loopback or the proxy network.

## Kubernetes Dashboard

- As of September 2026 the Kubernetes documentation marks the Dashboard deprecated and unmaintained (the repository was archived in January 2026) and points new installs to Headlamp; the pattern below applies to any cluster UI.
- Do not expose it with a LoadBalancer or Ingress. Reach it from the operator's machine with `kubectl -n kubernetes-dashboard port-forward svc/kubernetes-dashboard-kong-proxy 8443:443` and open `https://localhost:8443`; the UI is then reachable only from that machine.
- Login is by bearer token of a ServiceAccount with a minimal RBAC role; the tutorial's sample user is cluster-admin and is for demonstration only. On the older 2.x releases, `--enable-skip-login` and `--enable-insecure-login` both default to `false`; never turn them on.
- A ServiceAccount token is a machine credential, so configuring OIDC on the API server puts no MFA on this login. Human MFA comes from the access path (a port-forward over SSH from a machine that already required it, a tailnet per [tailscale.md](tailscale.md), or Cloudflare Access per [cloudflare.md](cloudflare.md)) or from a UI that performs an identity-provider login itself; see [mfa.md](mfa.md).

## Jenkins

- Authentication (the security realm: Jenkins' own user database, LDAP, and others) and authorization (the strategy) are configured separately. The setup wizard leaves a single admin in the local database; do not enable account signup for that database, since new accounts inherit whatever the strategy grants to authenticated users.
- Use the Matrix Authorization Strategy (global or project-based) and grant nothing significant to `anonymous` or to `authenticated`; granting Overall/Administer to anonymous is the same as "Anyone can do anything".
- Leave CSRF protection on. It has no UI switch and is only disabled by the `hudson.security.csrf.GlobalCrumbIssuerConfiguration.DISABLE_CSRF_PROTECTION` system property; the documentation says to keep it enabled even on private networks.
- Inbound agents use a fixed or random TCP port, or WebSocket over the same HTTPS port with no extra listener; prefer WebSocket or keep the agent port on the private network.
- Jenkins has no native second factor; put the web UI behind SSO with MFA at the provider or behind an identity layer ([mfa.md](mfa.md)).

## Gitea

- It listens on `HTTP_ADDR = 0.0.0.0`, `HTTP_PORT = 3000` by default; set `HTTP_ADDR = 127.0.0.1` behind a proxy, or `PROTOCOL = https` with `CERT_FILE` and `KEY_FILE` to terminate TLS itself.
- In `[service]`, `DISABLE_REGISTRATION = true` (default `false`) and, for a private forge, `REQUIRE_SIGNIN_VIEW = true` (default `false`).
- Users enrol TOTP or a WebAuthn key under Settings > Security; `TWO_FACTOR_AUTH = enforced` in `[security]` (Gitea 1.24 and later) requires it. With MFA on, Git over HTTP uses an access token instead of the password, and tokens bypass MFA, so scope them and revoke unused ones ([machine-auth.md](machine-auth.md)).

## Uptime Kuma

Listens on `3001` and is WebSocket-based, so a reverse proxy in front needs the `Upgrade` and `Connection` headers. Open it right after the first start and finish the account setup before anyone else can; then enable the 2FA the project lists as a feature for that account. Status pages can be public; the dashboard is not.

## The Docker API

The daemon socket is root on the host: anyone who can talk to it can run a privileged container. Never start `dockerd` with `-H tcp://0.0.0.0:2375`; Docker's documentation calls remote access without TLS not recommended, and scanners find open 2375 within minutes. Two acceptable remote paths:

```bash
# 1. SSH to the Unix socket (nothing new listens on the network)
export DOCKER_HOST=ssh://docker-user@host1.example.com
docker context create remote --docker host=ssh://docker-user@host1.example.com

# 2. TLS with client certificates on 2376, all four flags set
dockerd --tlsverify --tlscacert=ca.pem --tlscert=server-cert.pem --tlskey=server-key.pem -H=0.0.0.0:2376
export DOCKER_HOST=tcp://$HOST:2376 DOCKER_TLS_VERIFY=1 DOCKER_CERT_PATH=~/.docker/zone1/
```

Without `--tlsverify` the daemon does not check client certificates. Firewall 2376 to the operator addresses even with TLS ([docker.md](docker.md)).

## Dozzle

- Dozzle reads the Docker socket to show logs, the same host-level access the Docker API section above describes ([docker.md](docker.md)); a Dozzle login is a login to the host.
- Authentication is off unless configured. Generate a `users.yml` with `docker run -it --rm amir20/dozzle generate admin > users.yml` (omit `--password` and Dozzle prompts for it on stdin, so it never lands in shell history), mount that file into the container, and set `DOZZLE_AUTH_PROVIDER=simple`; or set `DOZZLE_AUTH_PROVIDER=forward-proxy` to delegate login to a fronting proxy such as Authelia, Authentik, or Cloudflare Access.
- Container actions (start, stop, recreate) and shell access into a running container can be turned on; leave both off unless a specific workflow needs them, since either turns a log viewer into remote command execution on the host.
- Bind it to loopback or a private interface and reach it through SSH port forwarding, a tailnet, or Access, with MFA at the fronting layer, like every panel above.

## Docker Registry (`registry:2`)

- The reference registry image ships with no authentication at all: anyone who reaches the port can push and pull every image, and TLS must be configured before any authentication scheme works, since credentials would otherwise cross the wire in clear text.
- Restrict access with htpasswd basic authentication, a token server, or a registry distribution that has its own authentication built in. If using the registry's own native htpasswd auth provider (set directly in the registry's `config.yml`), credentials must be bcrypt-hashed (`htpasswd -B`); the registry rejects any other hash format. If instead a reverse proxy sits in front and does its own basic authentication from its own htpasswd file, that proxy's own hashing rules apply, not the registry's.
- Bind it to loopback or a private interface and reach it through SSH port forwarding, a tailnet, or Access, with MFA at the fronting layer.

## Filebrowser

- Ships with a default administrator account created on first run (historically `admin`/`admin`). Change it immediately, before the instance is reachable by anyone else. The project's own repository (archived on September 1, 2026) says not to expose it directly to the internet.
- Bind it to loopback or a private interface and reach it through SSH port forwarding, a tailnet, or Access, with MFA at the fronting layer; never publish a file-serving admin panel.

## Node-RED

- The editor and admin API on `1880` have no authentication at all by default; anyone who reaches the port can view, deploy, and modify flows.
- Set `adminAuth` in `settings.js` with bcrypt-hashed user passwords (`node-red admin hash-pw` generates the hash), and set `credentialSecret` to a value you control, since Node-RED otherwise generates one for you and stored credentials are only as protected as that secret.
- Bind it to loopback or a private interface and reach it through SSH port forwarding, a tailnet, or Access, with MFA at the fronting layer; the editor is equivalent to a shell on whatever the flows can reach.

## Verify

```bash
ss -tlnp | grep -E ':(9443|9000|8000|3000|81|3001|2375|2376) '   # 127.0.0.1 or absent, never 0.0.0.0
curl -s -o /dev/null -w '%{http_code}\n' https://panel.example.com/
                                                                  # 401, 403, or a login redirect, never a dashboard. No -k:
                                                                  # this panel is behind a proxy holding a real certificate, so
                                                                  # a check that skips verification proves nothing about it
docker -H tcp://203.0.113.10:2375 info                            # must fail: connection refused or filtered
env -u DOCKER_HOST -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  curl -sS -o /dev/null -w '%{http_code}\n' --cacert ca.pem https://203.0.113.10:2376/_ping
                                                                  # must fail the handshake on the CLIENT certificate. Do not use
                                                                  # `docker ... info` here: without `--tlsverify` it fails for the
                                                                  # wrong reason, and `DOCKER_CERT_PATH` exported in the setup above
                                                                  # can silently supply the very certificate the check is meant to lack
curl -sS -o /dev/null -w '%{http_code}\n' --cacert ca.pem --cert client-cert.pem --key client-key.pem \
  https://203.0.113.10:2376/_ping                                 # positive control: 200 with the right client certificate
```

From outside the network, every panel URL is unreachable or shows a login; a page that renders host, container, or repository data without one is a finding.

## Sources (checked September 2026)

- Portainer CE install on Docker (ports 9443, 9000, 8000): https://docs.portainer.io/start/install-ce/server/docker/linux
- Portainer initial setup (setup token, first admin, 12-character password): https://docs.portainer.io/start/install-ce/server/setup
- Portainer authentication and OAuth providers: https://docs.portainer.io/admin/settings/authentication and https://docs.portainer.io/admin/settings/authentication/oauth
- Coolify installation, firewall, proxy, and DNS pages: https://coolify.io/docs/get-started/installation , https://coolify.io/docs/knowledge-base/server/firewall , https://coolify.io/docs/knowledge-base/proxy/overview , https://coolify.io/docs/knowledge-base/dns-configuration , https://coolify.io/docs/knowledge-base/server/openssh
- Dokploy installation (ports 80, 443, 3000; admin setup; panel domain): https://docs.dokploy.com/docs/core/installation
- Nginx Proxy Manager setup (port 81, default admin user): https://nginxproxymanager.com/setup/
- Vaultwarden wiki: admin page and ADMIN_TOKEN https://github.com/dani-garcia/vaultwarden/wiki/Enabling-admin-page , registration https://github.com/dani-garcia/vaultwarden/wiki/Disable-registration-of-new-users , HTTPS https://github.com/dani-garcia/vaultwarden/wiki/Enabling-HTTPS , and the `.env.template` https://github.com/dani-garcia/vaultwarden/blob/main/.env.template
- Kubernetes Dashboard (deprecation, port-forward, token login): https://kubernetes.io/docs/tasks/access-application-cluster/web-ui-dashboard/ ; 2.x arguments: https://github.com/kubernetes/dashboard/blob/v2.7.0/docs/common/dashboard-arguments.md
- Jenkins security: https://www.jenkins.io/doc/book/security/managing-security/ , https://www.jenkins.io/doc/book/security/access-control/ , https://www.jenkins.io/doc/book/security/csrf-protection/
- Gitea config cheat sheet and MFA: https://docs.gitea.com/administration/config-cheat-sheet and https://docs.gitea.com/usage/user-setting/multi-factor-authentication/
- Uptime Kuma README and reverse proxy wiki: https://github.com/louislam/uptime-kuma and https://github.com/louislam/uptime-kuma/wiki/Reverse-Proxy
- Docker: protect the daemon socket https://docs.docker.com/engine/security/protect-access/ and remote access https://docs.docker.com/engine/daemon/remote-access/
- Dozzle authentication (DOZZLE_AUTH_PROVIDER, users.yml, actions and shell): https://dozzle.dev/guide/authentication
- Docker Registry deployment (default authentication, TLS requirement): https://distribution.github.io/distribution/about/deploying/
- Filebrowser: https://filebrowser.org/
- Node-RED securing the runtime (adminAuth, credentialSecret): https://nodered.org/docs/user-guide/runtime/securing-node-red
