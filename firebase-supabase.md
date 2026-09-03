# Firebase and Supabase: the rules are the security

These platforms handle TLS for you; the exposure works differently. Client SDKs talk to the backend using keys that ship in your frontend code and are **public by design** (the Firebase API key, the Supabase `anon` key). The only server-side gate between the internet and your data is the rules layer: Firebase security rules, or Postgres row-level security (RLS) on Supabase. AI-generated apps repeatedly ship with that layer open because "it worked in testing".

## Firebase

- Every Firestore, Realtime Database, and Storage instance needs explicit security rules. Never deploy the all-open rule (`allow read, write: if true;` or `".read": true, ".write": true`); it exposes the entire datastore to anyone with your public config.
- Require authentication and scope by user:

```
// Firestore example
match /users/{userId}/{document=**} {
  allow read, write: if request.auth != null && request.auth.uid == userId;
}
```

- New projects start in locked mode; keep production locked-by-default and open specific paths deliberately. Test with the Rules Playground and emulator before deploying.
- Server-side credentials (service accounts for the Admin SDK) bypass rules entirely; they stay on servers only, handled per [secrets.md](secrets.md).

## Supabase

- Enable RLS on **every** table exposed through the API, then write policies; a table without RLS is readable and writable with the public `anon` key:

```sql
alter table profiles enable row level security;

create policy "own rows"
on profiles for select
using ( auth.uid() = user_id );
```

Write separate policies per operation (`select`, `insert`, `update`, `delete`); no policy means no access once RLS is on, which is the correct starting point.
- The `service_role` key bypasses RLS; it is a server-only secret that must never reach the client bundle or the repository.
- Supabase Auth supports MFA on user accounts; enable it for anything sensitive ([mfa.md](mfa.md) for the general rules).

## Verify

- With only the public key (no signed-in user), API reads and writes against protected tables/paths fail.
- Signed in as user A, reading user B's rows fails.
- Search the client bundle for `service_role` and private keys; the result must be empty.

## Sources (checked September 2026)

- Firebase security rules: https://firebase.google.com/docs/rules
- Supabase row level security: https://supabase.com/docs/guides/database/postgres/row-level-security
