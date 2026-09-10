# Identity providers: hosted login and MFA for your app and your team

[authentication.md](authentication.md) says to prefer SSO or OIDC over local accounts and to enforce MFA at the identity provider. This guide names the providers, states what their free tiers include, and says who each fits. Wiring instructions live in [oidc-integration.md](oidc-integration.md); login placed in front of an app without code changes lives in [cloud-identity-proxies.md](cloud-identity-proxies.md) and [cloudflare.md](cloudflare.md).

Every tier and price below was read from the vendor's pricing page in September 2026 and will change; verify against the linked source before relying on it. Prices are USD list prices.

## 1. Decide which kind of identity you need

- **Workforce identity**: your team signs in with the organisation's existing accounts (Google Workspace, Microsoft Entra ID, Okta). Use it for admin panels, dashboards, internal tools, and anything only staff should reach. If your organisation already runs one of these, use it; do not buy a second directory.
- **Customer identity (CIAM)**: your application's own users sign up and sign in. Use a hosted provider rather than writing password storage, MFA, recovery, and rate limiting yourself.
- **Developer identity**: GitHub (or GitLab) login gates a tool for developers, optionally restricted to an organisation. Often the simplest correct choice for a solo or small project.

A login proves who the person is. **It does not decide whether they may use your app.** After any of the providers below, your application (or the fronting layer) still checks that the identity is on an allowlist: a tenant, a hosted domain, a group, or an explicit list of users. Accepting every Google or Microsoft account as "staff" is the recurring mistake; [oidc-integration.md](oidc-integration.md) covers the check.

## 2. Workforce providers

| Provider | Free tier and MFA facts (September 2026) | Fit |
|---|---|---|
| Microsoft Entra ID | Free tier, bundled with Azure and Microsoft 365 subscriptions, includes MFA and unlimited SSO to SaaS apps. Security defaults require every user to register MFA, enforce it for administrators, and prompt other users when Microsoft judges it necessary. P1 at $7 per user per month (annual commitment) adds Conditional Access, which is how you require MFA for everyone on every sign-in; P2 at $10 adds risk-based policies. | Any team already on Microsoft 365. |
| Google Workspace / Cloud Identity | Sign in with Google (OIDC) costs nothing per app. Enforcing 2-Step Verification for the whole organisation is an admin-console setting in Workspace or Cloud Identity. Cloud Identity Free exists; its default licence count was not read from a Google page for this guide, so check the source. | Any team already on Workspace. |
| Okta Workforce Identity | Okta Verify supports push, TOTP, and FastPass. A $1,500 annual contract minimum applies and there is no free production tier. | Only when your organisation already runs Okta. Not a purchase for a small project. |
| JumpCloud, OneLogin, Ping Identity | Workforce directories in the same class. Tiers not verified for this guide. | Existing enterprise estates only. |

## 3. Customer identity providers

| Provider | Free tier and MFA facts (September 2026) | Notes |
|---|---|---|
| Microsoft Entra External ID | Core features free for the first 50,000 monthly active users (MAU). SMS MFA and machine-to-machine (client credentials) authentication are billed per transaction as add-ons. | Keep the external (customer) tenant separate from the workforce tenant. |
| Google Identity Platform / Firebase Authentication | Email, password, and social sign-in are free in base Firebase Authentication. Upgrading to Authentication with Identity Platform gives 50,000 MAU and 50 SAML/OIDC MAU at no cost and unlocks TOTP MFA; SMS is billed per message. | Rules and RLS still decide data access: [firebase-supabase.md](firebase-supabase.md). |
| Auth0 (Okta) | Free plan: 25,000 MAU, passkeys, and unlimited social connections. **No MFA factors on Free**; Pro, Enterprise, and Adaptive MFA start at the paid plans. B2C Essentials is $35 per month for 500 MAU. | Passkeys on Free give a phishing-resistant single factor, which is not the same as MFA. |
| Amazon Cognito | Lite and Essentials tiers: 10,000 MAU free for direct sign-in and 50 MAU free for SAML/OIDC federation. Essentials is $0.015 per MAU beyond that and includes passkeys; Lite does not. SMS goes through SNS and is billed separately. | Pairs with Application Load Balancer authentication ([cloud-identity-proxies.md](cloud-identity-proxies.md)). |
| Clerk | Hobby plan: 50,000 monthly retained users (a user who returns at least 24 hours after signing up; not the same unit as MAU). **MFA is Pro and above** at $25 per month, or $20 billed annually. | "Free plan" does not mean MFA. |
| WorkOS AuthKit | User management free for the first 1,000,000 MAU. Enterprise SSO and Directory Sync are separate products at $125 per connection per month for the first 15 connections each. | Good app login; the per-connection fees are for selling to enterprises. |
| Supabase Auth | Free plan: 50,000 MAU with TOTP MFA included. Phone MFA is a paid add-on at $75 per month for the first project. | Enrolment is not enforcement: require the `aal2` level in your policies ([firebase-supabase.md](firebase-supabase.md)). |
| Stytch, Descope, Kinde, Frontegg, Logto, Hanko, Zitadel, Ory, SuperTokens, FusionAuth | Same class. Logto, Hanko, Zitadel, Ory, and SuperTokens are open source with hosted tiers; FusionAuth is proprietary with a free community edition. Tiers not verified for this guide. | Check the current pricing page before choosing. |

## 4. Developer identity

- **GitHub OAuth**: an OAuth app gives login for any GitHub user; restrict to members of your organisation or team in the app (or with oauth2-proxy, which has a GitHub provider with org and team restrictions). GitHub Actions OIDC is a different mechanism for workloads, covered in [machine-auth.md](machine-auth.md).
- **AWS IAM Identity Center**: the free workforce directory for your own AWS console and CLI access, and an OIDC source for Application Load Balancer authentication.

## 5. Self-hosted identity providers

Keycloak, authentik, Zitadel, Ory, and Authelia ([mfa.md](mfa.md)) give you OIDC and MFA without a vendor. They also give you a server to patch, back up, and keep highly available: a compromised or down identity provider takes every app with it. For a small project a hosted tier above is usually the smaller correct change.

## 6. MFA products

- **Duo**: the Duo Free edition covers up to 10 users with MFA and the Duo Mobile app. Its Authentication Proxy speaks RADIUS and LDAP, which retrofits MFA onto VPNs and services with RADIUS support.
- **Provider-native authenticators**: Microsoft Authenticator (Entra), Okta Verify (Okta), Google prompts (Google). Any RFC 6238 authenticator app works where a provider offers TOTP.
- **Hardware keys and passkeys**: YubiKey and other FIDO2 keys, and platform passkeys, are the phishing-resistant factor. Every provider in sections 2 and 3 supports WebAuthn at some tier; require it for administrators ([mfa.md](mfa.md)).

## 7. Poor fits for a small project

Zscaler Private Access, HashiCorp Boundary, Ping Identity, OneLogin, and Okta as a new purchase are enterprise products with enterprise pricing and sales-led onboarding. They are listed so an assistant recognises them when a customer already has them, not as recommendations.

## Verify

- With only the password (or only a social login) an administrator cannot reach an admin function once MFA is required at the provider; test with a fresh session.
- A valid account from outside your allowlist (a personal Gmail, a different tenant, a non-member GitHub user) is rejected after login, not admitted.
- The provider's audit log shows the sign-in; your application log shows the identity it received.

## Sources (checked September 2026)

- Microsoft Entra pricing (Free, P1, P2, External ID free MAU): https://www.microsoft.com/en-us/security/business/microsoft-entra-pricing
- Microsoft Entra External ID billing model: https://learn.microsoft.com/en-us/entra/external-id/external-identities-pricing
- Microsoft Entra security defaults: https://learn.microsoft.com/en-us/entra/fundamentals/security-defaults
- Google Cloud Identity pricing: https://cloud.google.com/identity/pricing
- Firebase pricing (Authentication and Identity Platform allowances): https://firebase.google.com/pricing
- Okta pricing: https://www.okta.com/pricing/
- Auth0 pricing: https://auth0.com/pricing
- Amazon Cognito pricing: https://aws.amazon.com/cognito/pricing/
- Clerk pricing: https://clerk.com/pricing
- WorkOS pricing: https://workos.com/pricing
- Supabase pricing: https://supabase.com/pricing
- Duo editions and pricing: https://duo.com/editions-and-pricing
- GitHub OAuth apps: https://docs.github.com/en/apps/oauth-apps
- AWS IAM Identity Center: https://docs.aws.amazon.com/singlesignon/latest/userguide/what-is.html
