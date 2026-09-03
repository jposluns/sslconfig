#!/usr/bin/env bash
# Regenerates site/llms-full.txt (every guide concatenated into one file).
# Run from the repository root after adding or editing guides.
set -euo pipefail

out="site/llms-full.txt"
files=(
  README.md
  free-certificates.md self-signed.md cloudflare.md tailscale.md
  authentication.md mfa.md secrets.md
  apache.md nginx.md lighttpd.md caddy.md haproxy.md traefik.md
  nodejs.md python.md docker.md kubernetes.md
  host.md cloud-firewalls.md paas.md
  postgresql.md mysql.md mongodb.md redis.md elasticsearch.md minio.md
  rabbitmq.md mosquitto.md
  jupyter.md ollama.md open-webui.md litellm.md model-servers.md
  gradio.md streamlit.md n8n.md code-server.md
  admin-uis.md cors.md headers.md firebase-supabase.md common-mistakes.md
)

{
  echo "# sslconfig.ai: all guides in one file"
  echo
  echo "> Generated from https://github.com/jposluns/sslconfig (CC0 1.0)."
  echo "> Per-guide index: https://sslconfig.ai/llms.txt"
  for f in "${files[@]}"; do
    echo
    echo "======================================================================"
    echo "==> ${f}"
    echo "======================================================================"
    echo
    cat "$f"
  done
} > "$out"

echo "wrote $out ($(wc -c < "$out") bytes, ${#files[@]} files)"
