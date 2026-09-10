# Object storage: S3, Cloudflare R2, Google Cloud Storage, Azure Blob, Supabase Storage

AI projects put user uploads, datasets, and model files in buckets, and one public bucket or one over-broad policy leaks every object in it, silently, to anyone who guesses or scrapes a URL. Every provider below now defaults new buckets to private; the work is keeping them that way, granting access per principal, and sharing objects through short-lived signed URLs rather than by making anything public. Self-hosted MinIO is covered in [minio.md](minio.md).

## 1. Amazon S3

- New buckets and objects allow no public access, and Object Ownership defaults to "Bucket owner enforced", which disables ACLs; keep it that way and grant access only through bucket policies and IAM.
- Turn on all four Block Public Access settings (`BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`, `RestrictPublicBuckets`) at the account level as well as per bucket; the account setting wins even if someone loosens a bucket policy later.
- A bucket policy is "public" if it grants to `"Principal": "*"` without a fixed condition (specific principal, `aws:SourceVpc`, `aws:SourceArn`, a narrow `aws:SourceIp`, and similar). Give each application its own IAM role with only the actions and prefixes it uses ([machine-auth.md](machine-auth.md)).
- Share objects with presigned URLs and a short expiry: `aws s3 presign s3://example-bucket/model.safetensors --expires-in 600` (default 3600 seconds, maximum 604800).

```bash
aws s3api get-public-access-block --bucket example-bucket     # all four true
aws s3api get-bucket-policy-status --bucket example-bucket    # "IsPublic": false
```

IAM Access Analyzer for S3 lists every bucket in the account whose ACL, bucket policy, or access point policy grants public or cross-account access.

## 2. Cloudflare R2

- Buckets are never publicly accessible by default; public access is an explicit step, either a custom domain you control or a Cloudflare-managed `r2.dev` subdomain, which is rate-limited and for development only. Under the bucket's settings, keep the Public Development URL disabled and attach no custom domain unless the bucket is meant to be public.
- Create R2 API tokens with the least permission: `Object Read only` or `Object Read & Write` scoped to specific buckets for applications; the `Admin` levels can create and delete buckets and belong to operators only. The secret access key is shown once, so store it in a secret manager ([secrets.md](secrets.md)).
- R2 supports S3 presigned URLs, generated with your R2 token and SigV4, valid from 1 second to 7 days (604800 seconds); keep uploads and downloads on these rather than on a public bucket.

## 3. Google Cloud Storage

- Enable uniform bucket-level access so ACLs are disabled and only IAM grants access; after 90 consecutive days it cannot be turned off, which is the point.
- Enforce public access prevention on the bucket, or at project, folder, or organization level with the `storage.publicAccessPrevention` constraint; attempts to grant `allUsers` or `allAuthenticatedUsers` then fail with `412 Precondition Failed`, and anonymous requests to data get `401` or `403`. A bucket shows `enforced` or `inherited`.
- Signed URLs (V4) expire after at most 604800 seconds (7 days); `gcloud storage sign-url --duration=1h` allows up to 12 hours with the caller's credentials or 7 days with a service-account private key. Public access prevention does not apply to signed URLs, so keep their durations short.

```bash
gcloud storage buckets update gs://example-bucket --uniform-bucket-level-access --public-access-prevention   # boolean flags; describe then reads back enforced
gcloud storage buckets describe gs://example-bucket          # uniform_bucket_level_access: true, public access prevention enforced
```

## 4. Azure Blob Storage

- Anonymous access is prohibited by default for Resource Manager storage accounts. Keep the account property `allowBlobPublicAccess` at `false` ("Allow Blob anonymous access: Disabled" under Settings > Configuration); it overrides any container set to Container or Blob access, so a per-container mistake cannot open data. Check it with `az storage account show --name examplestorage --resource-group example-rg --query allowBlobPublicAccess --output tsv`.
- Prefer a user delegation SAS (secured by Microsoft Entra credentials) over service or account SAS signed with the account key, use HTTPS only, grant the least permission (read-only, a single blob), and use near-term expiry; a SAS expiration policy on the account warns when a longer one is generated. Consider disallowing Shared Key access so nobody can mint account-key SAS at all.
- Azure Policy with the `Microsoft.Storage/storageAccounts/allowBlobPublicAccess` field audits or denies accounts that allow anonymous access.

## 5. Supabase Storage

- Buckets are private by default; a public bucket means anyone with the URL can read the file, so use one only for assets that are meant to be public.
- Access to a private bucket is governed by row level security policies on `storage.objects`, and without policies Storage allows no uploads at all. Write policies per operation and scope them to the owner, for example:

```sql
create policy "Individual user Access"
on storage.objects for select
to authenticated
using ( (select auth.jwt()->>'sub') = owner_id );
```

- Share private objects with `supabase.storage.from('bucket').createSignedUrl('path.pdf', 3600)` (seconds) from server code; `getPublicUrl` works only for public buckets. Signed URLs stay valid until they expire even if you rotate Auth keys, so keep them short. The service-role key bypasses RLS and never reaches a browser ([firebase-supabase.md](firebase-supabase.md)).

## Verify

```bash
curl -sI https://example-bucket.s3.amazonaws.com/model.safetensors        # 403, never 200
URL="$(aws s3 presign s3://example-bucket/model.safetensors --expires-in 60)"   # signs a GET, so test with GET
curl -sS -o /dev/null -w '%{http_code}\n' "$URL"              # 200 now
sleep 61; curl -sS -o /dev/null -w '%{http_code}\n' "$URL"    # 403 once the minute has passed
```

- An anonymous request to any object URL is denied (S3 returns `403`; GCS `401` or `403`; Azure `401`, or `409` when the account disallows anonymous access; Supabase private buckets return an error, not the file).
- The provider's public-access view is empty: IAM Access Analyzer for S3 shows no public buckets, `gcloud storage buckets describe` shows public access prevention `enforced`, the Azure Resource Graph query for `allowBlobPublicAccess` shows `false` on every account, and R2 buckets show no Public Development URL or custom domain.
- Application credentials are scoped to one bucket or prefix, and no root, account-key, or service-role credential appears in client code or the repository.

## Common mistakes

- Making a bucket public to fix a broken download link, when the fix was a signed URL.
- A presigned URL or SAS with a multi-day expiry pasted into a chat or ticket; it is a credential until it expires.

## Sources (checked September 2026)

- S3 Block Public Access (four settings, defaults, meaning of "public", IAM Access Analyzer): https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html and https://docs.aws.amazon.com/AmazonS3/latest/userguide/configuring-block-public-access-bucket.html
- S3 Object Ownership (Bucket owner enforced default, ACLs disabled): https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html
- AWS CLI `s3 presign` (`--expires-in` default and maximum): https://docs.aws.amazon.com/cli/latest/reference/s3/presign.html
- Cloudflare R2 public buckets, API tokens, presigned URLs: https://developers.cloudflare.com/r2/buckets/public-buckets/ , https://developers.cloudflare.com/r2/api/tokens/ , https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- Google Cloud Storage uniform bucket-level access, public access prevention, signed URLs, `gcloud storage sign-url`: https://docs.cloud.google.com/storage/docs/uniform-bucket-level-access , https://docs.cloud.google.com/storage/docs/using-uniform-bucket-level-access , https://docs.cloud.google.com/storage/docs/public-access-prevention , https://docs.cloud.google.com/storage/docs/access-control/signed-urls , https://docs.cloud.google.com/sdk/gcloud/reference/storage/sign-url
- Azure Blob anonymous access remediation and SAS overview: https://learn.microsoft.com/en-us/azure/storage/blobs/anonymous-read-access-prevent and https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview
- Supabase Storage buckets, access control, and downloads: https://supabase.com/docs/guides/storage/buckets/fundamentals , https://supabase.com/docs/guides/storage/security/access-control , https://supabase.com/docs/guides/storage/serving/downloads
