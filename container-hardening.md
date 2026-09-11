# Containers: non-root, dropped capabilities, read-only root, and network segmentation

A model server, chat UI, or proxy is the thing most likely to face untrusted input, so treat its container as compromised eventually and limit what that gets an attacker: not root, not the host's capabilities, not a writable filesystem, and not a route to the rest of the network.

## Docker and Compose

- **Run as non-root.** `USER <user>[:<group>]` in the Dockerfile sets the default user for later `RUN` instructions and for `ENTRYPOINT`/`CMD` at runtime (per the Dockerfile reference); a user with no primary group runs with the `root` group, so set both. Compose's `user:` overrides that per service; unset in both places, the container runs as root (per the Compose file reference).
- **Read-only root filesystem.** `read_only: true` on a Compose service creates it with a read-only root filesystem; mount a small `tmpfs` for any path the process must write to.
- **Drop capabilities.** `cap_drop: [ALL]` removes every Linux capability; add back only the specific one a service needs with `cap_add`.
- **No privilege escalation.** `security_opt: [no-new-privileges:true]` (the Compose reference treats `no-new-privileges`, `no-new-privileges=true`, and `no-new-privileges:true` as equivalent) stops a `setuid` binary from gaining more privilege than the process already has.
- **Never mount the Docker socket into a container.** `/var/run/docker.sock` is root-equivalent access to the host; a container holding it can start a privileged sibling and escape.

```yaml
services:
  app:
    build: .
    user: "10001:10001"
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
```

## Kubernetes securityContext

The same controls, per-Pod or per-container, in the Kubernetes securityContext documentation:

```yaml
spec:
  containers:
    - name: app
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        readOnlyRootFilesystem: true
        allowPrivilegeEscalation: false
        capabilities:
          drop: [ALL]
        seccompProfile:
          type: RuntimeDefault
```

`runAsNonRoot: true` refuses to start the container if its effective user is root; pin `runAsUser` too. `seccompProfile.type: RuntimeDefault` applies the runtime's default syscall filter instead of running unconfined.

Enforce this with Pod Security Admission's `restricted` level, set as the namespace label
`pod-security.kubernetes.io/enforce: restricted` (per the Pod Security Standards documentation); the label
applies to that namespace only, not the whole cluster. `restricted` requires, among its controls: no
privileged containers, no host namespaces or host ports, non-root execution, all capabilities dropped, and a
seccomp profile that is not `Unconfined`. A Pod violating any of these is rejected at admission, not merely
flagged. The `readOnlyRootFilesystem: true` setting above is a separate, per-container recommendation this
guide makes; it is good practice, but it is not one of the controls `restricted` itself requires.

## Network segmentation

A NetworkPolicy is additive and does nothing without an enforcing CNI (per the Kubernetes NetworkPolicy documentation; confirm yours enforces it before relying on this). Start default-deny, then allow only the specific path the app needs:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny-all }
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: allow-app-egress-to-db }
spec:
  podSelector: { matchLabels: { role: app } }
  policyTypes: [Egress]
  egress:
    - to: [{ namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: kube-system } } }]
      ports: [{ protocol: UDP, port: 53 }, { protocol: TCP, port: 53 }]
    - to: [{ podSelector: { matchLabels: { role: db } } }]
      ports: [{ protocol: TCP, port: 5432 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: allow-db-ingress-from-app }
spec:
  podSelector: { matchLabels: { role: db } }
  policyTypes: [Ingress]
  ingress:
    - from: [{ podSelector: { matchLabels: { role: app } } }]
      ports: [{ protocol: TCP, port: 5432 }]
```

A connection needs both sides to allow it: the egress policy on the source pod and the ingress policy on
the destination pod (per the Kubernetes NetworkPolicy documentation). With all three policies applied, an
`app` pod can resolve names through the cluster's DNS and reach the `db` pod on port 5432; the `db` pod
accepts connections only from pods labeled `role: app` on port 5432; every other path is refused. Databases
still need their own TLS and auth on top ([postgresql.md](postgresql.md), [mysql.md](mysql.md),
[mongodb.md](mongodb.md), [redis.md](redis.md)); a NetworkPolicy is a layer, not a substitute.

## Verify

```bash
docker exec app id                                  # uid is not 0
docker exec app sh -c 'touch /x'                    # read-only fs: fails
kubectl get pod app -o jsonpath='{.spec.containers[0].securityContext}'

# resolve the db Service's ClusterIP once and probe that same IP from both pods below; the
# role: other pod has no DNS egress under the policies above, so a probe by hostname would fail on
# name resolution rather than on the NetworkPolicy, and access by IP could still work even if
# the policy were not enforcing anything
DBIP=$(kubectl get svc db -o jsonpath='{.spec.clusterIP}')

# a probe pod needs its own admission-compliant securityContext under the restricted PSA level, and a
# real TCP connect to the db's actual port (a Postgres port does not speak HTTP, so wget cannot test it)
SC='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"probe","image":"busybox:1.36","securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}},"command":["nc","-z","-w","3",'"$DBIP"',"5432"]}]}}'

kubectl run probe-permitted --rm -it --restart=Never --image=busybox:1.36 --labels=role=app \
  --overrides="$SC" -- true                          # from a pod labeled role=app, by IP: must succeed first, proving the path works

kubectl run probe-forbidden --rm -it --restart=Never --image=busybox:1.36 --labels=role=other \
  --overrides="$SC" -- true                          # from a pod without that label, same IP: must time out or be refused at TCP, not fail on DNS
```

## Sources (checked September 2026)

- Docker Dockerfile reference (`USER`): https://docs.docker.com/reference/dockerfile/
- Docker Compose file reference (`user`, `read_only`, `cap_add`, `cap_drop`, `security_opt`): https://docs.docker.com/compose/compose-file/
- Kubernetes: Configure a security context for a Pod or Container: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes: Pod Security Standards (`restricted` level, Pod Security Admission labels): https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Kubernetes: Network Policies: https://kubernetes.io/docs/concepts/services-networking/network-policies/
