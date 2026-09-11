# Next.js: authentication that actually gates Route Handlers, Server Actions, and data

A Next.js app has many entry points: pages, layouts, Route Handlers (`app/**/route.ts`), and every exported Server Action, which the Next.js docs describe as reachable by a direct POST whether or not your UI calls it. A check that lives only in a layout or in `proxy.ts` (the file Next.js 16 renamed from `middleware.ts`) leaves the other entry points open. Next.js supplies cookies and sessions as primitives, not a login system; the login is yours or a library's.

## 1. Bind privately; TLS comes from the platform or the proxy

On Vercel and similar platforms the platform terminates TLS; nothing to configure ([paas.md](paas.md)). Self-hosted, `next start` listens on `0.0.0.0:3000` by default; bind to loopback and put a reverse proxy in front, which the Next.js self-hosting guide itself recommends, with TLS and headers per [nodejs.md](nodejs.md), [nginx.md](nginx.md), or [caddy.md](caddy.md).

```bash
next build && next start -H 127.0.0.1 -p 3000    # or PORT=3000; PORT cannot be set in .env
```

## 2. Put the check where the data is

The Next.js authentication guide's rule: create a Data Access Layer (DAL) with a `verifySession()` function and call it from every data request, Server Action, and Route Handler. Its reasons, paraphrased from the authentication and data-security guides:

- Layouts do not re-render on client navigation, so a session check there does not run on every route change, and a layout that returns `null` does not stop nested segments or Server Actions from running.
- Server Actions and Route Handlers get "the same security considerations as public-facing API endpoints"; a page-level check "does not extend to the Server Actions defined within it".
- Proxy "should not be your only line of defense": use it for optimistic redirects that read the cookie only, never database lookups. A `matcher` change can silently remove Proxy coverage from a Server Action.

```ts
// app/lib/dal.ts
import 'server-only'
import { cache } from 'react'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { decrypt } from '@/app/lib/session'

export const verifySession = cache(async () => {
  const session = await decrypt((await cookies()).get('session')?.value)
  if (!session?.userId) redirect('/login')
  return { isAuth: true, userId: session.userId, role: session.role }
})

// app/api/admin/route.ts: the handler checks for itself (return 401 here instead of redirecting if you prefer)
export async function GET() {
  const session = await verifySession()
  if (session.role !== 'admin') return new Response(null, { status: 403 })
}

// app/actions.ts: so does every Server Action; the page that renders the form does not count
'use server'
export async function deleteRecord(formData: FormData) {
  const session = await verifySession()
  if (session.role !== 'admin') return null
}
```

Also check ownership of the specific resource inside the DAL (authorization, not only authentication), and return only the fields the client needs.

## 3. Sessions: signed payload, hardened cookie

```bash
openssl rand -base64 32      # SESSION_SECRET, set in the environment; never with a NEXT_PUBLIC_ prefix
```

```ts
// app/lib/session.ts (the guide's stateless session, using jose)
import 'server-only'
import { SignJWT, jwtVerify } from 'jose'
import { cookies } from 'next/headers'
const key = new TextEncoder().encode(process.env.SESSION_SECRET)

export async function createSession(userId: string) {
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)
  const session = await new SignJWT({ userId, expiresAt })
    .setProtectedHeader({ alg: 'HS256' }).setIssuedAt().setExpirationTime('7d').sign(key)
  ;(await cookies()).set('session', session, { httpOnly: true, secure: true, expires: expiresAt, sameSite: 'lax', path: '/' })
}
```

`decrypt()` is `jwtVerify(session, key, { algorithms: ['HS256'] })`, returning the payload or `undefined`. Cookies can only be set or deleted in a Server Function or Route Handler; logout is `(await cookies()).delete('session')`. Keep the payload to the user ID and role, no PII. For sensitive operations the guide recommends database sessions verified against the store, not the cookie alone.

## 4. Keep secrets out of the client bundle

- `NEXT_PUBLIC_*` variables are inlined into the JavaScript sent to the browser at `next build`; every other variable is server-only. A secret with that prefix is published to every visitor ([secrets.md](secrets.md)). Only the DAL should read `process.env`; `.env*` files stay in `.gitignore`.
- More than one self-hosted instance: set `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` (base64, 16, 24, or 32 decoded bytes) at build so all instances share the Server Action closure key. The docs say not to rely on that encryption to hide secrets.
- Server Actions abort when `Origin` does not match `Host` (or `X-Forwarded-Host`). Behind a proxy whose host differs from the public domain, list the public origins in `experimental.serverActions.allowedOrigins` in `next.config.js`.

## 5. Libraries

**Auth.js** (https://authjs.dev/): `AUTH_SECRET` is the one mandatory variable; `npx auth secret` writes it to `.env.local`.

```ts
// auth.ts
import NextAuth from "next-auth"
export const { handlers, signIn, signOut, auth } = NextAuth({ providers: [] })
// app/api/auth/[...nextauth]/route.ts
import { handlers } from "@/auth"
export const { GET, POST } = handlers
```

Providers are configured from `AUTH_<PROVIDER>_ID`, `AUTH_<PROVIDER>_SECRET`, and for OIDC `AUTH_<PROVIDER>_ISSUER`; provider setup and the allowlist check are in [oidc-integration.md](oidc-integration.md) and [identity-providers.md](identity-providers.md). Behind a reverse proxy set `AUTH_TRUST_HOST=true` (automatic on Vercel). Server code calls `const session = await auth()`. Wrapping a Route Handler with `auth(...)` only fills in `req.auth`; nothing refuses the request for you, so the handler must check the session, then authorise, then touch data:

```ts
// app/api/notes/route.ts
import { NextResponse } from "next/server"
import { auth } from "@/auth"
// isAllowed and loadNotes are your app's own functions
export const GET = auth(async function GET(req) {
  if (!req.auth) return NextResponse.json({ message: "Not authenticated" }, { status: 401 })  // no automatic 401
  if (!isAllowed(req.auth.user)) return NextResponse.json({ message: "Forbidden" }, { status: 403 })  // your allowlist
  return NextResponse.json(await loadNotes(req.auth.user))
})
```

`export { auth as proxy }` in `proxy.ts` is the optimistic layer, and Auth.js says not to rely on it exclusively. MFA is not part of this configuration; enforce it at the identity provider ([mfa.md](mfa.md)).

**Better Auth** (https://better-auth.com/docs/introduction): `BETTER_AUTH_SECRET` (32+ characters, `openssl rand -base64 32`) and `BETTER_AUTH_URL`; the placeholder default secret throws in production.

```ts
// lib/auth.ts
import { betterAuth } from "better-auth"
import { nextCookies } from "better-auth/next-js"
import { twoFactor } from "better-auth/plugins"
export const auth = betterAuth({
  baseURL: "https://app.example.com",             // set explicitly; the docs advise against request inference
  trustedOrigins: ["https://app.example.com"],    // cross-origin requests from unlisted origins are rejected
  emailAndPassword: { enabled: true },            // default false
  plugins: [twoFactor(), nextCookies()],          // nextCookies lets Server Actions set the session cookie
})
// app/api/auth/[...all]/route.ts
import { toNextJsHandler } from "better-auth/next-js"
export const { GET, POST } = toNextJsHandler(auth)
```

Server-side check: `await auth.api.getSession({ headers: await headers() })` in Route Handlers, Server Actions, and Server Components. `getSessionCookie(request)` in `proxy.ts` only proves a cookie exists; Better Auth says to check in each page and route. `twoFactor()` adds TOTP (default), emailed or SMS OTP, and backup codes, with `twoFactorClient()` from `better-auth/client/plugins` on the client; run the schema migration the plugin page documents before enabling it.

## 6. Vercel: Deployment Protection is not user authentication

Deployment Protection controls who can open a deployment URL: Vercel Authentication admits Vercel users with access to the project; Passport, Password Protection, and Trusted IPs are Enterprise or paid add-on options. Standard Protection covers previews and generated URLs but not production domains; selecting the All Deployments scope for Vercel Authentication extends it to production, and Vercel's changelog of 9 September 2026 makes that free on every plan including Hobby, where protecting production previously required the USD 150 per month Advanced Deployment Protection add-on (at the time of writing). Availability is not activation: the production domain stays public until All Deployments is configured. It gates your team's previews; your users are not Vercel users, so production still needs section 2 ([paas.md](paas.md)).

## Verify

```bash
ss -tlnp | grep 3000                                    # self-hosted: 127.0.0.1 only
curl -si https://app.example.com/api/admin | head -1    # 401 (or 302 to /login) with no cookie
curl -si https://app.example.com/dashboard | head -1    # 302 to /login, not the page
grep -rl "${SESSION_SECRET:0:8}" .next/static           # no output: the browser bundle has no secret
# Server Action: clear cookies in the browser, submit the form that calls it; it must refuse, not mutate.
```

## Common mistakes

- Checking the session in `app/layout.tsx` or `proxy.ts` only; a Server Action or `route.ts` behind it is still open.
- A Proxy `matcher` that excludes `/api`, with nothing in the Route Handlers themselves.
- Naming a secret `NEXT_PUBLIC_*`, or treating Vercel Authentication as production login.

## Sources (checked September 2026)

- Next.js authentication guide: https://nextjs.org/docs/app/guides/authentication ; data security guide: https://nextjs.org/docs/app/guides/data-security
- Next.js `proxy.js`: https://nextjs.org/docs/app/api-reference/file-conventions/proxy ; `route.js`: https://nextjs.org/docs/app/api-reference/file-conventions/route ; `cookies`: https://nextjs.org/docs/app/api-reference/functions/cookies
- Next.js environment variables: https://nextjs.org/docs/app/guides/environment-variables ; CLI (`next start` defaults): https://nextjs.org/docs/app/api-reference/cli/next ; self-hosting: https://nextjs.org/docs/app/guides/self-hosting
- Auth.js protecting resources (Route Handler `req.auth` check): https://authjs.dev/getting-started/session-management/protecting
- Auth.js installation: https://authjs.dev/getting-started/installation ; deployment (`AUTH_SECRET`, `AUTH_TRUST_HOST`, provider variables): https://authjs.dev/getting-started/deployment ; protecting resources: https://authjs.dev/getting-started/session-management/protecting
- Better Auth introduction: https://better-auth.com/docs/introduction ; installation: https://better-auth.com/docs/installation ; options: https://better-auth.com/docs/reference/options ; Next.js integration: https://better-auth.com/docs/integrations/next ; two-factor plugin: https://better-auth.com/docs/plugins/2fa
- Vercel Deployment Protection: https://vercel.com/docs/deployment-protection
- Vercel changelog, protect production deployments for free on every plan (9 September 2026): https://vercel.com/changelog/protect-production-deployments-for-free-on-every-plan
