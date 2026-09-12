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
5. **Secrets never enter a command line.** A process's arguments are readable through `/proc/<pid>/cmdline`, which is what `ps` prints; on a default Linux that means every other user on the host, for as long as the process runs, and the command is then written to your shell history. A `hidepid` proc mount or a separate PID namespace narrows who can see it, neither is the default, and neither covers the history. Prefer a flag that reads from stdin (`htpasswd -i`, `docker login --password-stdin`, `gh auth login --with-token`), a file the tool reads itself (`~/.pgpass`, `curl --netrc`), or an environment variable where the tool offers nothing better. Where a value has to be typed, `read -rs` keeps it off the screen, and what `read` consumes is input rather than a command, so no shell records it.

   ```bash
   printf '%s' "$TOKEN" | docker login ghcr.io -u "$USER" --password-stdin
   ```

   There is no probe for this rule, and the obvious one is worse than none. `ps -eo args | grep -i 'password\|token\|secret'` finds only commands that spell the word out, such as `docker login --password hunter2`. It does not match `htpasswd -cbs .htpasswd admin Xk29fQ7LmVt3w9Zr`, or `mysql -pHunter2`, or `curl -u admin:hunter2`, because a real secret is a random string and `.htpasswd` does not contain the word "password". A snapshot also misses every short-lived process, which is most of them. A check that reads clean while the exposure is running is worse than no check, so this rule is enforced by review and by reaching for the stdin flag, not by grep.

6. **CI/CD secrets live in the platform's secret store** (for example GitHub Actions secrets), scoped to the jobs that need them, never echoed into logs or artefacts.

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

On every push, gitleaks must exit 0 with no findings (the `&& echo clean` then prints `clean`), and the grep must print nothing.

## Sources (checked September 2026)

- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- gitleaks: https://github.com/gitleaks/gitleaks
- trufflehog: https://github.com/trufflesecurity/trufflehog
- sops: https://github.com/getsops/sops and age: https://github.com/FiloSottile/age
- git-filter-repo: https://github.com/newren/git-filter-repo
- proc_pid_cmdline(5), for why a command line is readable by other users: https://man7.org/linux/man-pages/man5/proc_pid_cmdline.5.html
- docker login, for `--password-stdin`: https://docs.docker.com/reference/cli/docker/login/
- gh auth login, for `--with-token`: https://cli.github.com/manual/gh_auth_login
- htpasswd, for `-i` and what Apache says about `-b`: https://httpd.apache.org/docs/2.4/programs/htpasswd.html
