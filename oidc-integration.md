# OIDC login: wiring Google, Microsoft Entra, GitHub, and Okta into your app

Adding "Sign in with Google" takes an afternoon; the recurring defects are in what happens after the redirect comes back: an unvalidated ID token, an account matched by email, or an app that admits every Google or Microsoft account in existence because nobody checked whose it was. This guide gives the one flow every recipe shares, the exact claim to check per provider, the registration steps, and library pointers. Choosing a provider is covered in [identity-providers.md](identity-providers.md); login placed in front of an app without code changes is covered in [cloud-identity-proxies.md](cloud-identity-proxies.md).

## 1. The flow every recipe uses

Authorization code flow with PKCE from a server-side (confidential) client. RFC 9700 requires PKCE for public clients and recommends it for all others, web applications included; it requires exact string matching of redirect URIs at the authorization server; and it says clients should not use the implicit grant (`response_type=token`).

1. Register the exact callback URL at the provider (scheme, host, path, trailing slash). Prefix or wildcard matching is what makes redirect-based code theft work.
2. Send a random `state` bound to the browser session and a random `nonce` on every authorization request, plus `code_challenge` with `code_challenge_method=S256`. Scopes: `openid email profile`.
3. Exchange the code at the token endpoint from the server, with the client secret. Never from the browser.
4. Validate the ID token before trusting any claim (OpenID Connect Core section 3.1.3.7): the signature against the key set at the provider's `jwks_uri`, using an algorithm you pinned (Core says RS256 unless you registered another; the discovery document lists the provider's `id_token_signing_alg_values_supported`) rather than whatever the token header names; `iss` exactly equals the issuer you configured; `aud` contains your client ID; `exp` is in the future; `nonce` equals the one you sent.
5. Start a server-side session and give the browser only a session cookie marked `Secure`, `HttpOnly`, and `SameSite` per [authentication.md](authentication.md). Do not put ID or access tokens in `localStorage` or a script-readable cookie; nothing in the browser needs them.
6. Link the identity to a local account by the pair (issuer, `sub`). OpenID Connect Core section 5.7 says `email`, `phone_number`, and `preferred_username` are not guaranteed unique and may change; Google and Microsoft document the same for their `email` claims. Matching by email alone lets a re-used or unverified address take over an account.
7. Logout: destroy the server-side session and expire the cookie; where the discovery document lists an `end_session_endpoint`, also redirect there with `id_token_hint` and a registered `post_logout_redirect_uri` (Entra: `/oauth2/v2.0/logout`).

The discovery document at `<issuer>/.well-known/openid-configuration` supplies the endpoints and `jwks_uri`; its `issuer` value must be identical to the prefix you fetched it from. Every library in section 4 reads it for you.

## 2. Login is not authorisation

The provider proves who the person is. Whether they may use your app is your check, run after token validation and before the session exists, against an allowlist. The claim differs per provider:

- **Google**: the `hd` claim in the ID token must equal your Workspace domain (`example.com`). The `hd` request parameter only optimises the account picker; Google's documentation says not to rely on it for access control and to validate the returned `hd` claim. Treat a missing `hd` claim as a rejection.
- **Microsoft Entra**: the `tid` claim must be your tenant ID and `iss` must be `https://login.microsoftonline.com/<tenant-id>/v2.0`. Register the app as **Single tenant only** when only your organisation signs in. The `organizations` authority accepts any Entra tenant and `common` also accepts personal accounts; the issuer then varies per tenant, so an app on those authorities that does not check `tid` (or the GUID in `iss`) admits every Microsoft account. Microsoft documents `email` and `preferred_username` as mutable and unfit for authorisation; key the local account on `oid` or `sub` plus `tid`.
- **GitHub**: GitHub OAuth apps speak OAuth 2.0, not OpenID Connect; there is no discovery document and no ID token. After the token exchange call `GET https://api.github.com/user` for the identity, then check `GET /user/memberships/orgs/<org>` (200 with `"state": "active"` means a member; 404 means not affiliated) or a team with `GET /orgs/<org>/teams/<team_slug>/memberships/<username>` (200 with `"state": "active"`; the REST reference documents `pending` for an unaccepted invitation, and 404 means no membership). Both need the `read:org` scope. Key the local account on the numeric `id` from `/user`, not the `login`.
- **Okta**: add a `groups` claim to the ID token (org authorization server: **Applications > Applications >** your app **> Sign On**, edit the OpenID Connect ID Token section, filter **Matches regex** `.*`; the client must also request the `groups` scope) and require membership of a named group. The claim holds at most 100 groups and the request fails beyond that; use a narrower filter in large orgs.

The default for an identity that passes none of these is to reject and log it, never to create a pending account an admin later forgets to review.

## 3. Register the app at each provider

The client secret is a secret: environment variable or secret manager, never a repository or an image ([secrets.md](secrets.md)). Substitute the callback path your library expects for `https://app.example.com/auth/callback`.

- **Google**: Google Cloud console **Clients** page (`https://console.developers.google.com/auth/clients`); create an OAuth client and add the redirect URI. The match is exact, including scheme, case, and trailing slash. Discovery: `https://accounts.google.com/.well-known/openid-configuration`; `iss` is `https://accounts.google.com` or `accounts.google.com`.
- **Microsoft Entra**: Microsoft Entra admin center, **Entra ID > App registrations > New registration**; under **Supported account types** choose **Single tenant only** unless you are building for other organisations. Then **Authentication > Add a platform > Web** and add the redirect URI. Record the Application (client) ID and create a client secret. Discovery: `https://login.microsoftonline.com/<tenant>/v2.0/.well-known/openid-configuration` with `<tenant>` your directory (tenant) ID; `common` or `organizations` only together with the `tid` check above.
- **GitHub**: profile picture **> Settings > Developer settings > OAuth apps > New OAuth App**; set the Authorization callback URL. Authorize at `https://github.com/login/oauth/authorize` with `client_id`, `redirect_uri`, `scope=read:user read:org`, `state`, and PKCE (`code_challenge` with `code_challenge_method=S256`; GitHub does not accept `plain`); exchange at `https://github.com/login/oauth/access_token` with `client_id`, `client_secret`, `code`, the `code_verifier` that produced the challenge, and the same `redirect_uri`. Always send `redirect_uri`; when it is absent GitHub uses the first registered callback. Apps that had a single callback URL before August 3, 2026 keep wildcard matching for it, which accepts any subdirectory path on the same host; disable wildcard matching in the app settings so the callback must match exactly.
- **Okta**: Admin Console, **Applications and Resources > Applications > Create App Integration**, sign-in method **OIDC - OpenID Connect**, type **Web Application**; set the sign-in and sign-out redirect URIs and the assignment (Okta's guide allows everyone in the org; narrow it to a group). Client ID and secret are on the **General** tab under Client Credentials. Discovery: `https://<org>.okta.com/.well-known/openid-configuration` for the org authorization server, `https://<org>.okta.com/oauth2/<authorizationServerId>/.well-known/openid-configuration` for a custom one; `iss` equals that prefix.

## 4. Libraries

Use a maintained library; do not hand-parse JWTs. The snippets are from each library's documentation; the section 2 check is yours to add.

- **Node, [openid-client](https://github.com/panva/openid-client)** (`npm install openid-client`):
  ```javascript
  let config = await client.discovery(server, clientId, clientSecret)
  let code_verifier = client.randomPKCECodeVerifier()
  let code_challenge = await client.calculatePKCECodeChallenge(code_verifier)
  let state = client.randomState()
  let redirectTo = client.buildAuthorizationUrl(config, { redirect_uri, scope, code_challenge, code_challenge_method: 'S256', state })
  // callback:
  let tokens = await client.authorizationCodeGrant(config, currentUrl, { pkceCodeVerifier: code_verifier, expectedState: state })
  ```
- **Node, [Auth.js](https://authjs.dev/)** (`npm install next-auth@beta` for Next.js; SvelteKit and Express integrations exist): providers `next-auth/providers/google`, `github`, `okta`, and `microsoft-entra-id`, configured through `AUTH_<PROVIDER>_ID`, `AUTH_<PROVIDER>_SECRET`, and for Okta and Entra `AUTH_<PROVIDER>_ISSUER`; callbacks land on `/api/auth/callback/<provider>`. Sessions are an encrypted JWT, or a database session ID, in an `HttpOnly` cookie. With the JWT strategy, sign-out destroys the cookie but the token itself stays valid until `exp` unless your server keeps a blocklist (Auth.js documents this limitation); use database sessions where immediate invalidation matters. Set `AUTH_MICROSOFT_ENTRA_ID_ISSUER` to your tenant's `/v2.0` issuer: the documented default is `common`. Put the section 2 check in the `signIn` callback.
- **Python, [Authlib](https://docs.authlib.org/)** (`pip install Authlib`; Flask, Django, Starlette, FastAPI):
  ```python
  oauth.register('google', client_id='YOUR_CLIENT_ID', client_secret='YOUR_CLIENT_SECRET',
      server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
      client_kwargs={'scope': 'openid profile email'})
  # login:    return oauth.google.authorize_redirect(redirect_uri)
  # callback: token = oauth.google.authorize_access_token(); claims = token['userinfo']
  ```
- **Go, [go-oidc](https://pkg.go.dev/github.com/coreos/go-oidc/v3/oidc)** (`github.com/coreos/go-oidc/v3/oidc`):
  ```go
  provider, err := oidc.NewProvider(ctx, "https://accounts.google.com")
  verifier := provider.Verifier(&oidc.Config{ClientID: clientID})
  idToken, err := verifier.Verify(ctx, rawIDToken)   // signature, issuer, audience, expiry
  ```
  The package documents that it does not check the nonce value: compare `idToken.Nonce` to the one you stored. Leave `SkipIssuerCheck` off.

## 5. Where MFA comes from

Your app does not run the second factor; the provider does, under its policy: Conditional Access in Entra (**Entra ID > Conditional Access > Policies**, grant **Require authentication strength**; a P1 feature per [identity-providers.md](identity-providers.md)), 2-Step Verification in the Google Admin console (**Security > Authentication > 2-step verification**, Enforcement **On**), and authentication policies plus the global session policy in Okta. Ordering and options in [mfa.md](mfa.md).

An app can additionally refuse a session whose ID token shows no second factor, where the provider documents the claim. Okta's `amr` array carries values such as `pwd`, `mfa`, `otp`, and `hwk`. For Entra, check the ID token claims reference and the optional claims reference for the `amr` claim and its `mfa` value before relying on it. For Google, enforce 2SV in Workspace; no ID token MFA claim was verified for this guide. GitHub OAuth has no ID token, so MFA is whatever the organisation requires of its members.

## Verify

```bash
curl -s https://accounts.google.com/.well-known/openid-configuration | jq -r '.issuer, .jwks_uri'
curl -sI https://app.example.com/admin | head -1        # 302 to login or 401, never 200
```

Negative tests matter more than the happy path:

- Sign in with a valid account outside the allowlist (a personal Gmail, another Entra tenant, a GitHub user outside the org, an Okta user outside the group): the provider authenticates, your app refuses and logs the identity.
- Edit `redirect_uri` in the authorization URL (add a path segment or change the host): the provider shows an error and never redirects.
- Change `state` on the callback URL: your app rejects the callback.
- Replay a captured ID token after `exp`, or one issued to a different client ID at the same provider: your callback rejects it.
- Log out, then reload a protected page: it redirects to login. With database sessions the old session cookie no longer works; with JWT sessions it works until `exp`, so use database sessions or a revocation check where immediate invalidation matters.

## Sources (checked September 2026)

- RFC 9700, OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/info/rfc9700/
- OpenID Connect Core 1.0 (ID token validation 3.1.3.7, claim stability 5.7): https://openid.net/specs/openid-connect-core-1_0.html ; Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html ; RP-Initiated Logout 1.0: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- Google OpenID Connect (discovery URL, `hd`, `sub` versus `email`, token validation): https://developers.google.com/identity/openid-connect/openid-connect
- Google Workspace: deploy 2-Step Verification: https://knowledge.workspace.google.com/admin/security/deploy-2-step-verification
- Microsoft identity platform: register an application: https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app ; OpenID Connect (discovery, `{tenant}` values, redirect URI, sign-out): https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc
- Microsoft identity platform: ID token claims reference (`tid`, `iss`, `oid`, `sub`, `email`): https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference ; optional claims reference (`amr`, `mfa` value): https://learn.microsoft.com/en-us/entra/identity-platform/optional-claims-reference
- Microsoft Entra Conditional Access: require MFA for all users: https://learn.microsoft.com/en-us/entra/identity/conditional-access/policy-all-users-mfa-strength
- GitHub OAuth apps: authorizing: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps ; creating: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app ; scopes: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps
- GitHub REST: organization members: https://docs.github.com/en/rest/orgs/members ; team members: https://docs.github.com/en/rest/teams/members
- Okta: OAuth 2.0 and OpenID Connect overview: https://developer.okta.com/docs/concepts/oauth-openid/ ; OIDC API reference (discovery, issuer, `amr`, `groups`): https://developer.okta.com/docs/api/openapi/okta-oauth/guides/overview
- Okta: add a groups claim: https://developer.okta.com/docs/guides/customize-tokens-groups-claim/main/ ; sign users in to your web application: https://developer.okta.com/docs/guides/sign-into-web-app-redirect/-/main/ ; policies concept: https://developer.okta.com/docs/concepts/policies/
- openid-client: https://github.com/panva/openid-client
- Auth.js (installation, providers): https://authjs.dev/ ; session strategies (a JWT cannot be expired early without a blocklist): https://authjs.dev/concepts/session-strategies
- Authlib Flask client: https://docs.authlib.org/en/stable/oauth2/client/web/flask.html
- go-oidc: https://pkg.go.dev/github.com/coreos/go-oidc/v3/oidc
