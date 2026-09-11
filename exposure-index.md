# Exposure index: ports this corpus documents, and where to look them up

You ran a scan and something is listening. This page narrows the search.

A port number does not identify a service. IANA says so about its own registry: traffic on a registered
port need not belong to the service assigned to it, and many of the numbers below are registered to
something other than the service you will find there. Use the owning process from `ss`, not the number, to decide what you
are looking at; the number only tells you which guides are worth opening.

A port missing from this table is not a port nobody has reviewed. It is a port this page does not list.
Identify the process, then search the corpus by service name.

## How to use this

1. `sudo ss -tlnp` to get the listening sockets **and the process that owns each one**. Without `sudo`
   you get the ports but not the process names for sockets owned by other users, which is most of them.
2. Find the port below and open the guides named. More than one may apply.
3. Run **that guide's** Verify section. This page's Verify does not replace it, and cannot: a port being
   bound privately says nothing about whether the service behind it authenticates anyone.

## What binds what, according to this corpus

Rows say what *may* be listening. Where a guide documents a published container mapping rather than the
application's own listener, the row says so, because `-p 3000:8080` means two different ports and only
one of them is the application's.

| Port | May be | Documented in |
| --- | --- | --- |
| 22 | SSH, which should not be publicly reachable | [cloud-firewalls.md](cloud-firewalls.md), [host.md](host.md) |
| 80, 443 | Usually the TLS proxy, but also native HTTPS listeners in the language guides, and Vaultwarden's container port 80 | [nginx.md](nginx.md), [caddy.md](caddy.md), [haproxy.md](haproxy.md), [traefik.md](traefik.md), [apache.md](apache.md), [lighttpd.md](lighttpd.md), [go.md](go.md), [dotnet.md](dotnet.md), [devops-uis.md](devops-uis.md) |
| 81 | Nginx Proxy Manager admin UI (the proxy itself is on 80 and 443) | [devops-uis.md](devops-uis.md) |
| 1234 | LM Studio local server | [model-servers.md](model-servers.md) |
| 1880 | Node-RED editor and admin API, which have no authentication by default | [devops-uis.md](devops-uis.md) |
| 1883 | MQTT, plaintext | [mosquitto.md](mosquitto.md) |
| 2375 | Docker API, plaintext and unauthenticated | [devops-uis.md](devops-uis.md) |
| 2376 | Docker API over TLS. The port is a convention, not proof of client-certificate authentication: `--tls` and `--tlsverify` are different settings | [devops-uis.md](devops-uis.md), [docker.md](docker.md) |
| 3000 | The most crowded port here: 23 guides in this corpus mention it, and the most likely owners are Metabase, Dagster, Gitea, Dokploy, Next.js, SvelteKit's Node adapter (which defaults to `0.0.0.0`), Rails, Flowise, OpenHands, Langfuse, TGI, and the backend behind most proxy examples. Open WebUI's 3000 is a **published host port** mapping to container 8080 | [nextjs.md](nextjs.md), [frontend-frameworks.md](frontend-frameworks.md), [ruby.md](ruby.md), [bi-dashboards.md](bi-dashboards.md), [workflow-orchestrators.md](workflow-orchestrators.md), [devops-uis.md](devops-uis.md), [open-webui.md](open-webui.md), [llm-observability.md](llm-observability.md), [model-servers.md](model-servers.md), [agent-builders.md](agent-builders.md), [chat-uis.md](chat-uis.md), [mcp-servers.md](mcp-servers.md), [fronting-auth.md](fronting-auth.md) |
| 3001 | AnythingLLM, or Uptime Kuma | [chat-uis.md](chat-uis.md), [devops-uis.md](devops-uis.md) |
| 3080 | LibreChat | [agent-builders.md](agent-builders.md) |
| 3210 | LobeChat | [chat-uis.md](chat-uis.md) |
| 3306 | MySQL and MariaDB | [mysql.md](mysql.md), [cloud-firewalls.md](cloud-firewalls.md) |
| 4000 | LiteLLM proxy | [litellm.md](litellm.md) |
| 4180 | oauth2-proxy | [fronting-auth.md](fronting-auth.md) |
| 4200 | Prefect server | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 4222 | NATS client connections | [nats.md](nats.md) |
| 4317, 4318 | OTLP gRPC and OTLP HTTP receivers | [llm-observability.md](llm-observability.md) |
| 5000 | Redash, MLflow tracking server, or a .NET Kestrel default | [bi-dashboards.md](bi-dashboards.md), [mlflow.md](mlflow.md), [dotnet.md](dotnet.md) |
| 5003 | Dify's plugin daemon debugging port, published by the supplied Compose configuration unless you remove or restrict that mapping | [agent-builders.md](agent-builders.md) |
| 5432 | PostgreSQL, and pgvector on the same port | [postgresql.md](postgresql.md), [vector-databases.md](vector-databases.md), [cloud-firewalls.md](cloud-firewalls.md) |
| 5555 | Flower, the Celery monitor | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 5671, 5672 | AMQP over TLS, and AMQP plaintext | [rabbitmq.md](rabbitmq.md) |
| 5678 | n8n | [n8n.md](n8n.md) |
| 6001, 6002 | Coolify real-time updates and terminal | [devops-uis.md](devops-uis.md) |
| 6006 | Arize Phoenix | [llm-observability.md](llm-observability.md) |
| 6333, 6334, 6335 | Qdrant REST, gRPC, and internal cluster gRPC | [vector-databases.md](vector-databases.md) |
| 6362 | Neo4j backup | [neo4j.md](neo4j.md) |
| 6379 | Redis, Valkey, or the Ray head node | [redis.md](redis.md), [ray.md](ray.md), [cloud-firewalls.md](cloud-firewalls.md) |
| 7000 | frp server | [tunnels.md](tunnels.md) |
| 7233 | Temporal frontend gRPC | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 7473, 7474, 7687 | Neo4j HTTPS, HTTP, and Bolt | [neo4j.md](neo4j.md) |
| 7860 | Gradio, Stable Diffusion WebUI, or Langflow | [gradio.md](gradio.md), [image-gen-uis.md](image-gen-uis.md), [agent-builders.md](agent-builders.md) |
| 8000 | SurrealDB, Chroma, Triton HTTP, Coolify, Vaultwarden outside Docker, or Portainer's Edge agent tunnel | [surrealdb.md](surrealdb.md), [vector-databases.md](vector-databases.md), [model-servers.md](model-servers.md), [devops-uis.md](devops-uis.md) |
| 8001, 8002 | Triton gRPC and Triton Prometheus metrics | [model-servers.md](model-servers.md) |
| 8080 | llama.cpp, Weaviate HTTP, Airflow, code-server, Open WebUI's container port, Dify's nginx when mapped to `127.0.0.1:8080`, Spring Boot, Go, and the Vast.ai Jupyter deployment | [model-servers.md](model-servers.md), [vector-databases.md](vector-databases.md), [workflow-orchestrators.md](workflow-orchestrators.md), [code-server.md](code-server.md), [open-webui.md](open-webui.md), [agent-builders.md](agent-builders.md), [java.md](java.md), [go.md](go.md), [gpu-clouds.md](gpu-clouds.md) |
| 8088 | Apache Superset | [bi-dashboards.md](bi-dashboards.md) |
| 8123 | ClickHouse HTTP, plaintext | [clickhouse.md](clickhouse.md) |
| 8188 | ComfyUI | [image-gen-uis.md](image-gen-uis.md) |
| 8222 | NATS monitoring endpoints | [nats.md](nats.md) |
| 8233 | Temporal Web UI as started by `temporal server start-dev`, which is the context this corpus documents | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 8265 | Ray dashboard | [ray.md](ray.md) |
| 8443 | ClickHouse HTTPS, the Kubernetes Dashboard forwarding example, and the configured HTTPS listeners in the Gradio, Python, Java and Ruby guides | [clickhouse.md](clickhouse.md), [devops-uis.md](devops-uis.md), [gradio.md](gradio.md), [python.md](python.md), [java.md](java.md), [ruby.md](ruby.md) |
| 8501 | Streamlit | [streamlit.md](streamlit.md) |
| 8883 | MQTT over TLS | [mosquitto.md](mosquitto.md) |
| 8888 | Jupyter, including the Vast.ai and RunPod deployments | [jupyter.md](jupyter.md), [gpu-clouds.md](gpu-clouds.md) |
| 9000 | ClickHouse native TCP (plaintext), MinIO's S3 API, PHP-FPM, TGI's Prometheus listener, or Portainer's legacy HTTP port | [clickhouse.md](clickhouse.md), [minio.md](minio.md), [php.md](php.md), [model-servers.md](model-servers.md), [devops-uis.md](devops-uis.md) |
| 9004, 9005, 9009, 9010 | ClickHouse MySQL compatibility, PostgreSQL compatibility, and interserver replica traffic over HTTP and HTTPS | [clickhouse.md](clickhouse.md) |
| 9090 | InvokeAI. Prometheus also defaults here, though its guide does not state the number | [image-gen-uis.md](image-gen-uis.md), [admin-uis.md](admin-uis.md) |
| 9091 | Milvus WebUI, or Authelia | [vector-databases.md](vector-databases.md), [fronting-auth.md](fronting-auth.md) |
| 9092, 9093 | Kafka plaintext and SASL_SSL listeners. Which port carries which is configured, not fixed | [kafka.md](kafka.md) |
| 9200 | Elasticsearch and OpenSearch HTTP | [elasticsearch.md](elasticsearch.md) |
| 9292 | Puma standalone, whose default bind is all interfaces | [ruby.md](ruby.md) |
| 9440 | ClickHouse native TCP over TLS | [clickhouse.md](clickhouse.md) |
| 9443 | Portainer HTTPS UI | [devops-uis.md](devops-uis.md) |
| 10001 | Ray Client server, which executes code | [ray.md](ray.md) |
| 10002 to 19999 | Ray worker ports, allocated across this whole range by default, plus several randomized ports. Anything in this range on a Ray node may be a worker rather than the service the row below suggests | [ray.md](ray.md) |
| 11211 | Memcached. Check UDP as well as TCP | [memcached.md](memcached.md) |
| 11434 | Ollama | [ollama.md](ollama.md) |
| 15672 | RabbitMQ management UI | [rabbitmq.md](rabbitmq.md) |
| 19530 | Milvus gRPC | [vector-databases.md](vector-databases.md) |
| 27017 | MongoDB | [mongodb.md](mongodb.md), [cloud-firewalls.md](cloud-firewalls.md) |
| 30000 | SGLang | [model-servers.md](model-servers.md) |
| 50051 | Weaviate gRPC | [vector-databases.md](vector-databases.md) |
| 51820/UDP | WireGuard, in the configured example here. The port is chosen, not assigned | [tunnels.md](tunnels.md) |

## Verify

**This is a baseline inventory, not a security check, and not a proof of completeness.** It gives you a
list of the listeners and routes it discovered. It cannot establish that the list is complete: a
container on a bridge network publishes no host port and holds its sockets in another network
namespace, and a container on routed IPv6 accepts traffic on its own address whatever the host
publishes. Reconcile what you find here against your interface addresses, container addresses and
namespaces, and your routing and publishing configuration before believing the inventory is whole.

It establishes nothing at all about whether those services are safe to expose, and no checklist on an
index page can. That claim belongs to each service's own guide, and even there the Verify blocks are
worked examples over sampled URLs, not an enumeration of your application's sensitive routes.

```bash
sudo ss -tlnp                    # listening TCP sockets, with the owning process
sudo ss -tlunp                   # again including UDP, which Memcached and WireGuard answer on
docker ps --format '{{.Names}}\t{{.Ports}}'   # published container ports, which the host view can miss
```

`ss` reports sockets in its own network namespace, so a container's listeners are not all visible from
the host. A diagnostic such as `Cannot open netlink socket` means the command failed: empty output with
a zero exit status is not a pass.

From a second machine on a different network, against a host **you own or are authorized to test**.
Run these against every public address the host answers on, not just one; a host with several
interfaces or a NAT address beside an elastic address has several inbound paths. Substitute a literal
address, and check the target Nmap prints before you read the result: the
placeholder below is a hostname as far as Nmap is concerned, and if it resolves in your environment
Nmap will scan whatever it resolved to.

```bash
sudo nmap -Pn -p- REPLACE_WITH_A_LITERAL_IPV4_ADDRESS            # TCP over IPv4
sudo nmap -Pn -6 -p- REPLACE_WITH_A_LITERAL_IPV6_ADDRESS         # TCP over IPv6, which the line above never covers
sudo nmap -Pn -sU --top-ports 100 REPLACE_WITH_A_LITERAL_IPV4_ADDRESS      # UDP, preliminary only
sudo nmap -Pn -6 -sU --top-ports 100 REPLACE_WITH_A_LITERAL_IPV6_ADDRESS   # UDP over IPv6
```

UDP scanning needs privilege and returns `open|filtered` when it cannot distinguish the two, so a
clean-looking UDP result is weaker evidence than a clean TCP one. Treat the top-100 scan as a first
pass and probe the UDP ports your own inventory names.

Four things to establish, and none of them is "the service is secure":

1. **Every listening socket is attributed**, to a named owning process or to an identified kernel
   service or interface. Kernel WireGuard is the case that breaks process attribution: it owns its UDP
   socket in the kernel, so `ss -p` names no process and `sudo` does not create one. A port appearing
   in the table above is a hint about which guides to read, not an identification of what is running.
2. **Every socket's bind address is deliberate.** `127.0.0.1`, `::1`, a private address or a tailnet
   address, unless you can say why it is public.
3. **Every inbound route is inventoried, not just the ones a port scan finds.** A scan of your public
   address says nothing about an outbound tunnel. An application on loopback reached through
   [tunnels.md](tunnels.md), [cloudflare.md](cloudflare.md) or [tailscale.md](tailscale.md) is exposed
   at that hostname while your host shows no open inbound port at all. List every hostname, every
   literal address the host answers on including container addresses, every tunnel, proxy and alternate
   virtual host, and every URL path a proxy routes to a different backend. Each is its own route, and a
   scan by hostname does not cover a request made to a bare address.
4. **Each reachable service has been through its own guide**, by every route from condition 3, not only
   the ones the scan surfaced. Those guides are where the authentication and TLS checks live.

Then keep going: enumerate your own sensitive routes and request each one anonymously and as an
unauthorized user. A deployment can satisfy all four conditions above and still serve private data from
an endpoint no guide here knows the name of.

## Sources (checked September 2026)

- `ss` manual, including that it reports sockets within a network namespace:
  https://man7.org/linux/man-pages/man8/ss.8.html
- Nmap port specification, for `-p-` and `--top-ports`:
  https://nmap.org/book/man-port-specification.html
- Nmap host discovery, for `-Pn`: https://nmap.org/book/man-host-discovery.html
- Nmap target specification, for how a target string is resolved:
  https://nmap.org/book/man-target-specification.html
- Nmap scan techniques, for `-sU` and the `open|filtered` state:
  https://nmap.org/book/man-port-scanning-techniques.html
- Nmap miscellaneous options, for `-6`: https://nmap.org/book/man-misc-options.html
- Nmap legal issues, on scanning only hosts you are authorized to scan:
  https://nmap.org/book/legal-issues.html
- Docker `container ls`, for `--format` and the `.Names` and `.Ports` placeholders:
  https://docs.docker.com/reference/cli/docker/container/ls/
- Docker port publishing, for the `-p host:container` mapping this page distinguishes:
  https://docs.docker.com/engine/network/port-publishing/
- Docker daemon protection, for the difference between `--tls` and `--tlsverify` noted on port 2376:
  https://docs.docker.com/engine/security/protect-access/
- IANA Service Name and Transport Protocol Port Number Registry, including its statement that traffic on
  a port need not belong to the assigned service:
  https://www.iana.org/assignments/service-names-port-numbers
- RFC 6335, which defines the registry and the dynamic and private range 49152 to 65535:
  https://www.rfc-editor.org/rfc/rfc6335.html
- Each application default above is documented in the guide its row links to, and that guide cites the
  vendor page for it.
