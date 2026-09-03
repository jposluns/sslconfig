# Kubernetes: ingress TLS and authentication

The cluster equivalents of this repository's rules: nothing reaches a workload except through an ingress that terminates TLS, and no Service becomes public through a casual `type: LoadBalancer` or `NodePort`.

## 1. Automatic certificates with cert-manager

Install [cert-manager](https://cert-manager.io/docs/), define an ACME issuer once, and annotate ingresses:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    email: admin@example.com
    server: https://acme-v02.api.letsencrypt.org/directory
    privateKeySecretRef:
      name: letsencrypt-account
    solvers:
      - http01:
          ingress:
            class: nginx
```

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
spec:
  tls:
    - hosts: [app.example.com]
      secretName: app-tls
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend: { service: { name: app, port: { number: 80 } } }
```

cert-manager issues into `app-tls` and renews automatically. ingress-nginx redirects HTTP to HTTPS by default when a TLS block exists (`nginx.ingress.kubernetes.io/ssl-redirect` / `force-ssl-redirect` control it explicitly).

## 2. Authentication at the ingress

ingress-nginx supports basic auth from a Secret, as the proxy-level gate ([authentication.md](authentication.md) still applies inside the app):

```bash
htpasswd -cB auth admin
kubectl create secret generic app-basic-auth --from-file=auth
```

```yaml
  annotations:
    nginx.ingress.kubernetes.io/auth-type: basic
    nginx.ingress.kubernetes.io/auth-secret: app-basic-auth
    nginx.ingress.kubernetes.io/auth-realm: "Restricted"
```

For MFA and SSO, put an identity layer in front per [mfa.md](mfa.md) (oauth2-proxy and Authelia both document Kubernetes deployments), or publish through [cloudflare.md](cloudflare.md).

## 3. Cluster posture

- Expose workloads through the ingress only; avoid `NodePort`/`LoadBalancer` Services except for the ingress controller itself.
- Store credentials in Secrets (or an external secrets operator), not ConfigMaps or env literals in manifests committed to git ([secrets.md](secrets.md)).
- NetworkPolicies limit which pods reach databases; the database guides' TLS and auth still apply inside the cluster.

## 4. Verify

```bash
kubectl get svc -A | grep -E 'NodePort|LoadBalancer'   # only the ingress controller
kubectl get certificate -A                              # Ready=True
curl -sI http://app.example.com/                        # redirect to https
curl -s  https://app.example.com/                       # 401 where basic auth is set
```

## Sources (checked September 2026)

- cert-manager documentation: https://cert-manager.io/docs/
- ingress-nginx annotations (auth-type, auth-secret, auth-realm, ssl-redirect): https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/annotations/
