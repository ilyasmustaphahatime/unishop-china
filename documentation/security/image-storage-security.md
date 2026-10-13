# Product image storage security - Phase 10

Adversarial review 2026-10-13. See [API](../api/product-images-api.md),
[original implementation gate](../phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md) and
[independent findings/final rerun](../phases/PHASE_10_FINAL_ADVERSARIAL_AUDIT.md).
Product photos are not seller identity evidence: separate roots, namespaces,
service policies and endpoints. No public mount or shared evidence credentials.

| Threat | Control / evidence |
|---|---|
| BOLA/IDOR, foreign ref or forged role | Current ACTIVE/eligible DB authority; parent-qualified refs; real cross-seller and stale-session/identity tests |
| Hidden product image | Shared Phase 9 request-time public predicate; state/seller/onboarding/catalog tests; no-store on bytes |
| MIME spoof, SVG/HTML/executable, corrupt/animated raster, appended container | Full Pillow decode, strict one-container boundary, static JPEG/PNG/WebP whitelist, fresh-pixel re-encoding |
| EXIF/GPS/orientation leak | EXIF transpose then new pixel image; metadata-free encoder; real synthetic GPS/orientation assertions |
| Byte/pixel/decompression exhaustion | Actual transport/file bounds; cryptographic auth and service-owned owner/eligibility/quota preflight before reserving either intake slot; preflight releases SQL locks before slow input; pixel/bomb guards and two decoder slots |
| Truncated multipart or parser I/O failure | Require terminal callback; close framework-owned spools on rejection/cancellation; safe 503 for unexpected I/O; function-scoped cleanup before response headers; six parser compatibility exit cases |
| Path traversal, links/junctions, collisions/overwrite | Exact random key grammar, canonical root containment and link rejection; exclusive temporary write/fsync and exclusive hard-link publication |
| More than 8, stale quota/authority, ordering races | Parent lock plus final metadata revalidation, fresh locked entities, unique positions, transaction-local resequencing; InnoDB races repeated 3 times |
| Storage success/DB failure, ambiguous commit | Rollback plus explicit compensation; storage/decoder never automatically replayed; fault-injection and cross-seller reference-collision tests |
| Physical delete failure | Metadata removal and resequencing commit first; invisible orphan with safe ref-only alert; report-only audit |
| Private browser cache/blob survives switch | Session-version fences, identity/version query keys, private eviction including cold mutation keys, object URL cleanup; unit and real Chrome checks |

No antivirus claim: accepted pixels are re-encoded rather than arbitrary original
bytes being served. No credentials/raw request bodies/image data/private keys or
original names are logged. Audit inventory reports missing refs or a truncated
one-way orphan fingerprint, never actual paths/keys. Run reports with writes
quiescent; an in-flight upload can temporarily look orphaned. There is deliberately
no destructive cleanup mode or scheduled job. Operator remediation must be a
separate reviewed maintenance operation.

All image responses, including auth/validation/not-found errors, carry no-store,
no-cache, nosniff and no-referrer. A request-spool cleanup failure can occur AFTER
valid metadata has committed; return safe 503 before headers, do not undo/replay the
committed image, and refetch owner metadata. Upload is not an idempotent API.
The parser uses the installed framework's private owned-file inventory for narrow
error/cancellation cleanup; compatibility tests must run on framework upgrades.

File and MySQL transactions cannot be atomic together. A process crash between
publication and metadata commit, or between metadata deletion and physical deletion,
can leave an inaccessible orphan. Failed compensation also leaves an orphan; it
cannot acquire public/owner API authority without committed metadata. An ambiguous
DB commit plus file compensation can leave a missing row/object pair, detected by
the report. These are explicit recovery/backup obligations, not hidden guarantees.

DB checks enforce metadata bounds and safe key/ref grammar, not an aggregate
eight-row count or committed contiguity. Positions 8..15 exist only for unique-safe
transaction-local moves; application locks enforce final 0..7. Restrict direct
DB writes. Re-encoding has bounded input/pixels but can allocate tens/hundreds of
MiB; production needs measured worker memory/CPU/timeouts and external ingress
controls. Local ownership permissions must prevent another process swapping paths
between validation and open; cross-process hostile filesystem races are not a
claimed sandbox.

Visibility is checked on each request, not retroactive erasure of previously
downloaded pixels or a browser already rendering an earlier authorized response.
Application reads never return raw object-store URLs. Production CDN/caching must
preserve dynamic visibility; do not publish a permanently accessible public bucket.

OWASP API Security coverage: API1 object authorization; API2 existing bearer/session
auth; API3 strict field allowlists; API4 intake/decode budgets; API5 no admin/role
bypass; API6 bounded business mutations; API8 safe storage/TLS/errors; API9 scoped
six-operation inventory; API7 has no remote-URL fetch input, and API10's external
provider trust requires a separate production-adapter gate. ASVS topics
include access control, validation/file handling, session isolation, safe errors,
data protection and configuration. This is a scoped control/test mapping, not an
independent ASVS certification or claim that every Top 10 category is applicable.

Release blockers: production object adapter/evidence isolation/retention/access,
distributed quotas and abuse controls, TLS/proxy 10 MiB + envelope upload support
(scoped NGINX image cap corrected; runtime remains unverified), deployment secrets/providers, recovery/backup and
target MySQL 8 validation; inherited Tailwind 3 build advisories. Docker/NGINX
runtime is unavailable locally. No Tailwind migration or Phase 11 implementation.
