# Machine identity: API keys, client credentials, mutual TLS, and workload identity

Machines cannot do MFA, so their credentials are long-lived by default, and long-lived credentials leak through repositories, container images, and logs. The fix is scoped, short-lived, and where possible credential-free access: a CI job or workload that holds no key cannot leak one. [authentication.md](authentication.md) sets the baseline and [secrets.md](secrets.md) covers handling and leak response; this guide covers the credential types themselves, from the weakest to the one that removes the secret entirely.

## 1. API keys and bearer tokens

The simplest machine credential and the one that leaks most. When your service issues or accepts them:

- One key per client and per environment, generated randomly (commands in [secrets.md](secrets.md)), with the least privilege that client's task needs. A shared key cannot be revoked for one client without breaking the rest.
- Give every key an expiry and rotate on a schedule, with a short overlap during which both keys work, so rotation is routine rather than an outage.
- Send keys only in a header (`Authorization: Bearer ...`) over TLS, never in a URL. RFC 6750 makes TLS mandatory for bearer tokens and says they "SHOULD NOT be passed in page URLs", because URLs land in browser history, proxy logs, and server logs.
- Compare the presented key in constant time: `hmac.compare_digest()` in Python, `crypto.timingSafeEqual()` in Node.js (both arguments must have the same byte length). A plain `==` stops at the first differing byte and leaks timing.
- Where the service only needs to verify the key, store a hash of it and compare against the hash of the presented key. Show the plaintext once at creation; a database dump then yields no usable keys.

## 2. OAuth 2.0 client credentials

For service-to-service calls to an identity provider or an API that supports it, use the client credentials grant (RFC 6749 section 4.4): the client authenticates to the token endpoint with `grant_type=client_credentials` and receives a short-lived access token; no refresh token is issued, and the grant is for confidential clients only. Request the narrowest `scope` (or audience, where the provider uses one) the call needs, so a stolen token is bounded in time and reach, and validate the audience on the receiving side ([oidc-integration.md](oidc-integration.md)). The client secret is still a long-lived credential: store it per section 5, or replace it with a federated credential per section 4 where the provider allows. Hosted providers may bill this flow: Microsoft Entra External ID charges machine-to-machine authentication per transaction as an add-on, so a token refresh every hour is roughly 720 billable transactions a month (as of September 2026; tiers in [identity-providers.md](identity-providers.md)).

## 3. Mutual TLS

A client certificate from your own internal CA ([self-signed.md](self-signed.md)) is a possession factor for a machine: the private key never crosses the wire, and a replaced client key cuts off one client, not all of them. Replacing a key does not by itself reject the old certificate: revoke it (a CRL or OCSP the server checks), remove it from an explicit allowlist, or let it expire, and test that the old credential is refused (RFC 5280 covers revocation). It is not human MFA, and [mfa.md](mfa.md) still applies to every human path that reaches the host. The service guides already carry the server-side directives: `ssl_verify_client on` in [nginx.md](nginx.md), `SSLVerifyClient require` in [apache.md](apache.md), `clientcert=verify-full` in [postgresql.md](postgresql.md), `REQUIRE X509` in [mysql.md](mysql.md), `tls-auth-clients yes` in [redis.md](redis.md), `ssl_options.fail_if_no_peer_cert = true` in [rabbitmq.md](rabbitmq.md), and `require_certificate true` in [mosquitto.md](mosquitto.md). Issue one certificate per client, keep the CA key off the servers it signs for, and set short lifetimes so a lost key expires rather than lingers.

## 4. Workload identity federation: no long-lived cloud keys in CI

A GitHub Actions job can request a short-lived OIDC token (`permissions: id-token: write`) issued by `https://token.actions.githubusercontent.com` with a `sub` claim such as `repo:octo-org/octo-repo:ref:refs/heads/main` or `repo:octo-org/octo-repo:environment:prod`. The cloud provider trusts that issuer and exchanges the token for temporary credentials, so the repository stores no cloud key at all. The key point is the trust condition: every GitHub repository uses the same issuer, so a federation trust that admits any repository is a leaked key with extra steps. Condition on the exact repository and on the branch or environment.

**AWS.** The `aws-actions/configure-aws-credentials` step takes `role-to-assume` and `aws-region` and sends `sts.amazonaws.com` as the audience by default. The role's trust policy does the restricting:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": { "StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "repo:example-org/example-repo:ref:refs/heads/main"
    } }
  }]
}
```

IAM refuses a trust policy whose `sub` condition is absent or only a wildcard, and AWS warns that a condition wider than your organization lets "GitHub Actions from organizations or repositories outside of your control" assume the role.

**Google Cloud.** Create a Workload Identity Pool provider with `gcloud iam workload-identity-pools providers create-oidc` using `--issuer-uri="https://token.actions.githubusercontent.com"`, an `--attribute-mapping` such as `google.subject=assertion.sub,attribute.repository=assertion.repository`, and an `--attribute-condition` such as `assertion.repository_owner == 'example-org'`. Then grant `roles/iam.workloadIdentityUser` on the service account to `principalSet://iam.googleapis.com/<POOL_RESOURCE_NAME>/attribute.repository/example-org/example-repo`, which names the exact repository. Google recommends conditions on the numeric `repository_id` and `repository_owner_id` claims over names, since a name can be re-registered by someone else. The `google-github-actions/auth` step takes `workload_identity_provider` and `service_account`.

**Azure.** Add a federated credential on the app registration or user-assigned managed identity with issuer `https://token.actions.githubusercontent.com`, subject `repo:example-org/example-repo:environment:production` (or `repo:example-org/example-repo:ref:refs/heads/main`), and audience `api://AzureADTokenExchange`, for example `az ad app federated-credential create --id <APP_ID> --parameters credential.json`. Wildcards are not supported and the subject must match exactly; a wrong subject is accepted at creation and fails only at exchange time, with no error message. The `azure/login` step then needs only `client-id`, `tenant-id`, and `subscription-id`; there is no client secret to store.

Two cautions. GitHub documents an immutable default `sub` format that includes owner and repository IDs for repositories created after July 15, 2026 (as of September 2026), so read the claim your token actually carries before writing the condition. And pin every action to a release tag or commit SHA. Inside a cluster, [SPIFFE/SPIRE](https://spiffe.io/) is the equivalent: attested, short-lived identities issued to workloads without a stored secret.

## 5. Store the machine credentials that must exist

API keys, client secrets, and client-certificate keys that cannot be federated away go in a secret manager or the platform's own store ([secrets.md](secrets.md)): AWS Secrets Manager (https://aws.amazon.com/secrets-manager/), Google Cloud Secret Manager (https://docs.cloud.google.com/secret-manager/docs/overview), Azure Key Vault (https://azure.microsoft.com/en-us/products/key-vault), HashiCorp Vault (https://developer.hashicorp.com/vault) or OpenBao, its open-source fork under the Linux Foundation (https://openbao.org/), Infisical (https://infisical.com/), Doppler (https://www.doppler.com/), 1Password Secrets Automation (https://www.1password.dev/secrets-automation/), and Bitwarden Secrets Manager (https://bitwarden.com/products/secrets-manager/). The workload should authenticate to the store with its platform identity (an instance role, a managed identity, or the federation above) so the store does not become one more long-lived key.

## Verify

- A key issued to another client or environment is rejected: `curl -sS -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer <staging-key>" https://api.example.com/v1/status` against production returns `401` or `403`, never `200`.
- A revoked or expired key or token is rejected the same way, and the rejection appears in the service log with the client identity.
- The CI job holds no long-lived cloud key: the repository's Actions secrets contain no `AWS_SECRET_ACCESS_KEY`, service-account JSON, or Azure client secret, and the workflow declares `permissions: id-token: write`.
- The federation trust condition names the exact repository: the AWS `sub` condition, the Google `attribute.repository` binding, and the Azure `subject` each contain `example-org/example-repo`, and none is `repo:example-org/*` or a bare wildcard.
- `gitleaks git .` and `docker history <image>` show no key ([secrets.md](secrets.md), [docker.md](docker.md)).

## Sources (checked September 2026)

- OAuth 2.0 client credentials grant (RFC 6749 section 4.4): https://datatracker.ietf.org/doc/html/rfc6749#section-4.4
- OAuth 2.0 bearer token usage, TLS and URL rules (RFC 6750 sections 5.2 and 5.3): https://www.rfc-editor.org/info/rfc6750/
- Python `hmac.compare_digest`: https://docs.python.org/3/library/hmac.html ; Node.js `crypto.timingSafeEqual`: https://nodejs.org/api/crypto.html
- Microsoft Entra External ID billing model (M2M add-on): https://learn.microsoft.com/en-us/entra/external-id/external-identities-pricing
- GitHub: about security hardening with OpenID Connect (claims, subject formats): https://docs.github.com/en/actions/concepts/security/openid-connect
- GitHub: configuring OpenID Connect in AWS: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws ; in Google Cloud: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-google-cloud-platform ; in Azure: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure
- AWS IAM: configuring a role for the GitHub OIDC identity provider (trust policy, `sub` restriction): https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_create_for-idp_oidc.html
- aws-actions/configure-aws-credentials: https://github.com/aws-actions/configure-aws-credentials
- Google Cloud: Workload Identity Federation with deployment pipelines (GitHub Actions attribute mapping and conditions): https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines ; attribute conditions: https://docs.cloud.google.com/iam/docs/workload-identity-federation
- google-github-actions/auth: https://github.com/google-github-actions/auth
- Microsoft Entra: workload identity federation: https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation ; creating the trust on an app (subject formats, audience, exact match): https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust
- Azure: authenticate from GitHub Actions by OpenID Connect (`azure/login`): https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure-openid-connect
- SPIFFE and SPIRE: https://spiffe.io/ and https://spiffe.io/docs/latest/spire-about/
- RFC 5280 (certificate revocation): https://www.rfc-editor.org/info/rfc5280/
- Secret manager vendor pages: linked inline in section 5.
