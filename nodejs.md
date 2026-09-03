# Node.js and Express: TLS and authentication

Preferred production layout: bind the Node app to `127.0.0.1` and terminate TLS in a reverse proxy ([caddy.md](caddy.md), [nginx.md](nginx.md)) or behind [cloudflare.md](cloudflare.md). Node can also terminate TLS itself, shown below. Get a certificate per [free-certificates.md](free-certificates.md) or [self-signed.md](self-signed.md).

## 1. HTTPS directly in Node

```js
const https = require('node:https');
const fs = require('node:fs');
const express = require('express');

const app = express();

const options = {
  key:  fs.readFileSync('/etc/ssl/private/server.key'),
  cert: fs.readFileSync('/etc/ssl/certs/server.crt'),   // certificate plus chain
};

https.createServer(options, app).listen(443);

// Port 80 exists only to redirect
require('node:http').createServer((req, res) => {
  res.writeHead(301, { Location: `https://${req.headers.host}${req.url}` });
  res.end();
}).listen(80);
```

Binding ports below 1024 needs root or `CAP_NET_BIND_SERVICE`; running the app as root is a bad trade, which is one more reason to prefer the proxy layout.

## 2. Behind a proxy: tell Express about it

```js
app.set('trust proxy', 1);   // makes req.secure and secure cookies work behind 1 proxy hop
```

Security headers, including Strict-Transport-Security, via helmet:

```js
const helmet = require('helmet');
app.use(helmet());
```

## 3. Authentication

Follow [authentication.md](authentication.md). The pieces most Node projects need:

Password hashing (bcrypt; the `argon2` package is the equivalent alternative):

```js
const bcrypt = require('bcrypt');
const hash = await bcrypt.hash(password, 12);
const ok   = await bcrypt.compare(password, hash);
```

Sessions with hardened cookies (express-session):

```js
const session = require('express-session');
app.use(session({
  secret: process.env.SESSION_SECRET,      // long random value from the environment
  resave: false,
  saveUninitialized: false,
  cookie: { secure: true, httpOnly: true, sameSite: 'lax' },
}));
```

Rate-limit the login route (express-rate-limit v7):

```js
const rateLimit = require('express-rate-limit');
app.use('/login', rateLimit({ windowMs: 15 * 60 * 1000, limit: 20 }));
```

API keys and tokens come from `process.env`, never from literals in the source. Generate them per [authentication.md](authentication.md) and compare with `crypto.timingSafeEqual` where you check them yourself.

## 4. Client-side TLS discipline

- Never set `NODE_TLS_REJECT_UNAUTHORIZED=0` and never pass `rejectUnauthorized: false`; both disable certificate validation for every connection.
- For an internal CA or self-signed server, point Node at the CA instead: `NODE_EXTRA_CA_CERTS=/path/ca.crt` (see [self-signed.md](self-signed.md)).

## 5. Verify

```bash
curl -sI http://example.com/         # expect 301 with a https:// Location
curl -sI https://example.com/        # succeeds without -k; shows helmet's headers
curl -s  https://example.com/api     # expect 401/403 without credentials
ss -tlnp | grep node                 # behind a proxy: bound to 127.0.0.1 only
```

## Sources (checked September 2026)

- Node.js HTTPS module: https://nodejs.org/api/https.html
- Express behind proxies: https://expressjs.com/en/guide/behind-proxies.html
- helmet: https://helmetjs.github.io/
