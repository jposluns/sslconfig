# Common mistakes

The recurring findings behind exposed AI-assisted projects, distilled from the guides in this repository. Each line links to the fix.

1. **Binding to `0.0.0.0` to fix a connection problem** and never binding back. Loopback is the default posture; expose only through a TLS-terminating, authenticated layer. ([README](README.md))
2. **Publishing Docker ports and trusting UFW.** Published container ports bypass UFW's rules entirely; `ufw deny 3000` does not protect `-p 3000:3000`. ([docker.md](docker.md))
3. **Default credentials left in place**: mongo-express `admin`/`pass`, Grafana `admin`/`admin`, RabbitMQ `guest`, MinIO `minioadmin`. Scanners try these first. ([admin-uis.md](admin-uis.md), [rabbitmq.md](rabbitmq.md), [minio.md](minio.md))
4. **`OLLAMA_HOST=0.0.0.0`** on a machine with a public interface: the full model API with no authentication and no TLS. ([ollama.md](ollama.md))
5. **Disabling TLS verification in clients** (`verify=False`, `rejectUnauthorized: false`, `curl -k`, `NODE_TLS_REJECT_UNAUTHORIZED=0`) instead of distributing trust for a self-signed certificate. ([self-signed.md](self-signed.md))
6. **Secrets committed to the repository**, baked into images, or printed to logs, then "deleted" instead of rotated. ([secrets.md](secrets.md))
7. **Auth on the home page but not the API.** `/` redirects to a login while `/api/...` serves data unauthenticated. Test the API paths. ([authentication.md](authentication.md))
8. **Plain HTTP still serving next to HTTPS** instead of redirecting, leaving credentials to cross in cleartext on the forgotten port. (Every server guide's redirect step.)
9. **Quick tunnels left running**: `trycloudflare.com` URLs and Gradio `share=True` links are unauthenticated publication, not deployment. ([cloudflare.md](cloudflare.md), [gradio.md](gradio.md))
10. **Security features switched off to silence errors**: `xpack.security.enabled: false`, MongoDB without `authorization: enabled`, Redis with an empty `requirepass`. The error was the protection. ([elasticsearch.md](elasticsearch.md), [mongodb.md](mongodb.md), [redis.md](redis.md))
11. **`Access-Control-Allow-Origin: *` on endpoints that use cookies or keys**, or reflecting whatever Origin arrives. ([cors.md](cors.md))
12. **Database ports open to `0.0.0.0/0` in cloud firewalls** because a remote client needed access once. ([cloud-firewalls.md](cloud-firewalls.md))
13. **Firebase or Supabase rules left open** (`allow read, write: if true;`, RLS disabled) because the client key "worked": the key is public by design, the rules are the security. ([firebase-supabase.md](firebase-supabase.md))
14. **Single-factor logins on human-facing services** when the stack or a fronting layer supports MFA. ([mfa.md](mfa.md))

Run the [README verification checklist](README.md#verification-checklist) after any fix; several of these only surface when tested from outside the host.
