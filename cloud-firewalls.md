# Cloud firewalls: security groups and network rules

On AWS (security groups), Google Cloud (VPC firewall rules), and Azure (network security groups), the recurring hole is one rule wide open to the world: `0.0.0.0/0` (or `::/0`) on a database, admin, or SSH port, added once to unblock a remote connection and never removed.

## Rules

1. **Public means 80/443 on the TLS layer, nothing else.** Only the load balancer, reverse proxy, or tunnel endpoint accepts traffic from `0.0.0.0/0`, and only on 80 (redirect) and 443.
2. **Databases and internal services accept traffic from private sources only**: the application's security group, subnet, or VPC, never the internet. The per-database guides' TLS and auth still apply on top; the firewall is a layer, not the control.
3. **SSH is not public.** Restrict port 22 to your addresses, or remove the inbound rule entirely and use the provider's brokered access (AWS SSM Session Manager, GCP Identity-Aware Proxy, Azure Bastion) or a tailnet ([tailscale.md](tailscale.md)). Then harden the host per [host.md](host.md).
4. **Default deny, explicit allow.** Start from no inbound rules and add the minimum; review rules whenever a service is retired. Reference security-group IDs rather than IP ranges where the provider supports it, so app-to-database access survives IP changes without widening.
5. **Both layers matter on VMs running Docker**: the cloud firewall and the host's rules, remembering that published container ports bypass host UFW ([docker.md](docker.md)).

## Verify

- Provider console or CLI: list rules allowing `0.0.0.0/0` and confirm that each one is 80/443 on the front layer, nothing else.
- From an outside network: `nc -vz <public-ip> 5432 3306 27017 6379 22` fails on every port.
- An external scan of the public IP (for example with nmap, against your own infrastructure only) shows only the intended ports.

## Sources (checked September 2026)

- AWS VPC and security groups: https://docs.aws.amazon.com/vpc/
- Google Cloud VPC firewall rules: https://cloud.google.com/vpc/docs
- Azure virtual network security: https://learn.microsoft.com/en-us/azure/virtual-network/
