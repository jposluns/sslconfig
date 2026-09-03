# Secrets: keeping keys out of repositories

Leaked API keys and credentials in public repositories are the most common security incident in AI-assisted projects, and scanners harvest fresh commits within minutes. [authentication.md](authentication.md) states the baseline; this guide covers the handling.

## Rules

1. **Secrets never enter version control.** Add `.env`, `*.key`, and `*.pem` to `.gitignore` before the first commit. Load secrets from environment variables or a secret manager (AWS Secrets Manager, Google Secret Manager, Azure Key Vault, or your platform's store per [paas.md](paas.md)).
2. **Secrets never enter images or build logs.** `ENV` and `ARG` values in a Dockerfile ship with the image and appear in `docker history`; pass secrets at runtime instead ([docker.md](docker.md)). Do not print secrets in application or CI logs.
3. **Generate secrets randomly** (`openssl rand -base64 32`; `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`), 1 per service and environment, never shared between staging and production.
4. **Scan before every push.** [gitleaks](https://github.com/gitleaks/gitleaks) or [trufflehog](https://github.com/trufflesecurity/trufflehog) as a pre-commit hook and in CI:
   ```bash
   gitleaks git .          # scans the repository history
   gitleaks dir .          # scans the working tree
   ```
5. **CI/CD secrets live in the platform's secret store** (for example GitHub Actions secrets), scoped to the jobs that need them, never echoed into logs or artefacts.

## When a secret leaks

Order matters:

1. **Rotate first.** Revoke the exposed credential at its provider and issue a new one. A secret that reached a public repository, a chat, a log, or a paste is compromised even if deleted seconds later; scrapers and forks already have it.
2. Only then clean the history if required (for example with [git-filter-repo](https://github.com/newren/git-filter-repo)), understanding that cleaning is hygiene, never containment: it does not unpublish anything.
3. Check provider logs for use of the leaked credential during the exposure window.

## Encrypting secrets that must be versioned

When a team needs configuration secrets in git (for example GitOps deployments), encrypt them: [sops](https://github.com/getsops/sops) with [age](https://github.com/FiloSottile/age) keys encrypts the values inside YAML/JSON/ENV files while leaving the structure diffable. The decryption key itself stays out of the repository.

## Verify

```bash
gitleaks git . && echo clean
grep -rn "sk-\|AKIA\|-----BEGIN" --include="*.py" --include="*.js" --include="*.ts" --include="*.env" . | grep -v node_modules   # crude but fast
```

Both must come back empty on every push.

## Sources (checked September 2026)

- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- gitleaks: https://github.com/gitleaks/gitleaks
- trufflehog: https://github.com/trufflesecurity/trufflehog
- sops: https://github.com/getsops/sops and age: https://github.com/FiloSottile/age
- git-filter-repo: https://github.com/newren/git-filter-repo
