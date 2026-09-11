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

**Managed clusters start public.** AWS documents that "by default, this API server endpoint is public to
the internet" for EKS. Restrict it: EKS supports private endpoint access and CIDR restrictions on the
public one, GKE calls the same control "authorized networks", and AKS calls it authorized IP ranges.
Whichever you run, the question to answer is which addresses can reach the API server, and the default
answer is everyone.

**A kubeconfig is a bearer credential.** Anyone holding one has whatever the certificate or token inside
it is bound to, with no second factor. Treat it as a secret ([secrets.md](secrets.md)), scope it with
RBAC rather than handing out cluster-admin, and prefer short-lived credentials from your provider's CLI
over a long-lived file on a laptop.

**Self-managed clusters expose more ports.** Kubernetes documents the control plane's inbound ports as
6443 for the API server, 2379 and 2380 for etcd, 10250 for the kubelet API, 10259 for the scheduler and
10257 for the controller manager. Only 6443 has any business being reachable beyond the cluster, and
only from addresses you list. etcd holds every Secret in the cluster, in plaintext unless you configure
encryption at rest.

**The kubelet answers anonymously by default.** Kubernetes states that "requests to the kubelet's HTTPS
endpoint that are not rejected by other configured authentication methods are treated as anonymous
requests", given the username `system:anonymous`. Port 10250 runs commands in containers, so set
`--anonymous-auth=false` and `--authorization-mode=Webhook` on every node, and never expose it.

## Verify

```bash
kubectl get svc -A | grep -E 'NodePort|LoadBalancer'                 # only the Gateway's Service
kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}'
                                                                     # the API server address your
                                                                     # kubeconfig points at, to scan below
kubectl get gateway/eg -o jsonpath='{.status.addresses[0].value}'    # the public address; DNS points here
kubectl get certificate -A                                           # Ready=True
curl -sI http://app.example.com/                                     # 301 to https://app.example.com/
curl -sS -o /dev/null -w '%{http_code}\n' https://app.example.com/   # 401 where basic auth is set

# From a machine OUTSIDE any allowed range, against the API server address printed above.
# You own the cluster; scan only addresses you are authorized to test.
curl -sS -o /dev/null -w '%{http_code}\n' --max-time 5 https://REPLACE_WITH_API_SERVER:6443/version
                                                                     # must time out or be refused. A 200
                                                                     # or a 401 both mean it answered you
nmap -Pn -p 6443,2379,2380,10250,10257,10259 REPLACE_WITH_A_NODE_ADDRESS
                                                                     # every one closed or filtered from
                                                                     # outside. 10250 runs commands in
                                                                     # containers; 2379 holds every Secret
```

## Sources (checked September 2026)

- Ingress NGINX: Statement from the Kubernetes Steering and Security Response Committees (retirement, detection command): https://kubernetes.io/blog/2026/01/29/ingress-nginx-statement/ ; Kubernetes docs, Gateway API (successor to Ingress, migration guide): https://kubernetes.io/docs/concepts/services-networking/gateway/
- Gateway API getting started (CRD install): https://gateway-api.sigs.k8s.io/guides/getting-started/ ; TLS: https://gateway-api.sigs.k8s.io/guides/user-guides/tls/ ; HTTP routing: https://gateway-api.sigs.k8s.io/guides/user-guides/http-routing/ ; redirects: https://gateway-api.sigs.k8s.io/guides/user-guides/http-redirect-rewrite/
- Envoy Gateway: https://gateway.envoyproxy.io/ ; Helm install: https://gateway.envoyproxy.io/docs/install/install-helm/ ; quickstart and its manifest (GatewayClass `controllerName`): https://gateway.envoyproxy.io/docs/tasks/quickstart/ , https://github.com/envoyproxy/gateway/releases/download/v1.9.1/quickstart.yaml
- Envoy Gateway tasks, secure gateways (TLS listener): https://gateway.envoyproxy.io/docs/tasks/security/secure-gateways/ ; basic auth: https://gateway.envoyproxy.io/docs/tasks/security/basic-auth/ ; OIDC: https://gateway.envoyproxy.io/docs/tasks/security/oidc/ ; external authorization (`extAuth`): https://gateway.envoyproxy.io/docs/tasks/security/ext-auth/ ; HTTP redirect: https://gateway.envoyproxy.io/docs/tasks/traffic/http-redirect/
- Authelia: proxy integration (the proxy calls the authorization endpoint): https://www.authelia.com/integration/proxies/introduction/ ; Envoy Gateway `SecurityPolicy` example: https://www.authelia.com/integration/kubernetes/envoy/gateway/
- kubectl JSONPath filter syntax: https://kubernetes.io/docs/reference/kubectl/jsonpath/
- Kubernetes ports and protocols (6443 API server, 2379 and 2380 etcd, 10250 kubelet, 10259 scheduler, 10257 controller manager): https://kubernetes.io/docs/reference/networking/ports-and-protocols/
- Kubernetes kubelet authentication and authorization (unrejected requests treated as anonymous, `--anonymous-auth`, `--authorization-mode=Webhook`): https://kubernetes.io/docs/reference/access-authn-authz/kubelet-authn-authz/
- Amazon EKS cluster endpoint access ("by default, this API server endpoint is public to the internet"): https://docs.aws.amazon.com/eks/latest/userguide/cluster-endpoint.html
- GKE control plane network isolation, including how authorized networks work: https://docs.cloud.google.com/kubernetes-engine/docs/concepts/network-isolation#how_authorized_networks_work
- AKS API server authorized IP ranges: https://learn.microsoft.com/en-us/azure/aks/api-server-authorized-ip-ranges
- cert-manager Gateway API usage (enabling support, annotations): https://cert-manager.io/docs/usage/gateway/ ; ACME HTTP-01 `gatewayHTTPRoute` solver: https://cert-manager.io/docs/configuration/acme/http01/
- Traefik Kubernetes Gateway API provider: https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-gateway/ ; Cilium Gateway API support: https://docs.cilium.io/en/stable/network/servicemesh/gateway-api/gateway-api/
