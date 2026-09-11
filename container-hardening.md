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

Enforce this cluster-wide with Pod Security Admission's `restricted` level, set as the namespace label `pod-security.kubernetes.io/enforce: restricted` (per the Pod Security Standards documentation). `restricted` requires, among its controls: no privileged containers, no host namespaces or host ports, non-root execution, a read-only root filesystem, all capabilities dropped, and a seccomp profile that is not `Unconfined`. A Pod violating any of these is rejected at admission, not merely flagged.

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
metadata: { name: allow-app-to-db }
spec:
  podSelector: { matchLabels: { role: db } }
  policyTypes: [Ingress]
  ingress:
    - from: [{ podSelector: { matchLabels: { role: app } } }]
      ports: [{ protocol: TCP, port: 5432 }]
```

With both applied, the database pod accepts connections only from pods labeled `role: app` on port 5432; everything else is refused. Databases still need their own TLS and auth on top ([postgresql.md](postgresql.md), [mysql.md](mysql.md), [mongodb.md](mongodb.md), [redis.md](redis.md)); a NetworkPolicy is a layer, not a substitute.

## Verify

```bash
docker exec app id                                  # uid is not 0
docker exec app sh -c 'touch /x'                    # read-only fs: fails
kubectl get pod app -o jsonpath='{.spec.containers[0].securityContext}'
kubectl run probe --rm -it --image=busybox --restart=Never -- \
  wget -T 3 -qO- db:5432                             # from outside the allowlist: times out
```

## Sources (checked September 2026)

- Docker Dockerfile reference (`USER`): https://docs.docker.com/reference/dockerfile/
- Docker Compose file reference (`user`, `read_only`, `cap_add`, `cap_drop`, `security_opt`): https://docs.docker.com/compose/compose-file/
- Kubernetes: Configure a security context for a Pod or Container: https://kubernetes.io/docs/tasks/configure-pod-container/security-context/
- Kubernetes: Pod Security Standards (`restricted` level, Pod Security Admission labels): https://kubernetes.io/docs/concepts/security/pod-security-standards/
- Kubernetes: Network Policies: https://kubernetes.io/docs/concepts/services-networking/network-policies/
