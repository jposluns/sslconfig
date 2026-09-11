# Egress control and cloud metadata: keeping an agent from exfiltrating credentials

An AI agent, RAG fetcher, or webhook handler that retrieves URLs can be steered by a prompt injection into requesting the cloud metadata endpoint or an internal service instead of the URL it was meant to fetch. Making the fetcher refuse that request is application security; this guide covers the deployment-side backstop, metadata hardening so the endpoint rejects an unqualified request, plus default-deny egress so the request never leaves the workload at all.

## AWS: require IMDSv2 and cap the hop limit

The instance metadata service listens on `169.254.169.254`. IMDSv2 requires a session token obtained with a
`PUT` before any `GET` succeeds. By default, the response to that `PUT`, the token itself, has a hop limit
of 1 at the IP protocol level: the token cannot travel more than one network hop back to the requester (per
the AWS instance metadata service documentation). A containerized application sitting one hop from the
host, for example behind the container network's own routing, will not receive the token and so cannot
complete an IMDSv2 request; this is a limit on the token response reaching that far, not a guarantee that no
proxy anywhere can reach the metadata service itself. Enforce IMDSv2 and keep the hop limit at 1:

```bash
aws ec2 modify-instance-metadata-options \
  --instance-id i-0123456789abcdef0 \
  --http-tokens required \
  --http-put-response-hop-limit 1 \
  --http-endpoint enabled
```

With `--http-tokens required`, a request without a valid token receives a 401 from the service itself.

## GCP and Azure: a required header, but block the address anyway

GCP's metadata server answers at `metadata.google.internal` or `169.254.169.254` and requires a `Metadata-Flavor: Google` header on every request; Google states the request and response never leave the physical host. Azure's Instance Metadata Service listens at the same non-routable address, `169.254.169.254`, reachable only from within the VM, and requires a `Metadata: true` header, rejecting any request that also carries an `X-Forwarded-For` header. Both header checks stop a naive `curl`, but neither stops a fetch that has been steered into adding the header, so block `169.254.169.254` from workloads that have no legitimate reason to reach it, the same as any other internal address.

## Default-deny egress

- **Cloud firewall / security group egress rules** (the inbound side of the same tools is in
  [cloud-firewalls.md](cloud-firewalls.md)): default outbound rules on most providers allow everything out;
  add explicit egress rules that permit only DNS and the specific provider APIs the application calls, and
  deny the rest. On AWS, security groups do not filter traffic to or from the instance metadata address,
  `169.254.169.254` (per the security groups documentation); they are not a backstop for metadata access.
  Keep egress rules for every other destination, and rely on IMDSv2, the hop limit, and disabling the
  metadata endpoint where it is unused to control reachability of the metadata service itself.
- **Kubernetes NetworkPolicy egress**: a pod is unrestricted for egress until a `NetworkPolicy` with `Egress`
  in its `policyTypes` selects it, after which only listed destinations are reachable. This has no effect
  unless the cluster's network plugin (CNI) implements `NetworkPolicy`; confirm enforcement before relying
  on it.

  ```yaml
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: agent-egress
  spec:
    podSelector: {matchLabels: {app: agent}}
    policyTypes: [Egress]
    egress:
      - to: [{ipBlock: {cidr: 203.0.113.0/24}}]
        ports: [{protocol: TCP, port: 443}]
  ```
- **Docker network isolation**: an internal network has no default route out, and Docker's own firewall
  rules drop traffic leaving it, while containers on the network still reach each other:
  `docker network create --internal agent-net`.

## Scope boundary

Steering a fetcher into requesting the metadata address or an internal host is server-side request forgery,
an application-security defect belonging to the code doing the fetching, not to this guide. IMDSv2, the
header requirements above, and egress rules are deployment-side controls: they do not prevent the request
from being attempted, they make the attempt fail.

## Verify

```bash
# AWS, no token supplied: with --http-tokens required this returns 401
curl -s -o /dev/null -w '%{http_code}\n' http://169.254.169.254/latest/meta-data/
# GCP, no Metadata-Flavor header: must fail, must not return metadata
curl -s -o /dev/null -w '%{http_code}\n' http://169.254.169.254/computeMetadata/v1/instance/
# Azure, no Metadata: true header: must fail, must not return metadata
curl -s -o /dev/null -w '%{http_code}\n' 'http://169.254.169.254/metadata/instance?api-version=2025-04-07'
# positive control: a host on the egress allow list, for example the AWS STS endpoint used for role
# credentials, must succeed
curl -s -o /dev/null -w '%{http_code}\n' --max-time 5 https://sts.amazonaws.com/

# negative control: a known-live host outside the egress allow list must be blocked, not merely
# unresolved; curl reports a DNS failure differently from a network-level block
curl -sv --max-time 5 https://www.example.com/ 2>&1 | grep -q "Could not resolve host" \
  && echo "DNS failure, not a policy block: confirm this host still resolves before retrying" \
  || echo "blocked past DNS resolution, or timed out: this is the egress policy taking effect"
# confirm the metadata options actually took effect
aws ec2 describe-instances --instance-ids i-0123456789abcdef0 \
  --query 'Reservations[].Instances[].MetadataOptions'
# expect HttpTokens: required, HttpPutResponseHopLimit: 1
```

## Sources (checked September 2026)

- AWS EC2 instance metadata service configuration: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html
- AWS VPC security groups (traffic security groups do not filter, including instance metadata): https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html
- AWS CLI `modify-instance-metadata-options`: https://docs.aws.amazon.com/cli/latest/reference/ec2/modify-instance-metadata-options.html
- GCP metadata server overview: https://cloud.google.com/compute/docs/metadata/overview
- Azure Instance Metadata Service: https://learn.microsoft.com/en-us/azure/virtual-machines/instance-metadata-service
- Kubernetes NetworkPolicy: https://kubernetes.io/docs/concepts/services-networking/network-policies/
- Docker network create (`--internal`): https://docs.docker.com/reference/cli/docker/network/create/
