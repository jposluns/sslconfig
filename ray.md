# Ray: dashboard, Jobs, and Client ports execute code

Ray's own security page is blunt: if you expose the Ray Dashboard, Ray Jobs, or Ray Client services, "anybody who can access the associated ports can execute arbitrary code on your Ray Cluster", explicitly by submitting a Job or connecting a Client, indirectly through the Dashboard REST API, and implicitly because Ray deserialises arbitrary Python objects with cloudpickle. Ray "doesn't implement access controls for developers interacting with a given cluster"; security and isolation "must be enforced outside of the Ray Cluster". The ports in question are the dashboard (and Jobs API) on `8265`, the Ray Client server on `10001`, and the head node port `6379`, all plain HTTP or gRPC with no login of their own.

## 1. Keep the dashboard on loopback

`ray start --dashboard-host` defaults to localhost, and `--dashboard-port` defaults to `8265`. Leave both alone and say so explicitly, because most tutorials and container entrypoints override the host to make the UI reachable:

```bash
ray start --head --dashboard-host 127.0.0.1 --dashboard-port 8265
```

Never pass `--dashboard-host 0.0.0.0` (or `::`) on a machine with a public interface. In Docker the two binds are different things: the host publishes on loopback only (`-p 127.0.0.1:8265:8265`, which Docker's port-publishing docs say only the Docker host can reach), while inside the container the dashboard must listen on the container's own interface (`--dashboard-host 0.0.0.0` there, private to the Compose network and the host), because a dashboard bound to the container's `127.0.0.1` is not reachable through the published port at all. See [docker.md](docker.md).

Reach the dashboard and the Jobs API through a channel that already authenticates you:

```bash
ssh -L 8265:127.0.0.1:8265 user@203.0.113.10          # then open http://127.0.0.1:8265
ray job submit --address http://127.0.0.1:8265 -- python script.py
ray dashboard cluster.yaml                             # cluster launcher: sets up the same SSH forwarding
kubectl port-forward svc/"$HEAD_SERVICE" 8265:8265    # KubeRay: the RayCluster head service
```

A tailnet ([tailscale.md](tailscale.md)) is the other clean option: the dashboard binds to the tailnet address, and only enrolled devices can route to it. If a browser-facing hostname is unavoidable, put an authenticating TLS proxy in front ([nginx.md](nginx.md), [caddy.md](caddy.md), or [cloudflare.md](cloudflare.md) with Access) and keep the origin on loopback; Ray's docs themselves list "deploy a TLS proxy in front of your Ray cluster" as the pattern.

## 2. Network isolation is the primary boundary

Ray expects "a controlled, isolated network" between all its components. Beyond `8265`, the head node listens on `6379` (head process), `10001` (Ray Client), and every node opens worker ports `10002` to `19999` by default plus several randomised ports. Put every node of a cluster in one private network or security group that admits only the cluster's own members ([cloud-firewalls.md](cloud-firewalls.md), [host.md](host.md), [kubernetes.md](kubernetes.md)), and expose nothing from that group to the internet. The Ray Client port in particular is a remote code execution endpoint by design; use Ray Jobs over the forwarded dashboard port instead of publishing `10001`.

Ray does not isolate jobs from each other. Workloads that must not see each other's data or credentials go on separate clusters.

## 3. Token authentication (Ray 2.52.0 and later)

Starting in Ray 2.52.0 the cluster can require a shared-secret token on every external API and internal connection. Per the Ray docs it is disabled by default in 2.52.0 (as of September 2026, with a plan to enable it by default in a future release) and is "not an alternative to deploying Ray clusters in a controlled network environment", only defence in depth.

```bash
export RAY_AUTH_MODE=token
ray get-auth-token --generate           # writes ~/.ray/auth_token and prints it
RAY_AUTH_MODE=token ray start --head
```

Every node and every client needs the same token. Ray reads it from `RAY_AUTH_TOKEN`, then from the file named by `RAY_AUTH_TOKEN_PATH`, then from `~/.ray/auth_token`; the docs recommend the file paths over the environment variable so other code that reads the environment cannot see it. Copy the file to each node before `ray start`, keep its permissions tight, and never commit it: tokens do not expire and are stored in plaintext ([secrets.md](secrets.md)). The token travels as an HTTP header, so over plain HTTP it is visible to the network; only send it inside the SSH tunnel, tailnet, or TLS proxy from step 1.

On Kubernetes, KubeRay v1.6.0 and later enable this through the `authOptions` field of a `RayCluster`; the operator creates a Secret with a random token and sets `RAY_AUTH_MODE` and `RAY_AUTH_TOKEN` on every Ray container. Clients read it with `kubectl get secrets <name> --template={{.data.auth_token}} | base64 -d`. Without the token, `ray job submit` fails with `401 Unauthorized`.

MFA: Ray has no user accounts, so a second factor can only come from the path to the cluster: the SSH login, the tailnet, or an identity-aware proxy in front of the dashboard ([mfa.md](mfa.md)).

## 4. TLS for the gRPC traffic

Ray can encrypt and mutually authenticate its internal gRPC connections. Export these in the environment of every node, head and workers alike, before Ray starts there; Ray reads them at startup (`RAY_USE_TLS` defaults to `0`), so a plain assignment without `export`, or a variable set after the node started, never reaches the Ray processes:

```bash
export RAY_USE_TLS=1                                 # default 0
export RAY_TLS_SERVER_CERT=/etc/ray/tls/tls.crt      # presented to other endpoints
export RAY_TLS_SERVER_KEY=/etc/ray/tls/tls.key
export RAY_TLS_CA_CERT=/etc/ray/tls/ca.crt           # CA that signs every node's certificate
```

Ray warns that this costs performance (large for small workloads, smaller for large ones) and that it "is not a replacement for network isolation". The docs describe it for the gRPC traffic; for the dashboard and Jobs HTTP API they point to a TLS proxy in front, which is the fronting proxy in step 1.

## Verify

```bash
ss -tlnp | grep 8265                                    # 127.0.0.1:8265 (or the tailnet IP), never 0.0.0.0 or *
ss -tlnp | grep -E ':6379|:10001'                       # private interface only
curl -sI --max-time 5 http://203.0.113.10:8265/         # from another network: connection refused or timeout
# Through the SSH tunnel of step 1, from a machine without the token, with RAY_AUTH_MODE=token on the cluster:
ray job submit --address http://127.0.0.1:8265 -- python -c "print(1)"   # must fail: Unauthorized
```

## Common mistakes

- `--dashboard-host 0.0.0.0` copied from a quickstart so the UI "works" from a laptop; forward the port instead.
- Treating token authentication as permission to expose `8265` to the internet. Ray says the opposite.
- Publishing `10001` for Ray Client convenience. It is unauthenticated code execution unless the token and isolation above are both in place.
- Putting the head node in a security group that also hosts unrelated services; any compromise there reaches every Ray worker.

## Sources (checked September 2026)

- Ray security guidelines (arbitrary code execution, network isolation, TLS is not a replacement, token auth from 2.52.0): https://docs.ray.io/en/latest/ray-security/index.html
- Ray token authentication (`RAY_AUTH_MODE`, `RAY_AUTH_TOKEN`, `RAY_AUTH_TOKEN_PATH`, `ray get-auth-token`, plaintext-header caveat): https://docs.ray.io/en/latest/ray-security/token-auth.html
- `ray start` CLI reference (`--dashboard-host` default, `--dashboard-port` 8265, `--port` 6379, `--ray-client-server-port` 10001): https://docs.ray.io/en/latest/cluster/cli.html
- Configuring Ray (TLS environment variables, ports opened by nodes): https://docs.ray.io/en/latest/ray-core/configure.html
- Configure Ray clusters to use token authentication (KubeRay `authOptions`, 401 without token): https://docs.ray.io/en/latest/cluster/kubernetes/user-guides/kuberay-auth.html
- Docker, port publishing (loopback publishing): https://docs.docker.com/engine/network/port-publishing/
