# Exposure index: what is listening, and which guide fixes it

`ss -tlnp` tells you a port is open. It does not tell you what is behind it, whether that thing
authenticates anyone, or which guide here covers it. This page is the lookup between the two.

Run the check, take each port you did not expect, and find it below. A listening port that is not in
this table is a service nobody has reviewed against this corpus, which is the state everything here
exists to catch. The bind address matters more than the port: loopback or a private address is the
default posture, and a public bind is a deliberate decision you should be able to defend
([web-exposure.md](web-exposure.md), [common-mistakes.md](common-mistakes.md)).

Every default below is taken from the guide it links to, which cites the vendor for it.

## Ports that identify one service

| Port | What listens there | Guide |
| --- | --- | --- |
| 81 | Nginx Proxy Manager admin UI (the proxy itself is on 80 and 443) | [devops-uis.md](devops-uis.md) |
| 1234 | LM Studio local server | [model-servers.md](model-servers.md) |
| 1883 | MQTT, plaintext | [mosquitto.md](mosquitto.md) |
| 2375 | Docker API, plaintext and unauthenticated | [devops-uis.md](devops-uis.md) |
| 2376 | Docker API, TLS with client certificates | [devops-uis.md](devops-uis.md) |
| 3080 | LibreChat | [agent-builders.md](agent-builders.md) |
| 3210 | LobeChat | [chat-uis.md](chat-uis.md) |
| 3306 | MySQL and MariaDB | [mysql.md](mysql.md) |
| 4000 | LiteLLM proxy | [litellm.md](litellm.md) |
| 4200 | Prefect server | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 4222 | NATS client connections | [nats.md](nats.md) |
| 4317 | OTLP gRPC receiver | [llm-observability.md](llm-observability.md) |
| 4318 | OTLP HTTP receiver | [llm-observability.md](llm-observability.md) |
| 5432 | PostgreSQL, and pgvector on the same port | [postgresql.md](postgresql.md), [vector-databases.md](vector-databases.md) |
| 5555 | Flower, the Celery monitor | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 5671 | AMQP over TLS | [rabbitmq.md](rabbitmq.md) |
| 5672 | AMQP, plaintext | [rabbitmq.md](rabbitmq.md) |
| 5678 | n8n | [n8n.md](n8n.md) |
| 6006 | Arize Phoenix | [llm-observability.md](llm-observability.md) |
| 6333 | Qdrant HTTP | [vector-databases.md](vector-databases.md) |
| 6334 | Qdrant gRPC | [vector-databases.md](vector-databases.md) |
| 6379 | Redis; also the Ray head node port | [redis.md](redis.md), [ray.md](ray.md) |
| 7233 | Temporal frontend gRPC | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 7473 | Neo4j HTTPS | [neo4j.md](neo4j.md) |
| 7474 | Neo4j HTTP | [neo4j.md](neo4j.md) |
| 7687 | Neo4j Bolt | [neo4j.md](neo4j.md) |
| 7860 | Gradio, and the image-generation and agent UIs built on it | [gradio.md](gradio.md), [image-gen-uis.md](image-gen-uis.md), [agent-builders.md](agent-builders.md) |
| 8001 | Triton gRPC | [model-servers.md](model-servers.md) |
| 8002 | Triton Prometheus metrics | [model-servers.md](model-servers.md) |
| 8088 | Apache Superset | [bi-dashboards.md](bi-dashboards.md) |
| 8123 | ClickHouse HTTP, plaintext | [clickhouse.md](clickhouse.md) |
| 8188 | ComfyUI | [image-gen-uis.md](image-gen-uis.md) |
| 8222 | NATS monitoring endpoints | [nats.md](nats.md) |
| 8233 | Temporal Web UI | [workflow-orchestrators.md](workflow-orchestrators.md) |
| 8265 | Ray dashboard | [ray.md](ray.md) |
| 8443 | ClickHouse HTTPS | [clickhouse.md](clickhouse.md) |
| 8501 | Streamlit | [streamlit.md](streamlit.md) |
| 8883 | MQTT over TLS | [mosquitto.md](mosquitto.md) |
| 8888 | Jupyter | [jupyter.md](jupyter.md) |
| 9090 | InvokeAI | [image-gen-uis.md](image-gen-uis.md) |
| 9091 | Milvus WebUI | [vector-databases.md](vector-databases.md) |
| 9092 | Kafka, plaintext listener | [kafka.md](kafka.md) |
| 9093 | Kafka SASL_SSL listener | [kafka.md](kafka.md) |
| 9200 | Elasticsearch and OpenSearch HTTP | [elasticsearch.md](elasticsearch.md) |
| 9440 | ClickHouse native TCP over TLS | [clickhouse.md](clickhouse.md) |
| 9443 | Portainer HTTPS UI | [devops-uis.md](devops-uis.md) |
| 10001 | Ray Client server, which executes code | [ray.md](ray.md) |
| 11211 | Memcached (check UDP too) | [memcached.md](memcached.md) |
| 11434 | Ollama | [ollama.md](ollama.md) |
| 15672 | RabbitMQ management UI | [rabbitmq.md](rabbitmq.md) |
| 19530 | Milvus gRPC | [vector-databases.md](vector-databases.md) |
| 27017 | MongoDB | [mongodb.md](mongodb.md) |
| 30000 | SGLang | [model-servers.md](model-servers.md) |
| 50051 | Weaviate gRPC | [vector-databases.md](vector-databases.md) |

## Ports that several services share

Finding one of these open tells you less. Check which process owns it in the `ss -tlnp` output, then
read the guide that matches.

| Port | What might be listening | Guides |
| --- | --- | --- |
| 80, 443 | The TLS proxy, and only the TLS proxy | [nginx.md](nginx.md), [caddy.md](caddy.md), [haproxy.md](haproxy.md), [traefik.md](traefik.md), [apache.md](apache.md), [lighttpd.md](lighttpd.md) |
| 3000 | The most common application default: Next.js, Rails and other app servers, Open WebUI, Grafana-style dashboards, Langfuse, Dify, and the backend behind most proxy examples here | [nextjs.md](nextjs.md), [ruby.md](ruby.md), [open-webui.md](open-webui.md), [llm-observability.md](llm-observability.md), [agent-builders.md](agent-builders.md), [chat-uis.md](chat-uis.md), [mcp-servers.md](mcp-servers.md), [fronting-auth.md](fronting-auth.md) |
| 3001 | AnythingLLM, or Uptime Kuma | [chat-uis.md](chat-uis.md), [devops-uis.md](devops-uis.md) |
| 5000 | MLflow tracking server, or Metabase, Superset and Redash depending on how they were installed | [mlflow.md](mlflow.md), [bi-dashboards.md](bi-dashboards.md) |
| 8000 | SurrealDB, Chroma, Triton HTTP, or Portainer's Edge agent tunnel | [surrealdb.md](surrealdb.md), [vector-databases.md](vector-databases.md), [model-servers.md](model-servers.md), [devops-uis.md](devops-uis.md) |
| 8080 | llama.cpp, Weaviate HTTP, Airflow, or code-server | [model-servers.md](model-servers.md), [vector-databases.md](vector-databases.md), [workflow-orchestrators.md](workflow-orchestrators.md), [code-server.md](code-server.md) |
| 9000 | ClickHouse native TCP (plaintext), MinIO's S3 API, PHP-FPM, or Portainer's legacy HTTP port | [clickhouse.md](clickhouse.md), [minio.md](minio.md), [php.md](php.md), [devops-uis.md](devops-uis.md) |

## Verify

```bash
ss -tlnp                                    # every listening TCP socket, with the owning process
ss -tlunp                                   # again including UDP, which memcached and others answer on

# from a second machine on a different network, not from this host
nmap -Pn -p- 203.0.113.10                   # only the TLS proxy ports may be open
```

Read the result against this table. Three things must all hold, and the last one is the one that
usually fails:

1. Every listening port appears above, or you can name the service and say why it is running.
2. Every one of them is bound to `127.0.0.1`, a private address, or a tailnet address, except the TLS
   proxy on 80 and 443.
3. The external scan shows nothing except those proxy ports. Checking from the host proves nothing:
   published container ports bypass the host firewall ([docker.md](docker.md)), and a rule you can see
   locally is not a rule that stopped anything.

A port you cannot account for is the finding. Do not close the exercise by assuming it is harmless.

## Sources (checked September 2026)

- IANA Service Name and Transport Protocol Port Number Registry (the registry for assigned ports; most
  of the application defaults above are unregistered and come from the vendor instead):
  https://www.iana.org/assignments/service-names-port-numbers
- RFC 6335, which defines the registry and the dynamic and private port range 49152 to 65535:
  https://www.rfc-editor.org/rfc/rfc6335.html
- Every other default in this table is documented in the guide its row links to, and each of those
  guides cites the vendor page for it. This page deliberately does not repeat those citations, so that
  a default is recorded in exactly one place and cannot drift between two.
