# Sources for the README verification checklist

The [verification checklist](README.md#verification-checklist) names tools, status codes and services
without citing them inline, so the front page stays readable. The citations live here. Each entry is
numbered to match the checklist item it supports.

Every guide carries its own sources; this file covers only the checklist in `README.md`.

## Sources (checked September 2026)

1. **No plaintext listener on a public interface.** This citation covers the check, not the principle:
   [ss(8)](https://man7.org/linux/man-pages/man8/ss.8.html) documents the command and its `-tlnp`
   options. The principle, and what to bind instead, is in [host.md](host.md) and
   [common-mistakes.md](common-mistakes.md).

2. **HTTP redirects to HTTPS.** The permanent redirect status codes `301` and `308`, the temporary
   `302` and `307`, and the `Location` header field are defined in
   [RFC 9110, HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html). `curl -sI` issues a
   HEAD request and prints only the response headers: [curl manual](https://curl.se/docs/manpage.html).

3. **TLS works without `-k`.** `-k` (`--insecure`) disables curl's certificate verification, so a
   request that needs it has a certificate problem: [curl manual](https://curl.se/docs/manpage.html).

4. **Old protocols are refused.** `openssl s_client` and its `-tls1_1` protocol selector are
   documented at
   [openssl-s_client](https://docs.openssl.org/master/man1/openssl-s_client/). TLS 1.0 and TLS 1.1
   are formally deprecated by
   [RFC 8996, Deprecating TLS 1.0 and TLS 1.1](https://www.rfc-editor.org/rfc/rfc8996.html), which is
   why TLS 1.2 is the minimum throughout these guides. Read a failure carefully: a local OpenSSL build
   or configuration can refuse TLS 1.1 before any offer reaches the server
   ([OpenSSL config](https://docs.openssl.org/master/man5/config/)), so client inability and server
   rejection look alike and have to be told apart.

5. **Authentication is enforced.** The `401 Unauthorized` and `403 Forbidden` semantics, and the
   distinction between them, are defined in
   [RFC 9110 section 15.5.2](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.2).

6. **No default credentials and no committed secrets.** These are two claims and the citation covers
   only one: [gitleaks](https://github.com/gitleaks/gitleaks) documents installation and the
   pre-commit and CI usage patterns for the scanner the checklist names, which finds secrets committed
   to a repository. It cannot test a deployed service for vendor default accounts, so that half needs
   a product-specific login check. The requirement itself, and what to do once a secret has been
   committed, is in [secrets.md](secrets.md).

7. **ACME renewal is automated.** `certbot renew --dry-run` is documented in the EFF Certbot user
   guide: [Certbot, Renewing certificates](https://eff-certbot.readthedocs.io/en/stable/using.html).
   The citation covers the renewal command, not the existence or health of whatever invokes it: a
   passing dry run does not prove a systemd timer or cron job exists, so confirm that separately.
   Servers that manage renewal themselves document it directly:
   [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https) and
   [Traefik ACME](https://doc.traefik.io/traefik/https/acme/).

8. **External TLS scan.** [Qualys SSL Labs server test](https://www.ssllabs.com/ssltest/) for public
   endpoints, and [testssl.sh](https://github.com/testssl/testssl.sh) where the endpoint must not be
   submitted to a third party.

9. **A second factor on human logins.** Authenticator and multi-factor requirements are specified in
   [NIST SP 800-63B-4, Digital Identity Guidelines](https://pages.nist.gov/800-63-4/sp800-63b.html),
   which [supersedes the SP 800-63-3 edition](https://csrc.nist.gov/pubs/sp/800/63/B/4/final). Note
   what it actually requires: multi-factor at AAL2 and above, while at AAL1 it recommends offering a
   second factor rather than requiring one. The checklist item is this repository's own stronger rule,
   not a restatement of a NIST mandate. Which options are viable per tool is covered in
   [mfa.md](mfa.md).

10. **Probe from outside the deployment network.** Internet-wide scanners report what an outside
    observer saw at their last scan, not what is listening now: [Shodan](https://www.shodan.io/) and
    [Censys](https://censys.com/). They corroborate a direct probe from a second host and do not
    replace one, because a port published since the last observation will not appear in their data.
    Docker's published ports bypassing a host firewall is documented by Docker itself in
    [Packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
    The ordering and the outside-in method are in [deployment-lifecycle.md](deployment-lifecycle.md).

11. **Identity outside the allowed tenant, domain or group is denied.** A relying party must validate
    the ID token claims rather than trust them. The `iss` and `aud` claims are defined in
    [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html). The claims that
    carry tenant or hosted domain are provider specific and are not portable: Google's `hd` claim is
    documented in the
    [Google OpenID Connect reference](https://developers.google.com/identity/openid-connect/reference),
    and Microsoft Entra uses `tid` and `groups`, documented in its
    [ID token claims reference](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference).
    For proxy-enforced access see
    [Google Cloud IAP](https://docs.cloud.google.com/iap/docs/concepts-overview) and
    [cloud-identity-proxies.md](cloud-identity-proxies.md).

## Verify

This file is a citation list, not a configuration guide, so it has no setup steps of its own. To check
it is still sound: every link above resolves (the weekly link sweep covers them), and every numbered
entry still matches the correspondingly numbered item in the
[README verification checklist](README.md#verification-checklist). Nothing enforces that correspondence
mechanically, so confirm it by reading whenever the checklist changes.
