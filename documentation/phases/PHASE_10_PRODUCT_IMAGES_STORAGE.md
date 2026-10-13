# Phase 10 Product Images and Storage - Final Local Gate

Independent adversarial review continued through 2026-10-13. Its findings, fixes,
fresh final counts and full original/review manifests are recorded in
[PHASE_10_FINAL_ADVERSARIAL_AUDIT.md](PHASE_10_FINAL_ADVERSARIAL_AUDIT.md).
The dated implementation results below are preserved as historical baseline,
not a substitute for that subsequent audit. Production readiness remains NO.

Resume gate (2026-10-13): existing implementation/fixes preserved; the independent
report now records 1,388 backend, 197 image, 733 security, 89 x 3 concurrency,
304 frontend, 155 live HTTP and 27 real Chrome UI checks. The resume added a
completed-file disconnect regression and a held authorized response delivered
after logout/account switching without stale-preview restoration. Current data,
migration and all 13 unrelated artifacts remain preserved; no staging/commit/push.

Verified 2026-10-12. This is the scoped Phase 10 implementation/gate, not a
production approval. Historical Phase 9 reports are retained unchanged.

## 1. EXECUTIVE RESULT

Phase 10 implementation complete: **YES**.
Local Phase 10 gate passed: **YES**.
Ready for Phase 11 development: **YES**.
Production ready: **NO**. Phase 11 was not implemented.

Critical: 0 confirmed application findings.
High: 0 confirmed Phase 10 application findings; inherited braces High build advisory unresolved.
Medium: 2 implementation findings fixed before final gate (collision/deadlock
transaction handling and owned temporary/object collision cleanup); inherited
selector-parser Moderate build advisory unresolved.
Low: 1 fixed (cold mutation-seeded private product cache survived metadata-only eviction).
Informational: production storage/distributed controls/resource/deployment validation,
historical full-history rollback limitation and one upstream TestClient warning.

A forced cross-seller public-ref collision initially produced InnoDB 1213 and
secondary savepoint 1305. Upload now saves/decodes once, then retries only pure-DB
metadata work with fresh authority/quota locks. Failure compensates the new object.
Temporary/final nonce collisions no longer delete a pre-existing object not owned
by that save. A negative frontend test first reproduced private cold cache retention;
logout eviction now covers those keys without deleting public queries.
All final failures: 0. No security rule, TLS check, assertion or rate budget disabled.

Continuation verification (2026-10-12): resumed the existing dirty tree after the
reported stream interruptions; did not recreate or replace implementation files.

| Component | State on continuation | Final state |
|---|---|---|
| Metadata model, constraints, registration and additive migration | Implemented | Preserved; schema/no-drift and disposable cycles passed |
| Bounded upload, decoding, metadata stripping and immutable local storage | Implemented | Preserved; attack/fault/storage gates passed |
| Owner/public access and seller-evidence separation | Implemented | Preserved; auth/privacy and HTTP regression passed |
| Quota, order, cover, deletion and DB/storage compensation | Implemented | Preserved; fault tests and 3 fresh concurrency runs passed |
| Frontend manager, Blob lifecycle, gallery and session isolation | Implemented | Preserved; full frontend and real Chrome passed |
| Security/concurrency/live/migration audit tooling | Implemented; fresh continuation execution pending | All required local executions completed |
| Required singular API-document path | Missing; complete plural-named document existed | Added linking entry point without moving the existing document |
| Production cloud storage/deployment/distributed controls | Not implemented, explicitly outside local Phase 10 | Remain production blockers; no scope expansion |

Partially implemented functional Phase 10 components: NONE. Missing functional
Phase 10 components: NONE. No new application-code or migration edits were needed
on continuation. Full backend/frontend, 153 image, 689 security, 78 x 3 races,
145 HTTP, 21 Chrome, migration/static/audit gates were freshly rerun, not inferred
from earlier results. Only the API documentation entry point, this report and
current-status continuation note were added/updated during this continuation.

## 2. GIT BASELINE

Branch: `feature/authentication`.
Starting HEAD: `204d85f8fc6ceed59166939905241ab4f74d3e32`.
Remote: locally recorded `origin/feature/authentication` at the same SHA; no fetch/push.
Initial working tree: clean, 0 staged. Full previous history/revisions preserved.

Continuation starting tree: 37 modified tracked files, 40 untracked files (27
existing Phase 10 files plus 13 unrelated artifacts), 0 staged/deleted. All 77
paths were inventoried and SHA-256 snapshotted before continuation checks. The
complete tracked diff, untracked source/tests/tooling/docs and unrelated artifact
metadata were inspected. The additive migration, all application/frontend/test
code and dependency files remain byte-for-byte unchanged on continuation.

During the task, 13 unrelated human PDF/build/render artifacts appeared under
`output/` and `tmp/`. They were preserved; before/after SHA-256 matches for all
13. They are not Phase 10 runtime photos, code changes or staging candidates.
No other unexpected edits were found. No staging, commit or push.

## 3. ARCHITECTURE

Six thin routes reuse bearer auth, shared safe errors, strict input DTOs and budgets.
ProductImageService owns authority, parent/quota locks, transactions, order and
compensation. ProductImageRepository owns parent-qualified metadata/current reads,
eight bounded named-ref-unique collision attempts and transaction-local resequencing.
ProductImageStorage is a narrow save/read/delete/keys/exists interface; the local
adapter is separate from private seller-evidence storage. No generic CRUD/reconciler,
new queue, CDN, distributed service or duplicate product eligibility implementation.

Upload preflight locks current authority/parent/count, bounds/decodes/re-encodes and
saves once; that read-only DB phase closes before the final pure-DB metadata
transaction reacquires/rechecks every rule. Only DB work retries deadlocks.
Reorder/delete metadata are parent-serialized pure DB transactions. Reads use
authorized metadata, never a user-supplied object path. Routes own HTTP; services
do not construct HTTP errors or return internal keys.

## 4. DATABASE

Migration: `a10b2c3d4e5f_product_images.py`.
Down revision: `f9a1b2c3d4e5`.
Sole current/head: `a10b2c3d4e5f`. Drift: **NONE**.
Table: `product_images`; 11 columns: id, product_listing_id, public_ref,
storage_key, mime_type, width, height, file_size, position, created_at, updated_at.
Bytes stored in DB: **NO**. No original filename/user PII column.

PK UUID; RESTRICT listing FK; unique public_ref, storage_key and listing/position.
Actual MySQL indexes are these three uniques; the compound unique also supports
parent-ordered reads/FK. Seven checks enforce ref/key grammar, MIME, dimensions,
pixels, size and position. Parent FK restrict/delete and invalid metadata negatives
run against real MySQL (1451/1452/3819), not SQLite-only approximations.

Position CHECK permits 0..15 to reserve 8..15 for temporary unique-safe moves.
The locked service, not an aggregate SQL CHECK, enforces final max eight rows and
contiguous 0..7. ORM content identity/metadata is immutable; only ordering changes.

## 5. STORAGE MODEL

Development provider: `local`; default ignored
`backend/private_storage/product-media/`, object namespace `product-media/<64 random hex>`.
Public ref is independently random `img-<32 random hex>`, never derived from keys.
Production provider status: **NOT CONFIGURED/VERIFIED**; local production adapter
fails closed. No static mount/public bucket or raw storage URL is exposed.

Exact key grammar, canonical containment and symlink/junction component guards.
Save uses an exclusive owned temporary file, flush/fsync, then exclusive hard-link
publication, never overwrite. Cleanup only removes files actually created by that
attempt. Reads/deletes/audit do not create storage directories; inventory sees
leftover/unrecognized objects. Tests verify collision/path guards and failure cleanup.
The working default root is absent after all gates; all synthetic media is temporary.
Hostile filesystem mutation by another local process is not a claimed sandbox.

## 6. IMAGE SECURITY

Allowed: JPEG, PNG, static WebP. Rejected: SVG/HTML/executable/GIF/unsupported formats,
fake signatures, corruption, animation and appended container/trailing data.
Raw and stored limits: 10 MiB. Dimensions: 1..6000 per axis. Pixels: <=30,000,000.
Actual bytes bound both transport and file; Content-Length is not authority.

Pillow full verify/load, static frame check, strict container boundaries, unchanged
decompression guards and two process-local decoder slots. Input has a 15-second
deadline, 1 MiB spool threshold and 10 MiB + 64 KiB envelope. Metadata-free fresh
RGB/RGBA encoding applies EXIF orientation then strips EXIF/GPS/ICC/comments.
PNG/WebP alpha retained. No weakening of MAX_IMAGE_PIXELS or antivirus claim.
Tiny synthetic fixtures cover dimensions at boundaries without allocating giant photos.
Pillow encoding options verified against [official format docs](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html).

## 7. AUTHORIZATION

Upload/reorder: ACTIVE owning user, verified email/phone, current approved seller,
completed onboarding, non-ARCHIVED parent. DRAFT/PUBLISHED/PAUSED allowed.
Owner list/read: ACTIVE actual owner; retained after approval/onboarding loss/archive.
Delete: ACTIVE owner including archived/ineligible seller, enabling privacy cleanup.
Inactive users denied; JWT BUYER/SELLER/ADMIN roles do not substitute product ownership.
Cross-seller list/read/delete return inaccessible-resource responses; upload/reorder
cannot modify another seller's product, including a second fully qualified seller.
Image refs must belong to that same parent. Current locked reads refresh stale ORM state.

## 8. PRODUCT VISIBILITY

DRAFT: public image 404. PUBLISHED: public image 200 only while the same Phase 9
visibility predicate is satisfied. PAUSED/ARCHIVED: 404. Inactive seller, missing
approval/email/phone/onboarding, inactive listing city/category/parent: 404.
Unknown/hidden/foreign/deleted public refs share safe image-not-found 404.

Parent detail and byte endpoint reuse ProductService.public_view rather than
parallel visibility logic. No static bypass. Authorization is request-time, not
retroactive erasure of pixels already downloaded or an in-flight authorized response.
Public bytes are no-store; production caching/CDN must preserve this boundary.

## 9. ORDER / COVER

Committed positions contiguous 0..N-1, N<=8. Position 0 is cover.
Reorder requires the exact unique complete current parent-qualified ref set:
malformed/duplicate refs 422; missing/foreign/deleted set 409.
Unique-safe two-stage reorder uses reserved positions 8..15 then final 0..7 inside
one transaction; intermediate states are not API responses. Delete flushes metadata,
resequences remaining rows and commits; cover deletion promotes the next image.
No replacement/reuse of an old opaque ref. Zero-image publishing remains allowed.

## 10. DB/STORAGE CONSISTENCY

Storage save failure: no metadata commit, adapter cleans its owned temporary file.
Storage success + metadata failure: transaction rollback + file compensation.
Final metadata phase rechecks archive/approval/quota after the storage phase.
DB deadlock retry cannot decode/save twice. Failed commit recovery/fault tests pass.
Only named public-ref uniqueness errors retry; unrelated FK/storage-key failures do not.

Delete: metadata and order commit BEFORE physical delete. Physical cleanup failure
logs only a safe ref event, leaves invisible orphan, does not restore visibility.
Missing object read: safe 404, metadata retained. Size mismatch: safe 503.
Report-only CLI detects missing/unreadable refs and orphan fingerprints, never
internal keys/paths; no deletion mode. Quiescent default report: 0 rows, no issues.
Crash/ambiguous-commit windows remain explicit recovery obligations; filesystem and
MySQL are not one atomic transaction. See [threat model](../security/image-storage-security.md).

## 11. CONCURRENCY

Real independent InnoDB Sessions and temporary local objects, not process-mutex proof.
Image cases: quota-at-eight, upload/archive, upload/delete, delete/reorder,
delete/delete (one success/one 404), reorder/reorder (one complete serial order),
reorder/archive, five stale ORM snapshots (archive/approval/account/onboarding/count)
and cross-seller public-ref collision. Exactly 13 image concurrency cases.

All-project selector: `concurrency or concurrent or racing or race or _vs_ or duplicate_registration or delayed_resend or delayed_reset_delivery or deadlock`.
**78 passed per run, repeated 3 times, 0 failures**. Earlier auth/refresh/profile/
seller/challenge/catalog/product races remain included. Final API deadlock fault
test also verifies storage/decoder once and DB insertion twice, plus three final
phase eligibility/quota revalidation failures with compensation.

## 12. SECURITY ATTACK TESTS

153 new backend cases: 60 sanitizer/storage/intake units, 80 image API/DB/fault cases,
13 real concurrency/current-read cases. Fake MIME/signature, SVG/HTML/executable,
corruption, GIF/animated PNG/WebP, appended containers, traversal/links/junctions,
actual raw/multipart oversize/forged header, timeout/disconnect, Pillow bomb protection,
foreign ref/BOLA/IDOR, inactive/unverified identities, strict extra fields/files,
malformed rate exhaustion before decode, quota, immutable metadata, commit/flush/
save/delete/compensation faults all covered. Tests use only synthetic small rasters.

Scoped OWASP mapping: object/auth/property/function authority (API1/2/3/5), resource/
business bounds (API4/6), safe configuration/inventory (API8/9). No remote-URL fetch
input (API7); a future production provider requires API10 trust validation.
ASVS control topics: access, validation/file handling, session isolation, errors,
data protection and configuration. This is an implementation/test map, not an
independent certification. [OWASP API Security Top 10](https://api-security.owasp.org/editions/2023/en/0x11-t10/),
[ASVS](https://owasp.org/projects/asvs).

## 13. PUBLIC PRIVACY

Public image fields exactly: ref, position, url. Owner adds MIME/dimensions/size/
creation time. Hidden publicly: storage_key, IDs/FKs, user PII, filenames, private
evidence, credentials/tokens, metadata/comments/EXIF/GPS and private dimensions.
Canonical parent/ref API paths; no private download token in image URLs.

Byte headers: decoded MIME, nosniff, no-store, no-cache, no-referrer; no original
filename Content-Disposition. Public profile contract remains the intended existing
seller indicator; no evidence data added. Runtime-secret/real-user email/phone
comparison against all Phase 10 content and Git diff found zero matches. No actual
.env, venv, dependencies, build output or runtime media is a changed Git path.

## 14. FRONTEND

Strict productImages contracts/API/hooks with three focused components.
Manager: one-file upload, generic multipart filename, client UX limits plus server
authority, synchronous in-flight guard, reorder/cover/delete and archived cleanup.
Preview: central bearer Blob fetch, MIME/size check and current session/version
fencing before accepting results. Effect-created object URLs are removed/revoked
on ref changes/unmount/logout/account switch; no persistent raw files/blobs/tokens.
No arbitrary mutation retry or token-in-src pattern.

Public gallery derives trusted canonical API URL from validated slug/ref, has safe
missing-file and zero-image fallbacks. Private identity/version query keys with
zero retention/no retries; cold mutation-seeded keys also evicted on logout.
Image invalidation does not reset unsaved listing form detail. No heavy DnD library,
new Zustand media state, public feed/search or arbitrary returned URL consumption.

## 15. BACKEND TESTS

Baseline: **1,191 passed**. Final full pytest: **1,344 passed**.
Phase 10 targeted: **153 passed**. Cross-domain security targeted: **689 passed**.
Failures/skips: 0. Warning: one unchanged upstream Starlette/httpx TestClient
deprecation; no application warning suppressed. Compile, Ruff --no-cache and pip
check pass. An initial cached Ruff panic was avoided with the supported no-cache
run; no source/rule disabled.

```powershell
# From backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_product_image_security.py tests/integration/test_product_images.py tests/integration/test_product_image_concurrency.py
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\ruff.exe check --no-cache app tests scripts alembic
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit
```

The focused run selects 20 files across validation/auth/profile/seller/storage/
catalog/handles/product/image boundaries; all 689 pass against the same existing
suite without removed tests or weakened permission/privacy assertions.

## 16. FRONTEND TESTS

Baseline: 274 passed/18 files. Final: **304 passed/19 files**, including 30 new
image contract/preview/cache/switch/order/late-response/mutation/UI cases.
TypeScript: PASS. ESLint: PASS. Production Vite build: PASS. No package changes.

```powershell
# From frontend
npm.cmd test -- --run
npm.cmd exec tsc -- --noEmit
npm.cmd run lint
npm.cmd run build
```

## 17. LIVE MYSQL / STORAGE / HTTP

**145 checks PASS** in real loopback Uvicorn + local MySQL + temporary product/
evidence storage, no real delivery provider. Full existing auth/session/reset/change/
verification/profile/seller/catalog/listing workflow retained, plus JPEG/PNG/WebP
upload/private reads/metadata/order/public visibility/pause/republish/cover-delete/
archive/owner cleanup. Physical objects empty before teardown. Synthetic DB cleanup,
temporary storage removal, server shutdown and preservation all true.

Separate browser invocation: 50 real setup checks + 21 actual UI checks, all pass;
owned Vite/Uvicorn/Chrome stopped, fresh profile/inputs removed, DB/media cleanup true.
No human users/files/storage edited. All 15 pre-existing table fingerprints
unchanged; new product_images empty. This is not backup/restore certification.

| Table | Rows | Ordered SHA-256 |
|---|---:|---|
| `users` | 4 | `891bef3bf220acafe1b66fb708a89bfaf3c92ee2f1d2da384d3b37d6fade2a9d` |
| `user_roles` | 4 | `be38e6e535ea4f631251e5cbe9903b8090db6f1d4d3d5e19d2bb23d11c83fa26` |
| `phone_verification_codes` | 3 | `c0c2eaa4a03ddbcbe06d79bbd19f754aa9fe0e0424b577ce34a1924eec694344` |
| `refresh_tokens` | 7 | `e72016e35f65c47878e515f531ad671eeb3a29a6b69dea942fa430dd6411c2bc` |
| `password_reset_codes` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `email_verification_codes` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `user_profiles` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `seller_verifications` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `seller_evidence` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `seller_verification_audit` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `cities` | 6 | `34aa919e3c4ce4ec79d3fd15aa19c1673eb5ed415bb9e0d01ee4f522b4825e50` |
| `categories` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `admin_catalog_audit` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `catalog_write_lock` | 1 | `e28610836ab702cd35495751839961e9fae54fec4ee18dc4b314862c18c3d104` |
| `product_listings` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `product_images` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |

## 18. MIGRATIONS

Current/heads/history: sole `a10b2c3d4e5f`; alembic check: no upgrade operations.
Existing DB Phase 9 -> 10 additive upgrade succeeded. No real-data downgrade.
Disposable server: empty base -> head, actual listing/image schema comparison,
Phase 10 -> 9 -> 10 preserving prior 15 tables, then prior listing/catalog/challenge/
seller/profile/handle scoped cycles all PASS, drift false, disposable cleanup true.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py --product-images --products --catalog --seller-verification
```

Local server MySQL **9.4**; target MySQL 8 deployment validation remains unverified.
Inherited EXTRA full rollback-to-base error in `c91e4a7b2d6f` (MySQL 1553,
FK-supporting index dropped before FK) remains untouched; full history rollback
is NOT certified. Phase 10 downgrade removes metadata, not external files: review
retention/cleanup before any operational downgrade. No old revision edited.

## 19. OPENAPI

Local: **59**. All-fake development: **63**. Production-configured: **57**.
Exactly six image operations each; five owner Bearer, one public unauthenticated.
Duplicate operation IDs: **0**. Multipart request declares one required binary
file and no extra fields. Owner/public image property allowlists and max-eight
PublicProduct.images verified. No storage-key routes/query credentials/internal
ID navigation or Phase 11 routes/public product collection.
Existing contracts retained except explicit safe public images addition.

## 20. PERFORMANCE

Image bytes through DB: **NO**. Public detail adds one bounded metadata query,
not per-image/catalog/user queries; owner collections remain bounded. No N+1.
Multipart spool is memory-limited then temporary disk; raw read <=10 MiB, output
<=10 MiB. Full pixel decode/encode still allocates raster/encoder memory, not a
streaming image algorithm; 30M-pixel images need measured worker memory/CPU.
Two decoder/intake slots per process and early limits, not a global worker cap.

Preflight holds authority/parent/catalog locks through sanitize/save, conservatively
serializing writes; final commit reacquires rules. This is a documented throughput
tradeoff, not speculative lock refactoring. Local hard-link support/permissions/
capacity, production buffering/timeouts/quotas and crash recovery need deployment tests.

## 21. DEPENDENCIES

Python dependencies/manifests unchanged. Pillow **12.3.0**, WebP support verified.
pip check: PASS. Fresh pip-audit: **0 known vulnerabilities**.
Frontend installed **326 packages**, all match lock; **33 optional platform packages
absent**, no required missing/mismatched version. Manifest/lock consistent, unchanged.
Tailwind **3.4.19**, braces **3.0.3**, selector-parser **6.1.4**.
npm production (`--omit=dev`): **0 vulnerabilities**, exit 0.
npm full: **5 High / 2 Moderate dependency nodes**, exit 1, two inherited roots:

- [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm):
  braces <=3.0.3 stack-exhaustion via nested patterns; High CVSS 7.5, via Tailwind 3
  build chain (chokidar/fast-glob/micromatch).
- [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf):
  postcss-selector-parser <7.1.6 quadratic flat-selector CPU exhaustion; Moderate
  CVSS 5.9, via postcss-nested/Tailwind 3 build chain.

These are explicit release blockers, not seven independent root advisories or proof
of browser runtime exploitation. No forced audit fix/Tailwind 4 migration/pins/install.
Audits used normal HTTPS and machine system CAs; strict SSL true, HTTPS registry,
no certificate-validation bypass.

## 22. BROWSER

**PASS**: actual Chrome headless with fresh isolated synthetic profile, temporary
Vite/Uvicorn, real cookies/MySQL/storage. 21 UI assertions: seller login/draft,
two uploads and decoded authenticated previews, reorder/cover, public gallery/
metadata/bytes, refresh-cookie bootstrap, pause/republish/delete/archive behavior,
archived delete, mobile-width no overflow, logout/private removal/object URL
revocation, no browser-storage private state, second-account denial and URL privacy.

The first combined HTTP+browser attempt exhausted normal shared budgets; an
independent browser invocation fixes QA workload isolation, not application limits.
No TLS/network security flag disabled. No personal profile accessed. This is not
headed human UX/cross-browser/production-origin certification.
[CDP DOM upload protocol](https://chromedevtools.github.io/devtools-protocol/tot/DOM/).

```powershell
.\.venv\Scripts\python.exe scripts/audit_security_http.py
.\.venv\Scripts\python.exe scripts/audit_security_http.py --browser
```

## 23. DOCKER / NGINX

**ENVIRONMENT BLOCKED**: neither docker nor nginx executable is available.
No container startup/healthcheck/proxy/buffering/TLS claim. Static configs reviewed;
only backend .dockerignore media exclusion changed. Existing NGINX 6m body cap is
below Phase 10 10 MiB + 64 KiB envelope: deliberately configure/review the production
proxy and verify runtime upload/time/rate/visibility behavior. No silent infrastructure
rewrite or production deployment in this task.

## 24. DOCUMENTATION

Created: image API and this 28-section gate/manifest. Updated root/backend/frontend
READMEs, documentation index/current status, listing API, four architecture records,
image-storage security and product workflow. Historical Phase 9 reports preserved.
Examples have no live credentials/PII/storage keys. API documents actual budgets,
failure semantics, zero-image publishing and archived/lost-eligibility cleanup.

The requested [product-image-api.md](../api/product-image-api.md) entry point now
links to the already-complete [product-images-api.md](../api/product-images-api.md)
contract. Existing documentation/inbound links were preserved; no duplicate
contract or functional implementation was introduced for the filename mismatch.

## 25. PRODUCTION BLOCKERS

- Two inherited Tailwind 3 build advisories; separate dependency migration required.
- Verified production product object adapter, dynamic visibility/no permanent public
  bucket, private seller-evidence isolation/access/retention and storage permissions.
- Distributed multi-worker rate/intake/decoder/grant coordination and abuse controls.
- Docker/NGINX runtime, body envelope/time/buffering/TLS/proxy validation.
- Target MySQL 8 validation; inherited full-history rollback limitation resolution
  before relying on that rollback strategy; no backup/recovery certification.
- Production secrets/rotation/HTTPS cookie+CSRF origins, real delivery-provider
  credentials/validation, monitoring/cleanup/quotas/retention/backup restoration.
- Load/resource/crash/ambiguous-commit recovery and cross-browser/real production
  acceptance. Headless Chrome local PASS does not remove these release checks.

No confirmed unresolved local Phase 10 application/security blocker.
Production ready remains **NO**, even with all scoped local gates green.

## 26. FILES CHANGED

**65 Phase 10 files: 37 modified tracked, 28 new, 0 deleted**.
All remain unstaged. Reasons and exact paths below; not a staged/commit manifest.

| File | State | Reason |
|---|---|---|
| `.gitignore` | Modified | Ignore development product-media objects. |
| `backend/.dockerignore` | Modified | Exclude local product-media objects from build context. |
| `backend/.env.example` | Modified | Nonsecret product storage provider/root configuration. |
| `backend/alembic/versions/a10b2c3d4e5f_product_images.py` | New | Additive new metadata table; prior revisions untouched. |
| `backend/app/api/v1/products/dependencies.py` | Modified | DELETE receives authenticated write budgets. |
| `backend/app/api/v1/products/image_dependencies.py` | New | Authenticate/budget before strict one-file multipart parser. |
| `backend/app/api/v1/products/image_routes.py` | New | Thin safe HTTP metadata/bytes/order/delete routes and OpenAPI. |
| `backend/app/api/v1/products/routes.py` | Modified | Use configured API prefix for public image URLs. |
| `backend/app/api/v1/router.py` | Modified | Mount only the six scoped image operations. |
| `backend/app/common/product_image_rules.py` | New | Shared bounds and independent opaque ref/key grammars. |
| `backend/app/core/config.py` | Modified | Dedicated product-media root/provider settings. |
| `backend/app/core/http_input.py` | Modified | Bounded timed multipart spooling and guaranteed closure. |
| `backend/app/core/product_image_security.py` | New | Pre-parser peer budgets, actual-byte bounds and intake slots. |
| `backend/app/core/product_security.py` | Modified | Delegate recognized image paths to media-specific intake. |
| `backend/app/main.py` | Modified | Install image boundary and storage adapter, allow DELETE CORS. |
| `backend/app/models/__init__.py` | Modified | Register image metadata with runtime/Alembic. |
| `backend/app/models/product_image.py` | Modified | Replace placeholder with immutable FK/unique/CHECK metadata model. |
| `backend/app/repositories/product_image_repository.py` | New | Parent-qualified current reads, narrow collision retry and resequencing. |
| `backend/app/schemas/product_image.py` | New | Strict minimal owner/public/reorder contracts. |
| `backend/app/schemas/product.py` | Modified | Add bounded safe public image collection. |
| `backend/app/services/product_image_sanitizer.py` | New | Whitelist/decode/container/metadata/orientation/bomb security. |
| `backend/app/services/product_image_service.py` | New | Current authority/quota, pure-DB retries, compensation and audit. |
| `backend/app/services/product_image_storage.py` | New | Separate immutable contained exclusive local adapter; fail closed in production. |
| `backend/app/services/product_service.py` | Modified | Share public visibility projection and safe ordered image DTOs. |
| `backend/README.md` | Modified | Run commands, migration/live/browser/report-only audit usage. |
| `backend/scripts/audit_product_media.py` | New | Report-only missing/orphan inventory; no destructive mode. |
| `backend/scripts/audit_public_handle_migration.py` | Modified | Disposable Phase 10 round-trip and actual-schema/preservation checks. |
| `backend/scripts/audit_security_http.py` | Modified | Real image lifecycle, exact metadata/media cleanup, independent Chrome mode. |
| `backend/scripts/product_image_browser_checks.py` | New | Real synthetic Chrome/CDP lifecycle in fresh owned profile. |
| `backend/scripts/product_image_http_checks.py` | New | JPEG/PNG/WebP live authorization/visibility/cleanup checks. |
| `backend/tests/conftest.py` | Modified | Include new image table in preservation snapshots. |
| `backend/tests/integration/test_product_concurrency.py` | Modified | Delete only synthetic child image rows before owned parent cleanup. |
| `backend/tests/integration/test_product_image_concurrency.py` | New | Thirteen real InnoDB races/current-snapshot/ref-collision cases. |
| `backend/tests/integration/test_product_images.py` | New | Eighty API, DB constraint, fault, privacy and authorization cases. |
| `backend/tests/integration/test_product_listings.py` | Modified | Update exact public/scope assertions for legitimate image additions. |
| `backend/tests/product_image_fixtures.py` | New | Small synthetic raster/GPS/orientation fixtures only. |
| `backend/tests/unit/test_product_image_security.py` | New | Sixty sanitizer/storage/input-boundary attack tests. |
| `backend/tests/unit/test_public_handles.py` | Modified | Allow only new opaque image paths; retain privacy/future-route negatives. |
| `documentation/api/product-api.md` | Modified | Document safe public images and Phase 10 extension. |
| `documentation/api/product-image-api.md` | New | Required singular documentation entry point; preserve existing maintained contract. |
| `documentation/api/product-images-api.md` | New | Six-operation contracts, budgets, privacy and storage recovery semantics. |
| `documentation/architecture/backend-architecture.md` | Modified | Media domain, transaction/side-effect and ingress boundaries. |
| `documentation/architecture/database-design.md` | Modified | New head/schema/constraints, scoped cycles and preservation. |
| `documentation/architecture/frontend-architecture.md` | Modified | Image contracts/hooks/Blob lifecycle and isolated Chrome evidence. |
| `documentation/architecture/system-architecture.md` | Modified | Current domains, separate storage and deployment limitations. |
| `documentation/CURRENT_PROJECT_STATUS.md` | Modified | Superseding dated Phase 10 gate; retain historical reports. |
| `documentation/phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md` | New | This 28-section final evidence, manifest and handoff. |
| `documentation/README.md` | Modified | Link current gate, image API and threat model. |
| `documentation/security/image-storage-security.md` | Modified | Threat/control evidence and explicit recovery/resource limitations. |
| `documentation/workflows/product-workflow.md` | Modified | Listing/image lifecycle, authority and cleanup workflow. |
| `frontend/README.md` | Modified | Image UX, test/run commands and no production claim. |
| `frontend/src/app/queryClient.ts` | Modified | Evict private cold mutation caches even without query metadata. |
| `frontend/src/components/products/OwnerProductImage.tsx` | New | Authenticated version-fenced Blob image and revocation lifecycle. |
| `frontend/src/components/products/ProductImageManager.tsx` | New | Bounded upload, single-flight mutation, cover/order/delete/archive UX. |
| `frontend/src/components/products/PublicProductGallery.tsx` | New | Canonical public URLs and missing/zero-image fallback. |
| `frontend/src/features/productImages/api.ts` | New | Central bearer multipart/Blob transport, version fences and safe errors. |
| `frontend/src/features/productImages/hooks.ts` | New | Private query/mutation isolation and narrowly scoped invalidation. |
| `frontend/src/features/productImages/schemas.ts` | New | Strict refs/metadata/order/path contracts and client-side file UX. |
| `frontend/src/features/productImages/types.ts` | New | Small typed media-command/DTO domain. |
| `frontend/src/features/products/schemas.ts` | Modified | Validate bounded public image collection and parent/ref URL binding. |
| `frontend/src/pages/public/ProductDetailsPage.tsx` | Modified | Render safe public gallery and zero-image fallback. |
| `frontend/src/pages/seller/EditProductPage.tsx` | Modified | Integrate owner image manager without ownership duplication. |
| `frontend/tests/unit/product-images.test.tsx` | New | Thirty negative contract, Blob/cache/switch and mutation/UI regressions. |
| `frontend/tests/unit/product-pages.test.tsx` | Modified | Existing listing fixtures serve the new empty image collection. |
| `README.md` | Modified | Current Phase 10 scope, head, setup and release status. |

Unrelated human artifacts, not modified by Phase 10: output/pdf/unishop-full-architecture-flow.pdf,
tmp/pdfs/build_unishop_architecture.py, tmp/pdfs/rendered/page-01.png through page-11.png
(13 total, all hashes unchanged). No runtime image fixture/photo remains in the repo.

## 27. FINAL GIT STATE

HEAD: `204d85f8fc6ceed59166939905241ab4f74d3e32`, unchanged, tracking equal.
Staged: **0**. Unstaged tracked: **37**.
Untracked: **41** (Phase 10 28; unrelated human artifacts 13).
Deleted: **0**. `git diff --check`: PASS. No secret/runtime-media/build/dependency path
in the Phase 10 manifest. All earlier migration files and manifests/lock unchanged.
Commit created: **NO**. Push performed: **NO**.

## 28. FINAL VERDICT

Image validation sound: YES. Metadata privacy sound: YES. Storage boundary sound: YES.
Ownership sound: YES. Public visibility sound: YES. Ordering sound: YES.
Compensation logic sound: YES within documented non-atomic filesystem recovery semantics.
Concurrency sound: YES. Migration sound: YES for scoped cycles, not full-history rollback.
Frontend isolation sound: YES. Regression intact: YES. Existing data preserved: YES.
No runtime media tracked: YES. No Phase 11 code introduced: YES. Phase 11 may begin: YES.
Production ready: NO.

UniShop China Phase 10 Product Images and Storage passed its local implementation, file-upload security, storage-consistency, architecture, regression, concurrency, privacy, and data-integrity gate. Phase 11 Browse and Search development may begin. Production readiness is not claimed.
