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
answer is everyone.

**A kubeconfig may be a credential, or only a pointer to one.** A file with an embedded token, or with
a client certificate and its key, is the credential: anyone holding it has whatever it is bound to, with
no second factor. A file that names an exec credential plugin is not, because the plugin fetches a fresh
token when it runs, which is how EKS works with `aws eks get-token`. Copying that file without the
provider credentials the plugin depends on confers nothing. Open yours and find out which kind it is
before you decide how to handle it. Treat the credential-bearing kind as a secret
([secrets.md](secrets.md)), scope every kubeconfig with RBAC rather than handing out cluster-admin, and
prefer the plugin form.

**Self-managed clusters expose more ports.** Kubernetes documents the control plane's inbound ports as
6443 for the API server, 2379 and 2380 for etcd, 10250 for the kubelet API, 10259 for the scheduler and
10257 for the controller manager. These are defaults, not fixtures. The same page notes that "One common
example is API server port that is sometimes switched to 443", which is the port the managed providers
serve on, so read the port out of your own kubeconfig rather than assuming 6443. Only the API server has
any business being reachable beyond the cluster, and only from addresses you list. Kubernetes states that
"By default, the API server stores plain-text representations of resources into etcd, with no at-rest
encryption", so whoever reaches 2379 reads every Secret in the cluster. Kubernetes puts the consequence
plainly: "Access to etcd is equivalent to root permission in the cluster so ideally only the API server
should have access to it." Bind etcd to the control-plane node's own private address, require client
certificates on both the client and peer ports, and let nothing but the API server hold a client
certificate; a firewall rule in front of an etcd that still listens on `0.0.0.0` is one misconfiguration
away from the same outcome.

**The kubelet's default depends on how it is configured, and the two answers are opposites.**
Configured by command-line flag, `--anonymous-auth` carries "Default: true", and Kubernetes states that
"requests to the kubelet's HTTPS endpoint that are not rejected by other configured authentication
methods are treated as anonymous requests", given the username `system:anonymous`. Configured by file,
the same settings default the other way: the `KubeletConfiguration` v1beta1 reference gives
`authentication` the defaults "anonymous: enabled: false" and "webhook: enabled: true", and gives
`authorization` the default "mode: Webhook". kubeadm and the managed distributions configure by file, so
those nodes are not anonymous by default and a flag-configured node is. Assume neither. Read the
effective configuration on a node, and where the flags are in use set `--anonymous-auth=false` and
`--authorization-mode=Webhook`. Port 10250 runs commands in containers, so it should never be reachable
from outside the cluster either way.

**The read-only port asks nobody for anything.** `--read-only-port` carries "Default: 10255" and serves,
in Kubernetes' own words, "with no authentication/authorization (set to 0 to disable)". It is a separate
listener, so fixing 10250 does not touch it, and it hands pod and node state to anyone who can reach it.
GKE states that "The kubelet read-only port is disabled by default in new clusters that run version 1.32
or later", which is to say an older cluster did not inherit that and needs the change made.

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
# Clear the proxy variables first: curl honours them, and a proxy whose egress sits inside
# an allowed range returns a 200 from a correctly restricted API server.
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy
curl -sS -o /dev/null -m 5 -w '%{http_code}\n' "$API/version"; rc=$?; echo "curl exit $rc"
# Read the EXIT CODE here, not the status line, and leave verification ON. An exposed API
# server usually prints 000 with exit 60, because curl completed a TLS handshake and then
# declined to trust the cluster's own CA. Exit 60 is an ANSWER, and reading the 000 beside
# it as a pass is the mistake this comment exists to prevent. So is exit 0 with any status
# at all: 200, 401, 403 and 404 alike mean something served the request.
# Pass is exit 7 (connection refused) or exit 28 (timed out), and nothing else. Skipping
# verification with -k would work too, and it would put a TLS bypass in a Verify block.

# Scan the CONTROL-PLANE nodes, not a worker. A worker shows 6443 and 2379 closed while
# the control-plane host serves both. A managed cluster has no control-plane node you can
# scan, so there the curl above is the whole of this check.
kubectl get nodes -l node-role.kubernetes.io/control-plane -o wide
nmap -Pn -p 6443,2379,2380,10250,10255,10256,10257,10259 REPLACE_WITH_ONE_NODE_ADDRESS
nmap -6 -Pn -p 6443,2379,2380,10250,10255,10256,10257,10259 REPLACE_WITH_ITS_IPV6_ADDRESS
                                                                     # every one closed or filtered from
                                                                     # outside. 10250 runs commands in
                                                                     # containers; 2379 holds every Secret
```

One name is not one address and one node is not the cluster. Repeat the scan for every control-plane
node and every address each one answers on, in both families: a host filtered on IPv4 while it answers
on IPv6 passes every check above and is still reachable. The `kubectl get svc` line catches NodePort
Services that exist, but nothing here probes the 30000 to 32767 NodePort range itself, over TCP or UDP,
so scan that too if you run self-managed nodes with public addresses.

## Sources (checked September 2026)

- Ingress NGINX: Statement from the Kubernetes Steering and Security Response Committees (retirement, detection command): https://kubernetes.io/blog/2026/01/29/ingress-nginx-statement/ ; Kubernetes docs, Gateway API (successor to Ingress, migration guide): https://kubernetes.io/docs/concepts/services-networking/gateway/
- Gateway API getting started (CRD install): https://gateway-api.sigs.k8s.io/guides/getting-started/ ; TLS: https://gateway-api.sigs.k8s.io/guides/user-guides/tls/ ; HTTP routing: https://gateway-api.sigs.k8s.io/guides/user-guides/http-routing/ ; redirects: https://gateway-api.sigs.k8s.io/guides/user-guides/http-redirect-rewrite/
- Envoy Gateway: https://gateway.envoyproxy.io/ ; Helm install: https://gateway.envoyproxy.io/docs/install/install-helm/ ; quickstart and its manifest (GatewayClass `controllerName`): https://gateway.envoyproxy.io/docs/tasks/quickstart/ , https://github.com/envoyproxy/gateway/releases/download/v1.9.1/quickstart.yaml
- Envoy Gateway tasks, secure gateways (TLS listener): https://gateway.envoyproxy.io/docs/tasks/security/secure-gateways/ ; basic auth: https://gateway.envoyproxy.io/docs/tasks/security/basic-auth/ ; OIDC: https://gateway.envoyproxy.io/docs/tasks/security/oidc/ ; external authorization (`extAuth`): https://gateway.envoyproxy.io/docs/tasks/security/ext-auth/ ; HTTP redirect: https://gateway.envoyproxy.io/docs/tasks/traffic/http-redirect/
- Authelia: proxy integration (the proxy calls the authorization endpoint): https://www.authelia.com/integration/proxies/introduction/ ; Envoy Gateway `SecurityPolicy` example: https://www.authelia.com/integration/kubernetes/envoy/gateway/
- kubectl JSONPath filter syntax: https://kubernetes.io/docs/reference/kubectl/jsonpath/
- Kubernetes ports and protocols (6443 API server, 2379 and 2380 etcd, 10250 kubelet, 10259 scheduler, 10257 controller manager): https://kubernetes.io/docs/reference/networking/ports-and-protocols/
- Kubernetes kubelet authentication and authorization (unrejected requests treated as anonymous, `--anonymous-auth`, `--authorization-mode=Webhook`): https://kubernetes.io/docs/reference/access-authn-authz/kubelet-authn-authz/
- Kubernetes kubelet command-line reference (`--anonymous-auth` "Default: true", `--read-only-port` "Default: 10255" serving "with no authentication/authorization"): https://kubernetes.io/docs/reference/command-line-tools-reference/kubelet/
- Kubernetes `KubeletConfiguration` v1beta1 reference (the file defaults: `anonymous: enabled: false`, `webhook: enabled: true`, `mode: Webhook`): https://kubernetes.io/docs/reference/config-api/kubelet-config.v1beta1/
- Kubernetes encrypting confidential data at rest ("By default, the API server stores plain-text representations of resources into etcd, with no at-rest encryption"): https://kubernetes.io/docs/tasks/administer-cluster/encrypt-data/
- Kubernetes, operating etcd clusters, including securing communication and limiting access ("Access to etcd is equivalent to root permission in the cluster"): https://kubernetes.io/docs/tasks/administer-cluster/configure-upgrade-etcd/
- GKE, disable the kubelet read-only port (disabled by default only in new clusters running 1.32 or later): https://docs.cloud.google.com/kubernetes-engine/docs/how-to/disable-kubelet-readonly-port
- Amazon EKS cluster endpoint access ("[b]y default, this API server endpoint is public to the internet"): https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html
- GKE control plane network isolation, including how authorized networks work: https://docs.cloud.google.com/kubernetes-engine/docs/concepts/network-isolation#how_authorized_networks_work
- AKS API server authorized IP ranges: https://learn.microsoft.com/en-us/azure/aks/api-server-authorized-ip-ranges
- cert-manager Gateway API usage (enabling support, annotations): https://cert-manager.io/docs/usage/gateway/ ; ACME HTTP-01 `gatewayHTTPRoute` solver: https://cert-manager.io/docs/configuration/acme/http01/
- Traefik Kubernetes Gateway API provider: https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-gateway/ ; Cilium Gateway API support: https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/
