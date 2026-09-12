# Rented GPUs: RunPod, Vast.ai, Lambda, Modal

Unlike the major clouds, most rented-GPU platforms hand you a box (or a serverless function) without a default-deny firewall in front of it. Whatever port a template or container binds, SSH, a Jupyter notebook, a model server, is reachable the moment it listens, and serverless GPU platforms differ in what counts as public by default. Treat every listener the same way you would on your own hardware: bind it privately or authenticate it, per [ollama.md](ollama.md) and [model-servers.md](model-servers.md).

## RunPod

Exposed HTTP ports (the "Expose HTTP Ports" pod setting) go through RunPod's proxy at `https://[POD_ID]-[INTERNAL_PORT].proxy.runpod.net`; the proxy terminates HTTPS automatically, "All connections are secured with HTTPS, even if your internal service uses HTTP," but the resulting URL is publicly reachable by anyone who has it, so a bare Jupyter server or model API on an exposed HTTP port still needs its own authentication.

Exposed TCP ports get "direct TCP forwarding with a public IP address" instead, and TLS is not automatic there: RunPod's own docs say to "implement TLS in your application when handling sensitive data over TCP." Secure every template listener, including notebooks, before exposing its port; a notebook exposed as raw TCP with no application-level password is fully open.

A "symmetrical port mapping" option lets a template ask for matching internal and external port numbers by specifying a value above 70000 in its TCP configuration. That value is not a port: RunPod's documentation says such numbers are not valid ports and serve only to signal the request, and the real assignment arrives in the pod's environment (for example `$RUNPOD_TCP_PORT_70000`). It is a convenience for the pod's own scripts, not a security boundary, and the port is still public once mapped.

## Vast.ai

Rented instances open ports per launch mode (port 22 for SSH mode, port 22 plus 8080 for Jupyter mode by default); each internal port maps to a random external port on a shared public IP, and once a port is mapped it is reachable from the internet with no firewall step described in Vast.ai's docs.

The Instance Portal fronts web apps on the instance with a reverse proxy (Caddy) when the external and internal ports differ, and secures access with a token rather than a login: "a secure token is appended to the link to prevent unauthorised access to your applications," configured through the `PORTAL_CONFIG` environment variable. Do not strip that token off a shared link, and do not assume an app is private just because it sits behind the portal's port remapping.

## Lambda

Lambda's Public Cloud firewall is deny-by-default for inbound traffic with two exceptions: "By default, Lambda allows only incoming ICMP traffic or TCP traffic on port 22 (SSH)." Everything else, a Jupyter notebook, a model server port, needs an explicit firewall rule (global, workspace-wide rules, or a per-instance ruleset attached at launch); Lambda's own guidance is blunt about the tradeoff: "Each port you open increases the attack surface of your instances."

Opening a rule makes the port reachable from whatever source range you allow, with no authentication of its own, so pair the rule with the listener's native auth or a proxy in front, not the firewall rule alone.

## Modal

Modal's serverless constructs default differently depending on shape. Endpoints and Servers "require authentication by default" and need an explicit `--unauthenticated` flag to go public. Web Functions are the opposite: they are "publicly available by default," and stay that way until the function sets `requires_proxy_auth=True`.

Where proxy auth is enabled, callers authenticate with a Token ID and Token Secret pair, either as separate `Modal-Key` and `Modal-Secret` headers or combined as `Authorization: Bearer <token_id>.<token_secret>` (Modal notes this mirrors "the same scheme the OpenAI API uses"). A protected endpoint called without credentials returns 401 with "missing credentials for proxy authorization." Check which default your construct uses before deploying; do not assume a Web Function is private.

## The pattern, whatever the platform

The platform's own controls (RunPod's proxy TLS, Vast.ai's portal token, Lambda's firewall rules, Modal's proxy auth) are necessary but not sufficient on their own. How to bind the model server depends on which kind of proxy is in front of it. RunPod's HTTP proxy reaches the pod over its exposed network interface rather than through a local backend, so the service must bind `0.0.0.0` inside the pod; RunPod's own troubleshooting guidance is explicit that binding to `localhost` only will keep the proxy from reaching it. Vast.ai's Instance Portal is the opposite case: it is a local reverse proxy (Caddy) running on the instance itself, so the app it forwards to can stay on loopback behind it, the same pattern as an authenticating proxy on your own hardware. Whichever binding the platform's proxy needs, require the server's own API key on top as well, exactly as [ollama.md](ollama.md) and [model-servers.md](model-servers.md) describe. A platform-level control that goes away later, a firewall rule deleted, a template rebuilt without a flag, should not be the only thing standing between the listener and the internet.

MFA: none of these platforms add a second factor to the workload itself. The account you log into RunPod, Vast.ai, Lambda, or Modal with should have MFA enabled ([mfa.md](mfa.md)); an API key or proxy-auth token secures a machine client, and is a separate control from your platform login.

## Verify

```bash
ss -tlnp                                   # enumerate every listening port on the box
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8888/api/contents   # 403 without the token
curl -sS -o /dev/null -w '%{http_code}\n' "https://REPLACE_WITH_POD_ID-REPLACE_WITH_PORT.proxy.runpod.net/REPLACE_WITH_PROTECTED_PATH"
# 401 without credentials, against an actual protected endpoint rather than "/" (RunPod's proxy hostname form; substitute the equivalent for your platform)
curl -sS -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer REPLACE_WITH_TOKEN" "https://REPLACE_WITH_POD_ID-REPLACE_WITH_PORT.proxy.runpod.net/REPLACE_WITH_PROTECTED_PATH"
# 200 with the correct credentials, so the pair shows the listener itself gates access, not only the proxy hostname's obscurity
```

Every port `ss` shows listening should be either closed (not exposed at the platform layer) or authenticated (the listener itself demands a key, token, or login). A Jupyter server that answers without its token is a finding, whichever of these platforms it runs on.

## Common mistakes

- Assuming a rented box has a default-deny firewall like a major cloud's security group; most rented-GPU platforms do not.
- Treating a template's HTTPS proxy URL as proof the underlying service is authenticated; the proxy secures transport, not access.
- Leaving a Modal Web Function without `requires_proxy_auth=True` because Endpoints and Servers are private by default and it is easy to assume Web Functions are too.
- Reusing a rented box's platform login (RunPod/Vast.ai/Lambda/Modal account) as if it were the same thing as the workload's own authentication; they are separate controls.

## Sources (checked September 2026)

- RunPod expose ports (proxy HTTPS, TCP forwarding): https://docs.runpod.io/pods/configuration/expose-ports
- Vast.ai networking and ports (default ports, port mapping): https://docs.vast.ai/guides/instances/connect/networking
- Vast.ai Instance Portal (PORTAL_CONFIG, Caddy reverse proxy, secure-token links): https://docs.vast.ai/guides/instances/connect/instance-portal
- Lambda Cloud firewalls (default-deny inbound, SSH/ICMP exception, rule types): https://docs.lambda.ai/public-cloud/firewalls/
- Modal proxy auth for web endpoints (Endpoints/Servers vs Web Functions defaults, headers): https://modal.com/docs/guide/webhook-proxy-auth
