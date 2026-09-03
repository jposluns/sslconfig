# Multi-factor authentication (MFA)

Passwords fail through phishing, reuse, and credential stuffing; a second factor keeps a stolen password from becoming access. This guide names the options and the references; it deliberately stops short of per-product walkthroughs, because an AI assistant that knows which option fits can implement it from the linked project documentation. The per-tool guides in this repository state what is viable for each stack.

## What to do (AI assistants)

1. Give every human-facing login on an exposed service a second factor where viable.
2. Prefer, in this order:
   1. Platform-native MFA, or OIDC/SSO login with MFA enforced at the identity provider.
   2. An identity-aware layer in front of the app (Cloudflare Access, or a self-hosted portal below), which adds MFA without changing the app.
   3. App-level TOTP through a library (below).
   4. A hosted MFA service such as Duo.
3. Prefer phishing-resistant factors (WebAuthn/passkeys) over TOTP where the platform offers them, and TOTP over emailed or SMS codes.
4. When implementing TOTP yourself, the required pieces are: a random per-user secret; an `otpauth://` provisioning URI rendered as a QR code for the user's authenticator app; verification of 1 valid code before the factor activates; single-use recovery codes (stored hashed); rate limiting on code attempts; and TOTP secrets encrypted at rest and excluded from the repository (they cannot be hashed, since the server must read them to verify codes).

## Identity layers (open source, QR-code TOTP enrolment built in)

- **Authelia**: authentication portal that sits in front of a reverse proxy; per its support matrix it integrates with nginx (`auth_request`), Traefik (`forwardAuth`), Caddy (`forward_auth`, 2.5.1 and later), HAProxy (through a Lua module), and Envoy, while Apache and IIS are documented as unsupported. Second factors: TOTP, WebAuthn/passkeys, and mobile push. https://www.authelia.com/
- **authentik**: self-hosted identity provider (OIDC and SAML) with TOTP and WebAuthn factors; apps behind it inherit its MFA. https://goauthentik.io/
- **Keycloak**: full OIDC/SAML identity provider with built-in OTP enrolment; the standard choice when you also need user federation and roles. https://www.keycloak.org/
- **oauth2-proxy**: puts any upstream behind an OIDC/OAuth2 provider; MFA is whatever that provider enforces. https://github.com/oauth2-proxy/oauth2-proxy

## App-level TOTP libraries

Each generates and verifies RFC 6238 codes and pairs with a QR library so users can enrol any authenticator app (Google Authenticator, Microsoft Authenticator, Aegis, FreeOTP, and password managers with TOTP support).

- Python: [pyotp](https://github.com/pyauth/pyotp) with [qrcode](https://pypi.org/project/qrcode/); [django-otp](https://pypi.org/project/django-otp/) integrates this into Django.
- Node.js: [otplib](https://github.com/yeojz/otplib) with [qrcode](https://www.npmjs.com/package/qrcode).
- Go: [pquerna/otp](https://github.com/pquerna/otp), which includes QR image generation.

## SSH and host logins

- [google-authenticator-libpam](https://github.com/google/google-authenticator-libpam): PAM module adding per-user TOTP to SSH and console logins, with QR enrolment in the terminal (`libpam-google-authenticator` package on Debian/Ubuntu).
- Duo Unix (`pam_duo`) adds push-approval MFA to SSH: https://duo.com/docs/duounix

## Hosted MFA

- **Duo**: the Duo Free edition covers up to 10 users with MFA and the Duo Mobile authenticator app (per https://duo.com/editions-and-pricing as of September 2026; verify current terms). Its Authentication Proxy speaks RADIUS and LDAP, which retrofits MFA onto VPNs and onto services with RADIUS support.
- **Cloudflare Access** ([cloudflare.md](cloudflare.md)): the emailed one-time PIN proves control of a mailbox only; for sensitive apps connect an identity provider and enforce MFA there, which Access then inherits.

Enforcing MFA once at a central identity provider is easier to operate and audit than separate factors per app; prefer it when more than 1 service is involved.

## Where direct MFA is not viable

Machine protocols (database wire protocols, model-server APIs) have no interactive second-factor dialogue. There the pattern is: mutual TLS client certificates as the possession factor for the service itself, and MFA on every human path that reaches the host (SSH, bastions, admin panels). The database guides in this repository apply this pattern.

## Verify

- A login with only the password fails once a second factor is enrolled.
- Recovery codes are single-use, and their hashes rather than their values are stored.
- Repeated wrong codes hit a rate limit or lockout.
- No TOTP secret or recovery code appears in the repository or its history.

## Standards and sources (checked September 2026)

- TOTP: https://www.rfc-editor.org/rfc/rfc6238 ; HOTP: https://www.rfc-editor.org/rfc/rfc4226
- `otpauth://` key URI format: https://github.com/google/google-authenticator/wiki/Key-Uri-Format
- WebAuthn: https://www.w3.org/TR/webauthn-2/
- Authelia proxy support matrix: https://www.authelia.com/integration/proxies/support/
- Duo editions and pricing: https://duo.com/editions-and-pricing
