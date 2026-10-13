# Product Images API - Phase 10

Paths are relative to `/api/v1`. `{slug}` is `item-` plus 24 lowercase hex digits;
`{image_ref}` is immutable `img-` plus 32 lowercase hex digits. No internal UUID,
original filename, storage key or credential belongs in a URL.

| Method | Path | Authority / result |
|---|---|---|
| POST | `/seller/products/{slug}/images` | Eligible owner; one multipart `file`, sanitized metadata, 201 |
| GET | `/seller/products/{slug}/images` | ACTIVE owner; ordered metadata, including archived |
| GET | `/seller/products/{slug}/images/{image_ref}` | ACTIVE owner; sanitized private bytes |
| PATCH | `/seller/products/{slug}/images/order` | Eligible owner; complete unique current refs |
| DELETE | `/seller/products/{slug}/images/{image_ref}` | ACTIVE owner, including archived/ineligible seller; 204 |
| GET | `/products/{slug}/images/{image_ref}` | Anonymous; currently public-visible parent only, otherwise uniform 404 |

Five owner operations use the existing Bearer header. Previews fetch a Blob via
the central client and a temporary object URL, never a token query parameter.
Eligibility: ACTIVE account, verified email/phone, current approved seller attempt
and completed onboarding. Upload/reorder allow DRAFT/PUBLISHED/PAUSED only.
ACTIVE owners retain list/read/delete after approval/onboarding loss or archive;
inactive accounts cannot use owner operations. Refs are always parent-qualified.
Public bytes use exactly the Phase 9 listing visibility predicate.

Zero through eight images; zero-image publication is valid. Raw/stored limit
10 MiB each, dimensions 1-6000 per axis, at most 30,000,000 pixels. Only static
JPEG/PNG/WebP pass full decoding; MIME/extension is not authority. Animation,
unsupported/corrupt containers, trailing data/containers, oversize and decompression
hazards fail. Orientation is applied before fresh-pixel re-encoding. EXIF/GPS, ICC,
comments and original names are not retained. PNG/WebP alpha is preserved.

Multipart accepts one part named `file`, no fields/extra files. Actual-body bound:
10 MiB + 64 KiB envelope; input deadline 15 seconds; spool threshold 1 MiB.
Never manually set multipart Content-Type in the browser. Ingress and decoder
concurrency are two per process. Limits run before parsing/decoding, including
malformed input: upload peer 36/10 minutes, upload user 10/10 minutes, other writes
90/peer/minute, reads 180/peer/minute; shared listing user read 60/minute, write
30/minute and authenticated peer 120/minute also apply. Not distributed/DDoS proof.

Admission order: peer/header checks, cryptographic authentication and user budgets,
service-owned current owner/eligibility/quota preflight, then intake slots and
bounded spooling, strict multipart parsing, bounded file read, decoding/storage,
and final metadata revalidation. The read-only preflight releases SQL locks before
awaiting network bytes. Invalid tokens/ineligible/foreign/full listings cannot
reserve slow-body upload slots. Successful and error image responses all retain
nosniff/no-store/no-cache/no-referrer headers.

The parser requires the terminal multipart callback, not merely one completed file
before an unfinished next part. Truncated envelopes fail before storage/metadata.
Owned parser spools close on rejection/cancellation; parser I/O failures return
safe 503, not raw diagnostics. Request-spool cleanup runs before the response starts.
An upload may already be committed if that final cleanup fails: inspect the owner
image collection after an ambiguous failure; uploads are not idempotent and are
not automatically replayed. Framework non-file part limits are not file-size
limits: actual aggregate intake and bounded file reading remain authoritative.

Owner fields: `ref`, `position`, `url`, `mime_type`, `width`, `height`, `file_size`,
`created_at`. Public listing `images` fields: `ref`, `position`, `url`, maximum 8,
empty `[]` valid. URLs are canonical API paths, not storage URLs. No UUIDs, PII,
storage keys, original names, seller evidence, private dimensions or tokens public.

Reorder: `{"images":["img-<32 lowercase hex digits>","img-<32 lowercase hex digits>"]}`
(notation, not literal valid refs). Exactly all current refs once. Omission/foreign/
deleted ref: 409; duplicate/invalid ref/extra field: 422. Empty only for an empty
collection. Returns full ordered owner collection. Position 0 is cover, committed
positions contiguous 0..N-1. Deleting cover promotes next. No replace/undelete;
deleted ref remains 404. DELETE body may be empty or `{}` only.

Bytes: authoritative re-encoded MIME, `X-Content-Type-Options: nosniff`,
`Cache-Control: no-store`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`.
Missing file: safe 404 without metadata mutation; size mismatch/unavailable
storage: safe 503. Hidden/unknown parent, foreign/deleted public ref all return
`{"detail":"Image not found."}`. Other statuses: 400 malformed multipart,
401 invalid/inactive authentication, 403 eligibility, 409 quota/archive/order,
413 actual input bound, 415 HTTP media type, 422 unsafe image/DTO, 429 budget,
503 safe operation failure. No request values/SQL/paths/driver echo.

Storage saves once; final pure-DB transaction rechecks current authority/parent/quota
and may retry bounded InnoDB deadlocks. Failed metadata commit compensates storage.
Delete commits metadata/resequence before physical deletion. Cleanup failure leaves
an invisible orphan, never restored visibility. Report-only
`scripts/audit_product_media.py` exposes only missing refs or orphan fingerprints,
does not delete, and should run while writes are quiescent. Exit 0 clean, 1 issues/unavailable.

Ignored local root is not static-served; production local storage fails closed
until a separately verified adapter exists. NGINX now has a scoped product-image
location capped at exactly 10 MiB + 64 KiB (10,551,296 bytes), retaining the 6m
default for evidence/other endpoints. The configuration contract is statically
tested, but NGINX/container runtime remains unverified. Verify real proxy
buffering/timeouts/TLS and 413 behavior before deployment. Direct Uvicorn tests
are not proxy certification. No Phase 11 feed/search added.
