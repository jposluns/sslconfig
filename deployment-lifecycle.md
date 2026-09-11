# Deploying safely over time: verify from outside, safe order, previews, teardown

This repository's per-service guides check TLS, binding, and authentication from inside the host and at the moment you set them up. Real exposure is judged from outside the host, and it drifts: a preview URL, a restored backup, or an upgrade can reopen something already closed. This guide is the lifecycle layer around the per-service checks.

## 1. Verify from outside, not just from the host

A `curl` or `ss -tlnp` run on the host itself cannot see a firewall the host does not know about, or a platform-level bypass like Docker's iptables rules ([docker.md](docker.md)). Verify from a second network: a phone hotspot, a cloud shell, or a second VM.

- Port-by-port: `for p in 22 80 443 3000 5432 6379 27017; do nc -vz -w 3 203.0.113.10 "$p"; done`, or a full sweep, `nmap -p- 203.0.113.10` (per the nmap reference, which documents `-p-` and `-p 1-65535` as equivalent port-range syntax; only scan hosts you own or are authorized to test).
- Check every address the service actually has, not just the one you remember configuring: the public IPv4 address, the public IPv6 address if the host has one, and any platform-assigned URL alongside your custom domain (a PaaS default subdomain, per [paas.md](paas.md), often stays reachable even when the custom domain is fronted). A scan of one address that misses the others is not a clean result, it is an incomplete one.
- Cross-reference what is already indexed about your IP with a passive internet-wide scanner such as Shodan or Censys; both build a continuously updated index of internet-connected hosts and services, so a stale exposure can show up there before you find it yourself ([cloud-firewalls.md](cloud-firewalls.md) covers the firewall rules this is checking).

## 2. Safe initialization order

Sequence a first deployment so nothing is reachable before it is safe to reach:

1. Create the owner or admin account's credentials and any signing secrets (session, JWT, or cookie-signing keys) per [authentication.md](authentication.md).
2. Set the registration policy (disable open self-registration, or restrict it to an allowlisted domain) before the service is reachable.
3. Put the fronting gate in place, TLS and any proxy-level authentication, per [free-certificates.md](free-certificates.md) and the fronting-layer guides.
4. Only then open network access.

The common failure this order prevents: an unclaimed setup wizard is a race to become admin, open to whoever reaches it first. After that, confirm the setup route itself is closed: restart the service and try hitting the initial-setup URL again; it must refuse to mint a second admin, not silently succeed.

## 3. Previews and clones get production posture

A preview deployment or a database clone is not lower stakes just because it is temporary. Vercel's Deployment Protection illustrates the gap: Standard Protection, available on every plan, gates preview and generated deployment URLs but leaves the production domain open by default; protecting production too needs the All Deployments scope (Pro and Enterprise) ([paas.md](paas.md); as of September 2026, per Vercel's Deployment Protection docs). Where the platform's own gate does not cover a hostname, front it the same way as production, for example a Cloudflare Access policy scoped to that preview hostname. Either way, treat a clone's data the same as the original: rotate any credential a clone inherited if the clone is less trusted than the source.

## 4. Teardown: DNS before the app, then revoke the rest

Retiring a deployment in the wrong order leaves a dangling DNS record pointing at a resource someone else can now claim (a subdomain takeover). Delete the DNS record (the `CNAME` or `A`/`AAAA`) before you delete or release the underlying app, load balancer, or IP. Then revoke what pointed at it: access policies (Cloudflare Access or equivalent), API tokens and service credentials scoped to that deployment ([machine-auth.md](machine-auth.md)), and database users created only for it.

## 5. Re-verify after anything changes

Rerun the outside-in checks in section 1 and the negative auth tests from [authentication.md](authentication.md) after an upgrade, a backup restore (which can reintroduce a default account or reset a feature flag), or any change to network policy or auth configuration. Monitor certificate expiry from outside the host too: a renewal cron can silently fail while the host's own view still looks fine, so an external check (a scheduled `openssl s_client` from another machine, or a third-party uptime/certificate monitor) catches what a local `certbot renew --dry-run` cannot.

## Common mistakes

- Verifying only the custom domain and forgetting the platform's own generated URL, which is often still reachable and unauthenticated.
- Deleting the app first and the DNS record later, leaving exactly the dangling-CNAME window a takeover needs.
- Trusting a local `certbot renew --dry-run` as proof that production certificates are actually renewing; it proves the client works, not that the last real renewal succeeded.

## Verify

```bash
# From a second network, not the host itself:
nmap -p- 203.0.113.10                                  # only the intended ports answer
nmap -p- 2001:db8::10                                  # same, over the public IPv6 address
curl -sI https://retired-preview.example.com/          # expect DNS failure or connection error
dig +short retired-preview.example.com                 # expect no record, not a dangling CNAME
openssl s_client -connect app.example.com:443 -servername app.example.com </dev/null \
  | openssl x509 -noout -enddate                        # run from outside on a schedule
```

## Sources (checked September 2026)

- nmap reference guide (port scanning syntax): https://nmap.org/book/man-briefoptions.html
- Shodan: https://www.shodan.io/
- Censys: https://censys.com/
- Vercel Deployment Protection (Standard Protection versus All Deployments scope): https://vercel.com/docs/deployment-protection
- Cloudflare Access policies: https://developers.cloudflare.com/cloudflare-one/policies/access/
