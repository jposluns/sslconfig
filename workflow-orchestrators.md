# Workflow and agent orchestrators: Prefect, Dagster, Airflow, Temporal, Flower

These webservers and UIs schedule and trigger arbitrary code execution across your infrastructure, and most
ship with no authentication at all. Keep every one of them off the public internet and add auth before
anyone but you can reach the port.

## Prefect (self-hosted server)

There is no default authentication; `prefect server start` accepts unauthenticated API calls until you set
one up. Basic Auth is a single administrator/password string, set on the server with
`PREFECT_SERVER_API_AUTH_STRING` (or the `server.api.auth_string` setting) and the identical value on every
client with `PREFECT_API_AUTH_STRING` (`api.auth_string`); the UI prompts for the string on first load. This
is unrelated to Prefect Cloud: `PREFECT_API_KEY` authenticates only to Prefect Cloud, and if it happens to be
set alongside `PREFECT_API_AUTH_STRING` on a client talking to a self-hosted server, the key takes precedence
and the request fails with 401. Store the auth string in a secret manager or a private `.env` file, never in
the repository ([secrets.md](secrets.md)).

## Dagster (OSS)

The `dagster-webserver` (reachable by default around port 3000 in local dev) has no built-in authentication
or access control; the documentation for the open-source webserver does not describe a login of any kind.
Put it entirely behind an identity-aware fronting layer ([fronting-auth.md](fronting-auth.md)) or your own
reverse proxy with its own authentication ([nginx.md](nginx.md), [caddy.md](caddy.md)) plus MFA
([mfa.md](mfa.md)), and never publish the port directly.

## Apache Airflow

Airflow's own security model states it plainly: "Airflow doesn't support unauthenticated users by default"
and "Airflow is not designed to be exposed to untrusted users on the public internet"; every user of the UI
and API is assumed to be authenticated and known, and keeping it off the public internet is the deployment
manager's responsibility, not something the software enforces for you. Access is governed by a pluggable
"auth manager". The default is the Simple Auth Manager, which the documentation marks for development and
testing only: it prints a warning banner on login, and its users and roles (`viewer`, `user`, `op`, `admin`)
come from `simple_auth_manager_users` in `[core]` (for example `bob:admin,peter:viewer`), with a password
auto-generated per user and printed to the webserver logs unless you set your own. For production, configure
the FAB auth manager instead: install the FAB provider, then set `[core] auth_manager` to
`airflow.providers.fab.auth_manager.fab_auth_manager.FabAuthManager` and confirm the effective manager with
`airflow config get-value core auth_manager`. `[fab] auth_backends` is a different setting that selects the
authentication backends for the FAB API, not the auth manager. Point FAB at LDAP, OAuth, or another real identity backend,
and put MFA at that identity provider ([mfa.md](mfa.md), [identity-providers.md](identity-providers.md)).

## Temporal (self-hosted)

With no authorizer configured, the server runs the default `noopAuthorizer`, which the documentation says
"allows every API request, with no authentication or access control" at all, including administrative
operations. Configure an `Authorizer` together with a `ClaimMapper` (`temporal.WithAuthorizer()`,
`temporal.WithClaimMapper()`, or the equivalent `config.Global.Authorization` keys) so every gRPC call to the
Temporal Service is checked against a mapped claim before anything runs. This is entirely separate from Web
UI login: the UI's own config reference documents an `auth.providers` block with `enabled`, `type: oidc`,
`providerUrl`, `issuerUrl`, `clientId`, `clientSecret`, `callbackUrl`, and `scopes` for OIDC SSO into the
dashboard, but that only gates the UI, not the server API a worker or CLI talks to directly. mTLS secures
internode and frontend traffic separately again. Set up both layers; MFA comes from whichever identity
provider the UI's OIDC settings point at.

## Flower (for Celery)

Flower binds every interface by default (`--address` is empty, meaning all interfaces; `--port` defaults to
5555) with authentication disabled unless you configure it. `--basic-auth="user1:password1,user2:password2"`
turns on HTTP Basic Auth with a comma-separated credential list; OAuth 2.0 login against Google, GitHub,
GitLab, or Okta is enabled by setting `--auth_provider` to the provider's handler class plus `--oauth2_key`,
`--oauth2_secret`, `--oauth2_redirect_uri`, and an `--auth` regular expression of the email addresses allowed
to sign in. Prefer OAuth against a provider that enforces MFA over Basic Auth alone ([mfa.md](mfa.md)), and
bind `--address=127.0.0.1` behind a proxy rather than relying on Basic Auth as the only control.

## Verify

```bash
ss -tlnp | grep -E ':(4200|3000|8080|7233|8233|5555) '                 # loopback or private only, never 0.0.0.0
curl -sS -o /dev/null -w '%{http_code}\n' -X POST http://prefect.internal:4200/api/flows/filter -d '{}'
                                                                        # 401 without the auth string once configured. Do NOT probe
                                                                        # /api/health or /api/ready: Prefect exempts those two paths
                                                                        # on GET so container probes keep working, so they answer 200
                                                                        # whether or not authentication is configured
curl -sS -o /dev/null -w '%{http_code}\n' -u '' http://dagster.internal:3000/
                                                                        # must be blocked at the proxy, not Dagster itself
curl -sSI https://airflow.example.com/                                 # login redirect, never the DAG list
curl -sS -o /dev/null -w '%{http_code}\n' http://flower.internal:5555/
                                                                        # 401 once --basic-auth or OAuth is set
```

A DAG list, flow run, task graph, or worker pool that renders without a credential is a finding; so is a
Temporal Service that accepts a gRPC call with no claim behind it, since the UI login does not cover that
path.

## Common mistakes

- Assuming Airflow's Simple Auth Manager, meant for development, is acceptable in production because it
  technically requires a password.
- Configuring Temporal's UI SSO and believing the server API is now protected too; they are independent.
- Setting `PREFECT_API_KEY` on a client that should be using `PREFECT_API_AUTH_STRING` against a self-hosted
  server, then debugging the resulting 401 as a server problem.
- Publishing Flower's `5555` or Dagster's `3000` straight to the internet "for the team" with no proxy.

## Sources (checked September 2026)

- Prefect, security settings (`PREFECT_SERVER_API_AUTH_STRING`, `PREFECT_API_AUTH_STRING`, Cloud API keys
  taking precedence and causing 401): https://docs.prefect.io/v3/advanced/security-settings
- Prefect, self-hosted server on Windows (default port 4200): https://docs.prefect.io/v3/how-to-guides/self-hosted/server-windows
- Dagster, webserver and UI (default local port, no documented built-in auth): https://docs.dagster.io/guides/operate/webserver
- Apache Airflow, security overview: https://airflow.apache.org/docs/apache-airflow/stable/security/
- Apache Airflow, auth manager selection (`[core] auth_manager`, `airflow config get-value core auth_manager`): https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/auth-manager/index.html
- Apache Airflow FAB provider, API authentication (`[fab] auth_backends`, independent of the auth manager): https://airflow.apache.org/docs/apache-airflow-providers-fab/stable/auth-manager/api-authentication.html
- Prefect server source (health and ready paths exempted from the auth string on GET): https://github.com/PrefectHQ/prefect/blob/main/src/prefect/server/api/server.py
- Apache Airflow, quickstart (default port 8080): https://airflow.apache.org/docs/apache-airflow/stable/start.html
- Apache Airflow, security model ("doesn't support unauthenticated users", "not designed to be exposed... to
  untrusted users on the public internet"): https://airflow.apache.org/docs/apache-airflow/stable/security/security_model.html
- Apache Airflow, Simple auth manager (default, dev/test only, `simple_auth_manager_users`, generated
  passwords): https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/auth-manager/simple/index.html
- Temporal, self-hosted security (`noopAuthorizer` default, `Authorizer`, `ClaimMapper`): https://docs.temporal.io/self-hosted-guide/security
- Temporal, Web UI configuration reference (`auth.providers`, `enabled`, `type: oidc`, `providerUrl`,
  `clientId`, `clientSecret`, `callbackUrl`, `scopes`): https://docs.temporal.io/references/web-ui-configuration
- Temporal, CLI server reference (default frontend gRPC port 7233, Web UI port 8233): https://docs.temporal.io/cli/command-reference/server
- Flower, configuration (`--address`, `--port` 5555 default, `--basic-auth`, `--auth_provider`, `--oauth2_key`,
  `--oauth2_secret`, `--oauth2_redirect_uri`, `--auth`): https://flower.readthedocs.io/en/latest/config.html
