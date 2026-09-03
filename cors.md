# CORS: allow your origins, not everyone's

CORS misconfiguration does not expose a port; it lets hostile websites use your users' browsers, cookies included, against your API. AI assistants reach for `Access-Control-Allow-Origin: *` the moment a browser console shows a CORS error; that is the wrong fix for any API that authenticates.

## Rules

1. **List exact origins.** `Access-Control-Allow-Origin` names the site(s) allowed to call the API from a browser:
   ```
   Access-Control-Allow-Origin: https://app.example.com
   ```
2. **Never combine `*` with credentials.** Browsers refuse `Access-Control-Allow-Origin: *` together with `Access-Control-Allow-Credentials: true`; configurations that "fix" this by reflecting whatever `Origin` header arrives recreate `*` for credentialed requests, which is worse. Reflect only origins checked against an explicit allow list.
3. **`*` is acceptable** only for genuinely public, unauthenticated, read-only resources.
4. **CORS is not authentication.** It controls browsers, not attackers with curl; every endpoint still authenticates per [authentication.md](authentication.md).

## Framework examples

Express (`cors` package):

```js
const cors = require('cors');
app.use(cors({ origin: ['https://app.example.com'], credentials: true }));
```

FastAPI:

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

Keep the origin list in configuration per environment rather than hardcoding localhost origins into production.

## Verify

```bash
curl -s -o /dev/null -D - https://api.example.com/data -H "Origin: https://evil.example" | grep -i access-control
# expect: no Access-Control-Allow-Origin echoing the hostile origin
curl -s -o /dev/null -D - https://api.example.com/data -H "Origin: https://app.example.com" | grep -i access-control
# expect: your origin, and Allow-Credentials only if you use cookies
```

## Sources (checked September 2026)

- MDN: Cross-Origin Resource Sharing: https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS
