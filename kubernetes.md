# Kubernetes: Gateway API TLS and authentication

The cluster equivalents of this repository's rules: nothing reaches a workload except through the TLS-terminating entry point (a Gateway API `Gateway`), and no Service becomes public through a casual `type: LoadBalancer` or `NodePort`; the entry point's own Service is the only exception.

**If you run ingress-nginx today, migrate.** Earlier versions of this guide built on ingress-nginx. The Kubernetes project retired it in March 2026: per the Kubernetes Steering and Security Response Committees, "there will be no more releases for bug fixes, security patches, or any updates of any kind after the project is retired", and "choosing to remain with Ingress NGINX after its retirement leaves you and your users vulnerable to attack" (as of September 2026; statement linked in Sources). Detect it with cluster-admin permissions: `kubectl get pods --all-namespaces --selector app.kubernetes.io/name=ingress-nginx`. Any pod returned means migration is required; the `nginx.ingress.kubernetes.io/*` annotations die with the controller. Kubernetes documents Gateway API as "the successor to the Ingress API" and links a migration guide from its Gateway API page. The rest of this guide is the Gateway API form of the old rules.

## 1. Gateway API with a maintained implementation

Gateway API is a set of CRDs, not part of core Kubernetes; a controller you install implements them. This guide uses [Envoy Gateway](https://gateway.envoyproxy.io/): `helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.9.1 -n envoy-gateway-system --create-namespace` (version current at the time of writing; the default chart also installs the Gateway API CRDs). The chart does not create a `GatewayClass`; the quickstart applies one separately, and the `Gateway` below refers to it by name, so apply it first and confirm that the controller accepted it:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: eg
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
```

```bash
kubectl get gatewayclass eg -o jsonpath='{.status.conditions[?(@.type=="Accepted")].status}'   # True
```

Traefik's Gateway API provider (`providers.kubernetesGateway`) and Cilium (`gatewayAPI.enabled=true`, requires kube-proxy replacement) are maintained alternatives, linked in Sources. The `Gateway` is the entry point; keep its HTTP listener only for redirects and ACME challenges:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: eg
  annotations: { cert-manager.io/cluster-issuer: letsencrypt }   # section 2
spec:
  gatewayClassName: eg
  listeners:
    - { name: http, protocol: HTTP, port: 80 }
    - name: https
      protocol: HTTPS
      port: 443
      hostname: app.example.com
      tls: { mode: Terminate, certificateRefs: [{ kind: Secret, name: app-tls }] }
```

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: { name: app }
spec:
  parentRefs: [{ name: eg, sectionName: https }]        # sectionName binds the route to one listener
  hostnames: [app.example.com]
  rules: [{ backendRefs: [{ name: app, port: 80 }] }]   # a ClusterIP Service
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: { name: app-redirect }
spec:
  parentRefs: [{ name: eg, sectionName: http }]
  hostnames: [app.example.com]
  rules: [{ filters: [{ type: RequestRedirect, requestRedirect: { scheme: https, statusCode: 301 } }] }]
```

## 2. Automatic certificates with cert-manager

Install [cert-manager](https://cert-manager.io/docs/) with Gateway API support turned on: `--set config.gatewayAPI.enabled=true` on its Helm chart (cert-manager 1.15 and later per its docs; the Gateway API CRDs must exist before cert-manager starts, or restart its Deployment afterwards). Define an ACME issuer once, with the HTTP-01 solver pointed at the Gateway (adjust `namespace` to where the Gateway lives). The `cert-manager.io/cluster-issuer` (or `cert-manager.io/issuer`) annotation goes on the Gateway, not on routes: cert-manager creates one Certificate per Secret named in the HTTPS listeners, with `dnsNames` taken from each listener's `hostname`, issues into `app-tls`, and renews it.

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata: { name: letsencrypt }
spec:
  acme:
    email: admin@example.com
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef: { name: letsencrypt-account }
    solvers:
      - http01:
          gatewayHTTPRoute: { parentRefs: [{ name: eg, namespace: default, kind: Gateway }] }
```

## 3. Authentication at the entry point

Gateway API defines no authentication filter; each implementation adds its own. Envoy Gateway's `SecurityPolicy` attaches basic auth to a Gateway, HTTPRoute, or GRPCRoute from a Secret holding an htpasswd file. Its docs state that only SHA hashes are supported, which falls short of the bcrypt rule in [authentication.md](authentication.md): treat it as a gate over TLS with long random passwords, and keep the application's own login in place.

```bash
htpasswd -cbs .htpasswd admin REPLACE_WITH_LONG_RANDOM_VALUE
kubectl create secret generic app-basic-auth --from-file=.htpasswd
```

```yaml
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata: { name: app-basic-auth }
spec:
  targetRefs: [{ group: gateway.networking.k8s.io, kind: HTTPRoute, name: app }]
  basicAuth: { users: { name: app-basic-auth } }
```

For SSO, the same `SecurityPolicy` takes an `oidc` block (`provider.issuer`, `clientID`, a `clientSecret` Secret, `redirectURL`) so Envoy Gateway sends users to an OpenID Connect provider; enforce MFA at that provider ([mfa.md](mfa.md), [identity-providers.md](identity-providers.md)). The portable alternative for any Gateway implementation is oauth2-proxy deployed in the cluster as the route's backend in front of the app, per [mfa.md](mfa.md). Authelia does not proxy traffic; the proxy calls its authorization endpoint, so it needs an implementation with external authorization. On Envoy Gateway the same `SecurityPolicy` takes an `extAuth.http` block whose `backendRefs` point at the Authelia Service and whose `path` is `/api/authz/ext-authz/`, per Authelia's Envoy Gateway page. Publishing through [cloudflare.md](cloudflare.md) is the other option.

## 4. Cluster posture

- Expose workloads through the Gateway only; the Service Envoy Gateway creates for it in `envoy-gateway-system` is the one `LoadBalancer` in the cluster.
- Databases stay `type: ClusterIP` (the default) and never get a route; NetworkPolicies limit which pods reach them, and their guides' TLS and auth still apply inside the cluster ([postgresql.md](postgresql.md), [mysql.md](mysql.md), [redis.md](redis.md), [mongodb.md](mongodb.md)).
- Store credentials in Secrets (or an external secrets operator), not ConfigMaps or env literals in manifests committed to git ([secrets.md](secrets.md)).

## 5. The control plane is a separate exposure

Sections 1 to 4 cover how traffic reaches your workloads. None of it touches the cluster's own
management surface, and a reader can apply every one of them while the API server answers the whole
internet.

**Managed clusters start public.** AWS documents that "[b]y default, this API server endpoint is public
to the internet" for EKS. Restrict it: EKS supports private endpoint access and CIDR restrictions on the
public one, GKE calls the same control "authorized networks", and AKS calls it authorized IP ranges.
Whichever you run, the question to answer is which addresses can reach the API server, and the default
answer is everyone. GKE needs a second look, because it has two control-plane endpoints and authorized
networks only govern one. The vendor says authorized networks "provide an IP-based firewall that
controls access to the GKE control plane", and that reaching the DNS-based endpoint is a different
question entirely: "To access the control plane endpoint, you need to configure IAM roles and policies,
and authentication tokens." So a GKE reader who restricts authorized networks exactly as this section
says, and then probes the address in their kubeconfig, can still have a DNS-based endpoint answering
from anywhere, gated by IAM alone. Check both, and if you do not use the DNS-based endpoint, disable it
rather than leaving it to IAM.

**A kubeconfig may be a credential, or only a pointer to one.** A file with an embedded token, or with
a client certificate and its key, is the credential: anyone holding it has whatever it is bound to, with
no second factor. A file that names an exec credential plugin is usually not, because the plugin fetches
a fresh token when it runs, which is how EKS works with `aws eks get-token`, and copying it without the
provider credentials the plugin depends on confers nothing. Usually, not always: the exec block carries
`args` and `env`, and Kubernetes documents `env` as defining "additional environment variables to expose
to the process", so a plugin can be handed its own credentials right there in the file. Read the whole
block before you decide it is only a pointer. Open yours and find out which kind it is before you decide
how to handle it. Treat the credential-bearing kind as a secret ([secrets.md](secrets.md)), scope every
kubeconfig with RBAC rather than handing out cluster-admin, and prefer the plugin form.

**Self-managed clusters expose more ports.** Kubernetes documents the control plane's inbound ports as
6443 for the API server, 2379 and 2380 for etcd, 10250 for the kubelet API, 10259 for the scheduler and
10257 for the controller manager. Worker nodes have their own inbound list on the same page: 10250
again for the kubelet API, 10256 for kube-proxy health, and the NodePort range 30000 to 32767 over
TCP and UDP. These are defaults, not fixtures. The same page notes that "One common
example is API server port that is sometimes switched to 443", which is the port the managed providers
serve on, so read the port out of your own kubeconfig rather than assuming 6443. Only the API server has
any business being reachable beyond the cluster, and only from addresses you list. Kubernetes states that
"By default, the API server stores plain-text representations of resources into etcd, with no at-rest
encryption", so what is on that disk is every Secret in the cluster in the clear. Reaching 2379 is not
the same as reading it, because Kubernetes' operating-etcd guide says "Once etcd is configured
correctly, only clients with valid certificates can access it"; the point is that the certificate is
the entire boundary, and there is no second one behind it. Kubernetes puts the consequence plainly:
"Access to etcd is equivalent to root permission in the cluster so ideally only the API server should
have access to it." Require client certificates on both the client and peer ports, and keep the client
listener off any public interface. Do not simply move it to the private address: kubeadm points the
API server at loopback, `127.0.0.1:2379` or `::1` depending on the address family it advertises, and
configures etcd to listen there as well as on the advertised address, so dropping the loopback
listener breaks the API server on that node. Keep whichever one your cluster configured rather than
the literal written here. Keep issuance narrow rather than absolute, because kubeadm issues an
`etcd-healthcheck-client` certificate of its own and backups need one too; the rule is that you should
be able to name every holder. A firewall rule in front of an etcd still listening on `0.0.0.0` is one
misconfiguration away from the same outcome.

**The kubelet's default depends on how it is configured, and the two answers are opposites.**
Configured by command-line flag, `--anonymous-auth` carries "Default: true", and Kubernetes states that
"requests to the kubelet's HTTPS endpoint that are not rejected by other configured authentication
methods are treated as anonymous requests", given the username `system:anonymous`. Configured by file,
the same settings default the other way: the `KubeletConfiguration` v1beta1 reference gives
`authentication` the defaults "anonymous: enabled: false" and "webhook: enabled: true", and gives
`authorization` the default "mode: Webhook". kubeadm and the managed distributions configure by file, so
those nodes are not anonymous by default and a flag-configured node is. The EKS AMI's own node
bootstrap writes a `KubeletConfiguration` carrying `Anonymous.Enabled: false`, `Mode: "Webhook"` and
`ReadOnlyPort: 0`, which is the file path rather than the flag path. Assume neither. Read the
effective configuration on a node, and where the flags are in use set `--anonymous-auth=false` and
`--authorization-mode=Webhook`. Port 10250 runs commands in containers, so it should never be reachable
from outside the cluster either way.

**The read-only port has the same split, and the same answer.** The `--read-only-port` FLAG carries
"Default: 10255", and Kubernetes describes that listener as serving "with no
authentication/authorization (set to 0 to disable)". The `KubeletConfiguration` v1beta1 field carries
"Default: 0 (disabled)". So a flag-configured node serves an unauthenticated listener nobody asked for,
and a file-configured node does not unless something turned it on. GKE is the case where something did:
it states that "The kubelet read-only port is disabled by default in new clusters that run version 1.32
or later", which is only worth saying because older clusters have it on. Read the effective
configuration here too, and remember that 10255 is a separate listener, so securing 10250 does not
touch it.

## Verify

```bash
kubectl get svc -A | grep -E 'NodePort|LoadBalancer'                 # only the Gateway's Service
kubectl get gateway/eg -o jsonpath='{.status.addresses[0].value}'    # the public address; DNS points here
kubectl get certificate -A                                           # Ready=True
curl -sI http://app.example.com/                                     # 301 to https://app.example.com/
curl -sS -o /dev/null -w '%{http_code}\n' https://app.example.com/   # 401 where basic auth is set

# The API server endpoint, taken WHOLE. Do not rebuild it with :6443. Managed providers
# serve the API on 443, and a probe of 6443 times out against a cluster that is answering
# the internet on 443, which reads as a pass.
API=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}') && echo "$API"

# From a machine OUTSIDE any allowed range, against a cluster you are authorized to test.
# Neutralize the proxy settings, all of them. curl reads ALL_PROXY and all_proxy as well as
# the per-scheme variables, and it reads ~/.curlrc, which can also turn verification off.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy NO_PROXY no_proxy

# First at the TCP layer, because this is the only part with a clean answer. Did anything
# accept a connection?
read -r HOST PORT URL <<<"$(python3 - "$API" <<'PY'
import sys, urllib.parse
raw = sys.argv[1].strip()
if "://" not in raw:                      # kubectl accepts a bare host; curl would guess http
    raw = "https://" + raw
p = urllib.parse.urlsplit(raw)
if not p.hostname:
    sys.exit("cannot parse an API server out of: " + sys.argv[1])
print(p.hostname, p.port or (80 if p.scheme == "http" else 443),
      p.scheme + "://" + p.netloc)
PY
)" || exit 1
nc -vz -w 3 "$HOST" "$PORT"
# Parsed with python3 rather than cut with sed. A bracketed IPv6 address breaks on the
# colons, and the failure looks exactly like the clean drop you were hoping for. A bare
# host with no scheme is also legal in a kubeconfig, and curl would read that as HTTP on
# port 80 and probe the wrong thing entirely, so the scheme is filled in here and the URL
# the probe uses is the normalized one. This step needs python3, nc and nmap on the machine
# you run it from, none of which the cluster provides for you.
# "succeeded" means something is listening and reachable from here, whatever it does next.

# Then at the HTTP layer, with verification left ON.
curl -q --noproxy '*' -sS -o /dev/null --connect-timeout 3 -m 10 \
  -w '%{http_code}\n' "$URL/version"; echo "curl exit $?"
# Exit 0 with ANY status, 200, 401, 403 and 404 alike, means it answered.
# So does exit 60: curl reached a TLS peer, received a certificate and refused to trust it.
# That is not necessarily a completed handshake, and it does not need to be: something on
# that address answered in TLS, and the 000 printed beside it is not a pass.
# Exit 7 is "failed to connect", which is the outcome you want. Exit 28 is a TIMEOUT and it
# is NOT clean evidence either way: a dropped packet and an endpoint that accepted the
# connection and then stalled both produce it. If you get 28, the nc line above is what
# tells you which one you had.
# Any other exit is neither, and two are worth naming.
# Exit 6 is a name that did not resolve. Do not read that as proof of a private cluster:
# EKS documents that a private-only endpoint is still "resolved by public DNS servers to a
# private IP address from the VPC", so a correctly private cluster usually resolves fine
# and simply refuses the connection. Exit 6 means your resolver had no answer, which is
# worth understanding before you call it anything.
# And a TLS-intercepting middlebox on your own network answers every outbound 443 with its own
# certificate, so it prints exit 60 whether or not the cluster is reachable. Exit 60 means
# SOMETHING answered, and on a network like that it may not be the thing you aimed at; the
# unset above defeats a configured proxy and nothing defeats a transparent one except
# testing from somewhere else.

# Scan the control-plane nodes FIRST, because a worker shows 6443 and 2379 closed while
# the control-plane host serves both, and a scan of a worker alone therefore passes on an
# exposed control plane. Then scan every node that has a public address, worker nodes
# included: 10250 and 10256 are worker ports, 10250 runs commands in containers, and a
# kubeadm or k3s cluster built on cloud instances commonly gives every node a public
# address. A managed cluster hides the control-plane nodes from you, but not its workers,
# and the kubectl line below tells you which nodes have a public address. Scan the ones
# that do.
kubectl get nodes -o wide          # control-plane nodes and workers alike, but see below
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.addresses[*].address}{"\n"}{end}'
                                   # -o wide prints only the FIRST external address per node
nmap -Pn -p 6443,2379,2380,10250,10255,10256,10257,10259 REPLACE_WITH_ONE_NODE_ADDRESS
nmap -6 -Pn -p 6443,2379,2380,10250,10255,10256,10257,10259 REPLACE_WITH_ITS_IPV6_ADDRESS
                                                                     # every one closed or filtered from
                                                                     # outside. 10250 runs commands in
                                                                     # containers; 2379 is the whole of etcd
```

One name is not one address and one node is not the cluster. Repeat the scan for every node that has a
public address, worker nodes included, and every address each one answers on, in both families: a host
filtered on IPv4 while it answers on IPv6 passes every check above and is still reachable. The
`kubectl get svc` line catches NodePort Services that exist, but nothing here probes the 30000 to 32767
NodePort range itself, over TCP or UDP, so scan that too if you run self-managed nodes with
public addresses. And a cluster whose etcd runs on its own machines has hosts that `kubectl get nodes`
never lists, because they carry no kubelet; take their client and peer addresses from wherever you
configured them and scan those too.

Be clear about what a pass here is worth. It says that this host, at this moment, over this address
family, could not reach that endpoint. It does not say the cluster is restricted, because your own
egress, a stale kubeconfig context, a resolver, a tunnel that is down, or a transient failure at the far
end all produce the same result, and because an allowlist that admits one network you forgot about is
still an allowlist that admits it. Run it from more than one place before you believe it, and read the
allowed ranges out of the provider's own configuration rather than inferring them from a probe.

## Sources (checked September 2026)

- Ingress NGINX: Statement from the Kubernetes Steering and Security Response Committees (retirement, detection command): https://kubernetes.io/blog/2026/01/29/ingress-nginx-statement/ ; Kubernetes docs, Gateway API (successor to Ingress, migration guide): https://kubernetes.io/docs/concepts/services-networking/gateway/
- Gateway API getting started (CRD install): https://gateway-api.sigs.k8s.io/guides/getting-started/introduction/ ; TLS: https://gateway-api.sigs.k8s.io/guides/user-guides/tls/ ; HTTP routing: https://gateway-api.sigs.k8s.io/guides/user-guides/http-routing/ ; redirects: https://gateway-api.sigs.k8s.io/guides/user-guides/http-redirect-rewrite/
- Envoy Gateway: https://gateway.envoyproxy.io/ ; Helm install: https://gateway.envoyproxy.io/docs/install/install-helm/ ; quickstart and its manifest (GatewayClass `controllerName`): https://gateway.envoyproxy.io/docs/tasks/quickstart/ , https://github.com/envoyproxy/gateway/releases/download/v1.9.1/quickstart.yaml
- Envoy Gateway tasks, secure gateways (TLS listener): https://gateway.envoyproxy.io/docs/tasks/security/secure-gateways/ ; basic auth: https://gateway.envoyproxy.io/docs/tasks/security/basic-auth/ ; OIDC: https://gateway.envoyproxy.io/docs/tasks/security/oidc/ ; external authorization (`extAuth`): https://gateway.envoyproxy.io/docs/tasks/security/ext-auth/ ; HTTP redirect: https://gateway.envoyproxy.io/docs/tasks/traffic/http-redirect/
- Authelia: proxy integration (the proxy calls the authorization endpoint): https://www.authelia.com/integration/proxies/introduction/ ; Envoy Gateway `SecurityPolicy` example: https://www.authelia.com/integration/kubernetes/envoy/gateway/
- kubectl JSONPath filter syntax: https://kubernetes.io/docs/reference/kubectl/jsonpath/
- curl exit codes, used to read the API server probe (6 could not resolve, 7 failed to connect, 28 timed out, 60 peer certificate not trusted): https://curl.se/libcurl/c/libcurl-errors.html
- Nmap host discovery and port specification, for the node scan (`-Pn`, `-p`, `-6`): https://nmap.org/book/man-host-discovery.html , https://nmap.org/book/man-port-scanning-basics.html
- Kubernetes ports and protocols (6443 API server, 2379 and 2380 etcd, 10250 kubelet, 10259 scheduler, 10257 controller manager): https://kubernetes.io/docs/reference/networking/ports-and-protocols/
- Kubernetes kubelet authentication and authorization (unrejected requests treated as anonymous, `--anonymous-auth`, `--authorization-mode=Webhook`): https://kubernetes.io/docs/reference/access-authn-authz/kubelet-authn-authz/
- Kubernetes kubelet command-line reference (`--anonymous-auth` "Default: true", `--read-only-port` "Default: 10255" serving "with no authentication/authorization"): https://kubernetes.io/docs/reference/command-line-tools-reference/kubelet/
- Kubernetes `KubeletConfiguration` v1beta1 reference (the file defaults: `anonymous: enabled: false`, `webhook: enabled: true`, `mode: Webhook`, `readOnlyPort` "Default: 0 (disabled)"): https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/
- Amazon EKS AMI node bootstrap, the default `KubeletConfiguration` it writes (`Anonymous.Enabled: false`, `Mode: "Webhook"`, `ReadOnlyPort: 0`): https://github.com/awslabs/amazon-eks-ami/blob/main/nodeadm/internal/kubelet/config.go
- Kubernetes kubeconfig API reference (`ExecConfig`, whose `env` "defines additional environment variables to expose to the process"): https://kubernetes.io/docs/reference/config-api/kubeconfig.v1/
- Kubernetes encrypting confidential data at rest ("By default, the API server stores plain-text representations of resources into etcd, with no at-rest encryption"): https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/
- Kubernetes, operating etcd clusters, including securing communication and limiting access ("Access to etcd is equivalent to root permission in the cluster"): https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/
- GKE, disable the kubelet read-only port (disabled by default only in new clusters running 1.32 or later): https://docs.cloud.google.com/kubernetes-engine/docs/how-to/disable-kubelet-readonly-port
- Amazon EKS cluster endpoint access ("[b]y default, this API server endpoint is public to the internet"; private endpoint DNS, "resolved by public DNS servers to a private IP address from the VPC"): https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html
- GKE control plane network isolation, including how authorized networks work: https://docs.cloud.google.com/kubernetes-engine/docs/concepts/network-isolation#how_authorized_networks_work
- AKS API server authorized IP ranges: https://learn.microsoft.com/en-us/azure/aks/api-server-authorized-ip-ranges
- cert-manager Gateway API usage (enabling support, annotations): https://cert-manager.io/docs/usage/gateway/ ; ACME HTTP-01 `gatewayHTTPRoute` solver: https://cert-manager.io/docs/configuration/acme/http01/
- Traefik Kubernetes Gateway API provider: https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-gateway/ ; Cilium Gateway API support: https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/
