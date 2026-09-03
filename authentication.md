# Strong authentication baseline

TLS without authentication leaves a service open to the whole internet over an encrypted channel. These rules apply to every service in this repository's guides. `must` marks a requirement; `should` marks a recommendation.

## Rules

1. **Deny by default.** Every endpoint that is not deliberately public must require authentication, including APIs, health dashboards, admin panels, metrics, and message queues. Publish an explicit list of the paths that are public; everything else authenticates.
2. **No default or shared credentials.** Change or disable every vendor default account before exposure. Each human gets an individual account; each service gets its own credential. Never ship credentials in code, containers, or documentation.
3. **TLS first.** Credentials must only cross the network inside TLS. HTTP basic authentication and bearer tokens are acceptable only over HTTPS, because both send the secret with every request.
4. **Hash passwords with a modern algorithm.** Store only argon2id or bcrypt hashes (per current OWASP guidance; scrypt and correctly parameterized PBKDF2 are also acceptable). Never store plaintext, and never use unsalted or fast hashes such as MD5 or SHA-256 for passwords.
   - Node.js: `bcrypt` or `argon2` packages.
   - Python: `argon2-cffi` or `bcrypt`.
   - Shell (for htpasswd files): `htpasswd -B` (bcrypt).
5. **Generate secrets randomly and keep them out of the repository.**
   ```bash
   openssl rand -base64 32
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
   Load secrets from environment variables or a secret manager. Add `.env` to `.gitignore` before the first commit, and scan the repository for leaked secrets (for example with gitleaks) before pushing. A secret that has reached a public repository, a chat, or a log is compromised: rotate it, since deleting the file does not unpublish it.
6. **Prefer SSO/OIDC over local accounts** where the product supports it, and enable MFA wherever available. [Cloudflare Access](cloudflare.md) puts SSO or one-time-PIN login in front of any web app without changing the app.
7. **Scope machine access.** API clients get their own tokens with the least privilege the task needs, not an admin password. Support and exercise rotation; set expiry where the platform allows it.
8. **Harden sessions.** Set cookies `Secure`, `HttpOnly`, and `SameSite` (`Lax` or `Strict`), sign them with a strong random secret, and expire them. Invalidate sessions on password change.
9. **Rate-limit authentication endpoints** and lock or delay after repeated failures. Log authentication successes and failures with source address and account, and keep the logs long enough to investigate an incident. fail2ban is a low-effort control for SSH and login panels on Linux hosts.
10. **Least privilege everywhere.** Separate admin from daily-use accounts, and give database and OS service accounts only the rights the application uses.

## Quick checks

- Unauthenticated `curl` against a protected path returns `401`, `403`, or a login redirect, never data.
- `git log -p | grep -iE 'password|secret|api[_-]?key'` over a new repository comes back empty (a scanner does this better; use one).
- The user store contains no account named `admin`, `test`, or `demo` with a known or empty password.

## Sources (checked September 2026)

- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
