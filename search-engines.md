# Search engines for RAG: Meilisearch and Typesense

Both back RAG pipelines and site search, both ship a keyless dev mode meant for a laptop, and both hand out one bootstrap key that is full admin over every index. Ship that dev-mode instance or leak that bootstrap key and the whole corpus, every document your RAG pipeline embedded, is readable and writable by whoever has it.

## Meilisearch

Meilisearch runs in two modes. In development mode it answers without a key at all. Production mode requires setting `MEILI_MASTER_KEY` (at least 16 bytes) and launching with `--env production`; the master key is the credential everything else derives from.

From it, Meilisearch generates two default API keys, an admin key (full control, including index and settings management) and a search key (search only), and it also supports scoped API keys you create yourself and tenant tokens: "short-lived, client-side tokens derived from API keys" for per-end-user search restrictions without shipping a standing key to each user. Use the default (or a scoped) search key in front-end code; never the admin key or the master key.

Meilisearch does not terminate HTTPS itself in the typical deployment, so put a reverse proxy or your platform's TLS in front ([nginx.md](nginx.md), [caddy.md](caddy.md), [cloudflare.md](cloudflare.md)) and restrict network access with firewall rules as an additional layer ([cloud-firewalls.md](cloud-firewalls.md)).

## Typesense

Typesense starts from a bootstrap key set with the `--api-key` server parameter; that key has "admin permissions on all endpoints and data." Use it only to create a permanent admin key through the `/keys` API, then stop using the bootstrap key day to day so it can be rotated without a restart-time outage.

For anything that runs in a browser, generate a scoped, search-only key through the same `/keys` endpoint:

```json
{
  "actions": ["documents:search"],
  "collections": ["*"]
}
```

Narrow `collections` to a name or regex to limit a key to specific collections, embed a `filter_by` clause in a scoped key to restrict it to specific documents (Typesense: "Users will not be able to override the filter embedded inside the scoped API Key"), and use `include_fields`/`exclude_fields` to hide sensitive fields such as billing data from a given key. Typesense's own guidance is direct: "Never expose your Admin API Key or Bootstrap API Key to your frontend application as anyone with access to it will be able to write data into your collection." Set `expires_at` on browser-facing keys so a leaked one has a shelf life.

Typesense's cloud offering terminates TLS for you; a self-managed cluster needs the same reverse-proxy or platform TLS pattern as Meilisearch above.

## The pattern, either engine

The credential that goes into a browser must be search-only and, ideally, scoped to what that specific user or page needs (a tenant token in Meilisearch, a scoped key with `filter_by` in Typesense). The admin or bootstrap key stays server-side, in the platform's secret store, never in client bundles or repository history ([secrets.md](secrets.md)).

## Verify

```bash
curl -s http://search.example.com:7700/indexes                 # Meilisearch, no key: fails in production mode
curl -s http://search.example.com:7700/indexes -H "Authorization: Bearer REPLACE_WITH_SEARCH_KEY"  # search works
curl -s http://search.example.com:7700/indexes -X POST -H "Authorization: Bearer REPLACE_WITH_SEARCH_KEY"  # write: denied

curl -s http://search.example.com:8108/collections               # Typesense, no key: fails
curl -s http://search.example.com:8108/collections -H "X-TYPESENSE-API-KEY: REPLACE_WITH_SEARCH_ONLY_KEY"  # search works
curl -s http://search.example.com:8108/collections -X POST -H "X-TYPESENSE-API-KEY: REPLACE_WITH_SEARCH_ONLY_KEY"  # write: denied
```

Grep the client bundle and repository history for the admin/master/bootstrap key; it should never appear outside the server-side secret store.

## Common mistakes

- Shipping a Meilisearch instance without `MEILI_MASTER_KEY` and `--env production` because dev mode "worked fine" in testing.
- Putting the Typesense bootstrap key or Meilisearch admin key straight into front-end JavaScript instead of minting a scoped search key.
- A scoped key with no `filter_by` or `collections` restriction, which searches everything the admin key can see.

## Sources (checked September 2026)

- Meilisearch security overview (MEILI_MASTER_KEY, --env production, default admin/search keys, tenant tokens): https://www.meilisearch.com/docs/resources/self_hosting/security/overview
- Typesense data access control (bootstrap api-key, /keys, actions, collections, filter_by, include_fields/exclude_fields, expires_at): https://typesense.org/docs/guide/data-access-control.html
