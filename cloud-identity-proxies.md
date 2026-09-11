# Identity-aware proxies: login in front of the app with no code change

An identity-aware proxy puts a login page in front of an application without changing the application: the cloud's load balancer, platform edge, or tunnel authenticates the user against an identity provider and forwards the request with the user's identity in headers. [cloudflare.md](cloudflare.md) documents the pattern for Cloudflare Access; this guide covers the equivalents in AWS, Google Cloud, Azure, ngrok, and Vercel. The pattern fails in two ways: the origin stays reachable around the proxy, or the app trusts an identity header anyone can type. Both are addressed below.

## 1. Rules common to every proxy

1. **The origin accepts traffic only from the proxy.** Bind to loopback behind a tunnel, reference the load balancer's security group, or restrict ingress to the load balancer. If the app also answers directly, the login page is decorative ([cloud-firewalls.md](cloud-firewalls.md)).
2. **The app never trusts a plain identity header.** Where the proxy provides a signed assertion (AWS, Google Cloud, Cloudflare), verify its signature, issuer, audience, and expiry before using any claim. Where the platform documents that clients cannot set the identity headers (Azure), that guarantee holds only for requests that arrived through the platform.
3. **MFA comes from the identity provider behind the proxy.** None of these proxies adds a second factor of its own; enforce it at the IdP and the proxy inherits it ([mfa.md](mfa.md), [identity-providers.md](identity-providers.md)).
4. Authorization is still yours: the proxy proves who the user is, and the app or the proxy policy decides what they may do ([authentication.md](authentication.md)).
5. **Fail closed.** The auth layer must deny when it cannot reach a decision: missing auth configuration, an unreachable authorization service, and an unmatched route must never fall through to the app unauthenticated. Test this with a fresh, unauthenticated request against a protected route while the authorization service is unreachable, and require denial, not pass-through; an already-authenticated session is a separate question, since a proxy is not guaranteed to recheck the identity provider on every request.

## 2. AWS Application Load Balancer

A listener rule with an `authenticate-oidc` (any OIDC provider) or `authenticate-cognito` (Cognito user pool, including social and SAML federation) action, followed by a `forward` action. Both action types work only on HTTPS listeners. The `OnUnauthenticatedRequest` field takes `authenticate` (the default: redirect to the IdP), `allow` (forward without claims, for pages with a public view), or `deny` (HTTP 401). `SessionTimeout` defaults to 7 days and can be set as short as 1 second. The IdP must allow `https://<load-balancer-dns-or-cname>/oauth2/idpresponse` as a redirect URL.

```json
{ "Type": "authenticate-oidc",
  "AuthenticateOidcConfig": {
    "Issuer": "https://idp.example.com", "AuthorizationEndpoint": "...", "TokenEndpoint": "...",
    "UserInfoEndpoint": "...", "ClientId": "...", "ClientSecret": "REPLACE_WITH_LONG_RANDOM_VALUE",
    "SessionTimeout": 3600, "OnUnauthenticatedRequest": "deny" },
  "Order": 1 }
```

The load balancer forwards the user claims to targets in `x-amzn-oidc-data`, a JWT signed with ES256. The app must verify that signature (public key from `https://public-keys.auth.elb.<region>.amazonaws.com/<key-id>`, key ID from the JWT header) and confirm that the `signer` field in the JWT header is your load balancer's ARN before using any claim; AWS publishes the `aws-jwt-verify` library for this. `x-amzn-oidc-accesstoken` and `x-amzn-oidc-identity` are unsigned legacy headers and cannot be verified, so never use them for identity. Restrict the targets' security group to accept traffic only from the load balancer's security group, and use an HTTPS target group if the claims must be encrypted on the last hop.

## 3. Google Cloud Identity-Aware Proxy

IAP protects App Engine, Cloud Run, Compute Engine, GKE, and on-premises applications (plus Cloud Storage buckets). A user reaches the app only if they hold the **IAP-secured Web App User** IAM role on the resource; identities can come from Google Accounts, from an external IdP through Workforce Identity Federation, or from customers through Identity Platform.

IAP adds `x-goog-iap-jwt-assertion`, an ES256 JWT. Verify the signature against the keys at `https://www.gstatic.com/iap/verify/public_key-jwk`, check `iss` is `https://cloud.google.com/iap`, and check `aud` matches your resource (`/projects/PROJECT_NUMBER/global/backendServices/SERVICE_ID` for a backend service, `/projects/PROJECT_NUMBER/locations/REGION/services/SERVICE_NAME` for Cloud Run, `/projects/PROJECT_NUMBER/apps/PROJECT_ID` for App Engine). The unsigned `x-goog-authenticated-user-email` and `x-goog-authenticated-user-id` headers can be forged by anyone who bypasses IAP; Google's docs describe the JWT as the secure alternative.

Bypass is the main risk. Google's docs say to verify whether backend resources can be reached directly when IAP is enabled on a load balancer, and that IAP on a load balancer secures only traffic through that load balancer, not traffic that reaches a Cloud Run service through its `run.app` URL. Either enable IAP directly on the Cloud Run service (the documented recommendation, no load balancer needed), or disable the default URL or restrict ingress so only the load balancer reaches it. For Compute Engine and GKE, firewall rules must block traffic that does not come through the load balancer.

## 4. Azure App Service and Azure Functions

Built-in authentication ("Easy Auth") is a platform module in front of the app; per the docs no SDK, language, or application code change is required. Providers: Microsoft Entra, Facebook, Google, X, GitHub, Apple (preview at the time of writing), and any OpenID Connect provider. Under **Settings > Authentication**, choose **Require authentication** to reject unauthenticated traffic (as an HTTP 302 redirect to the provider, recommended for websites; or 401, recommended for APIs; or 403 or 404), or **Allow unauthenticated requests** to let the app decide. Enabling the feature redirects all requests to HTTPS regardless of the app's enforce-HTTPS setting (`requireHttps` in the V2 configuration can turn this off; do not). Requiring authentication applies to every path; exceptions need a configuration file with excluded paths.

The app receives the identity in `X-MS-CLIENT-PRINCIPAL` (Base64 JSON of the claims), `X-MS-CLIENT-PRINCIPAL-ID`, `X-MS-CLIENT-PRINCIPAL-NAME`, and `X-MS-CLIENT-PRINCIPAL-IDP`, with `/.auth/me` available when the token store is on. The docs state that external requests are not allowed to set these headers, so they are present only if App Service set them. With the Entra provider, any user in the tenant can obtain a token by default; restrict the app registration to assigned users if that is not intended.

**Azure Container Apps** uses the same authentication system, run as a sidecar container on each replica, with Microsoft Entra ID, Facebook, GitHub, Google, X, and custom OpenID Connect providers, and the same **Require authentication** / **Allow unauthenticated access** choice and `X-MS-CLIENT-PRINCIPAL-*` headers that external requests cannot set. The docs require HTTPS only: `allowInsecure` must be disabled on the ingress.

**Azure Static Web Apps** authenticates with GitHub and Microsoft Entra ID out of the box on all plans (a registered custom provider replaces the preconfigured ones; X is no longer preconfigured). Sign-in is at `/.auth/login/github` or `/.auth/login/aad`, signed-in users hold the `anonymous` and `authenticated` roles, and route rules in `staticwebapp.config.json` restrict paths by role. The preconfigured Entra provider accepts any Microsoft account; to limit sign-in to one tenant, configure a custom Entra provider.

## 5. Cloudflare Access

Set up the tunnel and Access policy per [cloudflare.md](cloudflare.md). Then have the app validate the `Cf-Access-Jwt-Assertion` header (preferred over the `CF_Authorization` cookie, which is not guaranteed to be passed) against the public keys at `https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs`, checking that `aud` equals the application's AUD tag and `iss` is your team domain. Access rotates the signing key every 6 weeks with the previous key valid for 7 days, so fetch keys from the endpoint rather than hard-coding them.

## 6. ngrok

ngrok's traffic policy `oauth` action (providers include `google`, `github`, and `microsoft`) and `openid-connect` action (`issuer_url`, `client_id`, `client_secret`, `scopes`) redirect unauthenticated visitors to the provider, so a local tool becomes public only behind a login. Restrict who gets through with an expression on the identity the action exposes:

```yaml
on_http_request:
  - actions:
      - type: oauth
        config:
          provider: google
  - expressions:
      - "!actions.ngrok.oauth.identity.email.endsWith('@example.com')"
    actions:
      - type: deny
        config:
          status_code: 403
```

Use `actions.ngrok.oauth.identity.email in ['alice@example.com']` for an explicit list. Leaving `client_id` and `client_secret` empty uses ngrok's managed OAuth application for the supported providers. Run with `ngrok http 3000 --traffic-policy-file policy.yml`; the older `--oauth`, `--oauth-allow-domain`, and `--oauth-allow-email` agent flags are marked deprecated in favour of traffic policy.

## 7. Vercel Deployment Protection

Vercel's protection guards a deployment from the public; it is not your application's user login. **Vercel Authentication** (all plans) admits logged-in team or project members with at least a viewer role, users granted access on request, holders of a shareable link, and automation with the bypass header. **Standard Protection** covers preview deployments and generated deployment URLs but not production domains; the **All Deployments** scope closes that gap, and Vercel's September 9, 2026 change made pairing it with Vercel Authentication free on every plan, including Hobby, rather than Pro and Enterprise only (per Vercel's Deployment Protection changelog, at the time of writing; the configuration reference page itself still listed All Deployments as Pro and Enterprise only when checked, so confirm current availability in your own dashboard). Until All Deployments protection is configured, the production domain stays public on every plan. **Password Protection** is an Enterprise feature or a paid Pro add-on (Advanced Deployment Protection, USD 150 per month at the time of writing); Trusted IPs and Passport (your own IdP) are Enterprise only.

## Verify

```bash
curl -sI http://203.0.113.10:3000/                      # origin direct: timeout or connection refused
curl -sI https://app.example.com/                       # via proxy, no session: 302 to the IdP, or 401/403
curl -s -H "x-amzn-oidc-identity: admin" \
     -H "X-MS-CLIENT-PRINCIPAL-NAME: admin" \
     -H "X-Goog-Authenticated-User-Email: admin@example.com" \
     https://app.example.com/whoami                      # still the login redirect; never "admin"
```

After logging in, confirm that the app's own identity check reads the signed assertion (`x-amzn-oidc-data`, `x-goog-iap-jwt-assertion`, `Cf-Access-Jwt-Assertion`) and rejects a request carrying a tampered one.

- Stop the authorization service, or break its configuration, and send a fresh, unauthenticated request to a protected route: it must be denied, never passed through to the app. This checks that an undecidable auth state fails closed; it does not test whether an already-established session survives the outage, since a proxy is not required to recheck the identity provider on every request.

## Common mistakes

- Enabling IAP or ALB authentication while the Cloud Run `run.app` URL, the instance's public IP, or a second listener still serves the app directly.
- Reading `x-amzn-oidc-identity`, `X-Goog-Authenticated-User-Email`, or a similar unsigned header as the user identity.
- Treating Vercel Authentication as end-user login, or leaving production on Standard Protection and assuming it is covered.
- Using the ngrok `oauth` action without a `deny` rule on email or domain, which lets anyone with a Google account in.

## Sources (checked September 2026)

- AWS, Authenticate users using an Application Load Balancer: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html
- Google Cloud IAP overview: https://docs.cloud.google.com/iap/docs/concepts-overview
- Google Cloud IAP, securing your app with signed headers: https://docs.cloud.google.com/iap/docs/signed-headers-howto
- Google Cloud IAP, enabling IAP for Cloud Run: https://docs.cloud.google.com/iap/docs/enabling-cloud-run
- Azure App Service authentication and authorization: https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization
- Azure App Service, work with user identities (headers): https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-user-identities
- Azure Container Apps authentication: https://learn.microsoft.com/en-us/azure/container-apps/authentication
- Azure Static Web Apps authentication and authorization: https://learn.microsoft.com/en-us/azure/static-web-apps/authentication-authorization
- Cloudflare Access, validate JWTs: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/
- ngrok traffic policy OAuth action: https://ngrok.com/docs/traffic-policy/actions/oauth/
- ngrok traffic policy OpenID Connect action: https://ngrok.com/docs/traffic-policy/actions/oidc/
- ngrok agent CLI (`ngrok http` flags): https://ngrok.com/docs/agent/cli/
- Vercel Deployment Protection: https://vercel.com/docs/deployment-protection
- Vercel Authentication: https://vercel.com/docs/deployment-protection/methods-to-protect-deployments/vercel-authentication
