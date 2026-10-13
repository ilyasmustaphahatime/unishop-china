# UniShop China - Phase 10 Final Adversarial Audit

Verified 2026-10-13 (Asia/Shanghai). Independent review of the existing, uncommitted
implementation; not a rebuild. Fresh final results below were obtained after the
security/configuration fixes and final EOF-only whitespace cleanup. Earlier
implementation counts remain historical in [the original report](PHASE_10_PRODUCT_IMAGES_STORAGE.md).

Resume verification: the continuation brief described an earlier three-finding
interruption. All 83 existing paths matched the last verified state by SHA-256,
including the original 65-file implementation, six fixes, report and 13 unrelated
artifacts. No work was reset/recreated. The resume changed only the browser audit,
one integration-test file and the three requested documentation files. Application
code, dependencies, additive migration and legitimate data remained unchanged.
The end-to-end verification workflow added a real delayed-response/account-switch
Chrome probe; a completed-file transport-disconnect regression added one API case.
All final gates below are freshly verified on this continued state, not old counts.

## 1. Executive Verdict

Phase 10 adversarial audit complete: YES.
Local Phase 10 gate valid: YES.
Ready to commit Phase 10: YES.
Ready for Phase 11 after commit: YES, after human review/commit and a separate request.
Production ready: NO. No Phase 11 implementation was started.

Confirmed review findings: Critical 0; High 1; Medium 3; Low 2. All six corrected
and regression-verified. Remaining uncorrected confirmed Phase 10 application
findings: 0. Informational/accepted-limit groups: 9, separately identified below;
these are not a claim of nine new exploitable defects.

- I01: inherited Tailwind 3 build advisories, still production/security blockers.
- I02: private production object/evidence storage, real delivery providers,
  deployment secrets/TLS/access/retention are not configured and certified.
- I03: filesystem/MySQL cannot share ACID; crashes, failed compensation and
  ambiguous COMMIT require reviewed orphan/missing recovery and backups.
- I04: process-local budgets/semaphores and unprofiled worst-case decoder memory
  are not distributed abuse controls or a production capacity certification.
- I05: target MySQL 8 runtime is unavailable; MySQL 9.4 is not a substitute.
- I06: Docker/NGINX runtime and proxy/TLS behavior unavailable; Chrome is not an
  all-browser/platform/production E2E certification.
- I07: a trusted, access-controlled filesystem root is required; a hostile local
  administrator swapping paths between checks/open is outside this sandbox.
- I08: inherited full-history rollback limitation in c91e4a7b2d6f is unchanged;
  only required scoped disposable rollback cycles are certified.
- I09: upstream Starlette TestClient/httpx deprecation warning remains; no test
  was skipped or warning filter introduced to conceal it.

## 2. Git Baseline

Branch: feature/authentication.
HEAD: 204d85f8fc6ceed59166939905241ab4f74d3e32; unchanged throughout.
Original working tree: 37 modified tracked files, 41 untracked, 0 staged/deleted.
Original Phase 10 files: 65 = 37 tracked modifications + 28 new files.
Unrelated artifacts: 13, separately inventoried and hashed; never edited/moved/deleted.

Preflight inspected status, full tracked diff, all untracked Phase 10 text,
artifact metadata/hashes, branch/history and whitespace. No newly introduced
ambiguous human changes were found. No reset/restore/clean/stage/commit/push.
Local upstream comparison remains zero commits ahead; no remote fetch/push claim.

## 3. Confirmed Findings

### A01 - HIGH: invalid-token slow bodies exhausted upload admission

Affected: backend/app/core/product_image_security.py,
ProductImageRequestBoundary.__call__; image_dependencies.image_file;
ProductImageService.preflight_upload/_upload_context.
Root cause: checking only the Bearer header shape before acquiring both global
intake slots and spooling the entire request. Real authentication happened later.
Scenario: two invalid JWT clients deliberately hold their bodies; a valid seller
then receives 429 although neither attacker is authenticated.
RED: test_invalid_bearer_slow_bodies_cannot_reserve_all_global_upload_slots
returned 429 for the valid seller rather than 201 in a gated real-ASGI/MySQL test.
Fix: retain cheap peer/header limits, register a trusted lazy intake callback,
then perform cryptographic auth, account budgets and service-owned current
owner/eligibility/quota preflight before invoking it. Release preflight SQL locks
before network input. Reuse policy helper in actual upload/final metadata checks.
GREEN: valid upload 201; invalid requests 401 without reading their slow bodies;
ineligible/foreign/full requests deny before input; no DB transaction held while
receiving the body. Final 197-image/733-security/full-1388 suites pass.
Limit: valid authorized users can still occupy bounded slots; process-local
budgets, 15-second input deadline and production ingress/distributed controls matter.

### A02 - MEDIUM: unfinished multipart next part committed an image

Affected: backend/app/api/v1/products/image_dependencies.py,
CompleteImageMultipartParser.parse/on_end and image_file.
Root cause: framework parser could return the completed first file despite EOF
in a subsequent incomplete multipart part without a terminal callback.
Scenario: valid PNG followed by the next-part delimiter without its completion.
RED: test_truncated_multipart_cannot_commit_an_image[unfinished_next_part]
returned 201 and created metadata/object, rather than rejecting the envelope.
Fix: narrowly subclass the existing parser, require its terminal callback,
preserve one-file/no-field limits and close its owned-file inventory on rejection,
parser exception or cancellation. No second independent multipart implementation.
GREEN: four incomplete-envelope API cases leave no rows/objects; six controlled
parser exit cases prove 1 MiB rollover and file closure; valid complete input works.
Limit: the owned-file cleanup inventory is a private framework seam; compatibility
tests must accompany framework upgrades. Transport limits remain independent.

### A03 - MEDIUM: multipart I/O and response cleanup crossed error boundaries

Affected: image_dependencies.image_file and image_routes.upload_image.
Root cause: parser dependency exceptions ran outside the route safe-error context,
and default yield cleanup ran after response start.
Scenario/RED: parser OSError produced generic 500 instead of safe 503;
FormData.close failure after a successful service call had already emitted 201.
Tests: test_multipart_filesystem_failure_is_safe_unavailable_not_a_traceback;
test_multipart_cleanup_failure_is_handled_before_response_starts.
Fix: explicit known input/status mapping plus safe unexpected-I/O 503;
Depends(image_file, scope="function") completes cleanup before response headers.
GREEN: expected safe 503 JSON/headers, no sensitive diagnostics; all resource,
fault/compensation and full suites pass. No observed actual path/traceback leakage
is claimed for the pre-fix debug=False deployment.
Limit: a valid image can already be committed when final request-spool cleanup
fails. Preserve it, do not replay/undo it; refetch owner metadata. Upload is not
an idempotent API. The regression explicitly verifies that committed object/row.

### A04 - MEDIUM: NGINX/app upload-size deployment contract mismatch

Affected: infrastructure/nginx/nginx.conf, server body limit/location selection.
Root cause: default 6m rejected images allowed by the application's 10 MiB policy.
RED: test_nginx_product_upload_contract_matches_actual_intake_budget found no
scoped contract matching MAX_MULTIPART_BYTES.
Fix: quoted product collection regex location with client_max_body_size 10551296
(10 MiB + 64 KiB), no URI part in regex proxy_pass. Other/evidence limits remain 6m.
GREEN: scoped static test and complete backend gates pass.
Limit: Docker/NGINX are not installed. nginx -t, proxy buffering/timeouts/TLS,
over-limit 413 and end-to-end boundary uploads are NOT runtime-verified.

### A05 - LOW: previous browser logout preview assertions were vacuous

Affected: backend/scripts/product_image_browser_checks.py, run_browser_checks.
Root cause: deleting every image before logout made “no private image after
logout” pass without exercising a living private preview.
RED: browser-live-private-preview-before-logout failed in the old workflow.
Fix: upload four images, retain two through archived cleanup/logout. Actual React
unmount/remount refetches both; Chrome holds one already-authorized 200 response
while the other preview is decoded/displayed. Logout revokes all live Blob URLs;
only after B signs in is A's response released. Match its loadingFinished event,
let promise/React frames settle, then prove no new Blob URL or old image appears.
The foreign owner page still denies access; parent cleanup removes both objects.
Resume RED: the first new probe failed at private-response-paused because URL-only
navigation waits did not prove component unmount/remount, and the older fixture
could not reliably keep both a live and in-flight preview. DOM disappearance and
settled two-row remount waits plus the fourth image repair that harness weakness.
GREEN: 27 real Chrome UI assertions + 50 setup checks; exact cleanup and hashes
preserved. No frontend production logic change was required.
Limit: headless Chrome on this machine only, supplemented by unit session-fence
cases. No all-browser certification. CDP scheduling records omit headers/cookies/
bodies, and no TLS/auth/rate-limit/production session control was disabled.

### A06 - LOW: image errors omitted consistent anti-sniff/privacy headers

Affected: backend/app/core/product_image_security.py,
ProductImageRequestBoundary protected_send.
Root cause: successful byte responses had nosniff, but route auth/not-found/
validation errors did not consistently receive it.
RED: test_image_error_responses_retain_media_security_headers[403/404/422].
Fix: stamp no-store, no-cache, nosniff and no-referrer on every recognized image
response start, including dependency/validation errors; CORS OPTIONS stays normal.
GREEN: three negative header cases and fresh API/full/security/live/browser gates.
Limit: defense in depth; no image-error XSS exploit was reproduced.

Additional gate hygiene: eleven original untracked Phase 10 files had a single
extra blank at EOF. Removed only those blanks. For the uncommitted Phase 10
migration, adding that LF back in memory reproduces its original SHA-256:
96b7dd03e8138028b9ede0911f27dfe1e11e2c614cdd47bea26eea78d0bb0538.
Its revision, DDL and downgrade semantics are unchanged; historical migrations
were not edited. Full gates were rerun after this whitespace-only cleanup.

## 4. Architecture

Routes: HTTP/schema/auth/budget/file-dependency handling and safe response mapping.
Services: current authority, lifecycle, quota/order, transaction ownership and
explicit DB/storage compensation. Read-only upload admission reuses policy.
Repository: SQLAlchemy metadata/locks/savepoints, bounded collision retries and
two-phase position flushing; no filesystem work or workflow commits.
Storage: narrow immutable binary adapter; no database/user authorization.
Sanitizer: bounded format/decode/orientation/metadata-free re-encoding only.
Dependency boundaries: React page -> feature contracts/hooks -> central API client
-> FastAPI/auth -> service -> repository/MySQL, sanitizer and storage.
Transaction ownership: services/common transaction helper, never routes/repository
hidden commits; pure database deadlock retries never replay decode/storage.
Architecture remained a modular monolith; no generic workflow/storage framework.

## 5. Upload Intake

Multipart parser: one file named file, zero ordinary fields, terminal callback
required; extra/duplicate/wrong-field/unfinished parts rejected before storage.
Pre-parse limits: peer/header checks then real auth/user budget and current
owner/eligibility/quota; only then intake slots and actual-byte spooling.
Raw byte limits: file 10,485,760; multipart 10,551,296; stored 10,485,760 bytes.
Spooling: aggregate spool and framework file spool roll over after 1 MiB;
64 KiB reads, two concurrent intake slots/process, 15-second input timeout.
Resource control: no SQL locks held during body wait; two decoder slots include
expensive encoding. Header lengths are not trusted as the actual-byte authority.
Malformed requests: missing/lying lengths, actual chunked HTTP, excess fields/
files, false MIME, truncated boundaries, incomplete parser states, timeout,
disconnect, cancellation and filesystem failure covered.
Resume ASGI case test_interrupted_completed_file_never_reaches_parser_or_storage:
after a fully delivered file and unfinished next part, disconnect returns safe
400 without calling the parser, closes its owned spool, leaves no rows/objects,
and confirms SQL locks are not retained while waiting for input.
Status mapping includes 400/408/413/415/422/429 and safe unexpected-I/O 503.
Application bounds do not certify OS/server/proxy buffering or DDoS resistance.

## 6. Image Decoder Security

Formats: static JPEG, PNG, WebP only; Pillow 12.3.0 with JPEG/WebP/zlib available.
Signatures: actual decoder format/container structure, not extension/client MIME.
Decode: verify then reopen and fully load; zero/header-only/corrupt/truncated,
SVG/HTML/PDF/executable/GIF/animated inputs rejected.
Pixel limits: 1..6000 each axis, <=30,000,000 pixels; original Pillow bomb
warnings/errors remain active and become rejection, never disabled.
Decompression/animation: checked before expensive load; n_frames/is_animated.
Re-encoding: EXIF transpose -> fresh RGB/RGBA pixel image -> authoritative format;
static WebP lossless, PNG alpha preserved, JPEG canonical RGB. Output size bound.
Strict one-container checks reject trailing archive/executable data. Handles/
decoder semaphore released on success/error; gated concurrency includes encoding.
No antivirus or exhaustive native-decoder fuzzing/capacity certification claimed.

## 7. Image Privacy

EXIF/GPS: synthetic GPS/camera/time/orientation containers re-decoded after output;
not copied to stored/public bytes. Orientation normalized; final dimensions match.
Other metadata: independent JPEG/PNG/WebP ICC/comment/text tests assert the
synthetic source contains metadata and the sanitized output does not.
Public image bytes: canonical rebuilt pixels; no original filename/container,
private seller evidence or profile data. Real photos/documents were never used.

## 8. Filesystem Security

Storage root: separate product-media namespace, private local development root;
overlap with evidence/production local adapter fails closed; no static mount.
Traversal: exact product-media/64-hex grammar, root containment, no client path/key.
Symlinks: check every component; reject links/Windows junctions/target links.
Native Windows junction and neighboring-evidence sentinel tests passed.
Atomic writes: exclusive owned temporary file, flush/fsync, exclusive hard-link
publication, never replacement; two real writers produce one exact winner.
Overwrite protection: random 256-bit keys, existing/temp collision never deletes
an object this save did not own. Read is bounded; delete targets metadata key only.
Temporary cleanup: adapter cleanup/failure tests and synthetic live roots clean;
pending/orphan detection is report-only. No arbitrary TEMP/artifact cleanup.
Host-admin path-swap TOCTOU and OS permission guarantees are not claimed; the
configured root must be inaccessible to untrusted local writers.

## 9. Authorization

Ownership: server current ACTIVE user, parent-qualified slug/ref, DB authority.
BOLA/IDOR: foreign list/bytes/upload/delete/reorder and cross-product references
deny; tokens/roles/client IDs cannot supply ownership.
Seller approval: ACTIVE + verified email/phone + completed onboarding + current
verified seller attempt required for upload/reorder; pending/rejected/revoked deny.
Account state: suspended/banned/deleted authentication denied; authority changes
before final metadata insert rechecked with fresh locks.
Archived behavior: no upload/reorder; ACTIVE owner retains private list/read/delete
including after seller approval/onboarding loss. No visibility restoration.
Cross-seller attempts: real HTTP/MySQL and negative API coverage pass.

## 10. Public Visibility

DRAFT/PAUSED/ARCHIVED: public parent/image 404. PUBLISHED: only if the SAME Phase 9
current public predicate admits account, profile/onboarding, email/phone,
seller approval, active city/category and correct parent/ref.
Seller revoked: parent+bytes hide; ACTIVE owner's private cleanup remains allowed.
Catalog inactive: hide immediately on subsequent public reads; eligible private
owner maintenance is intentionally not prohibited by catalog inactivity alone.
Unknown/mismatched/deleted refs and missing objects return safe consistent errors.
Caching: no-store/no-cache/no-referrer; no permanent bucket/CDN URL or redirects.
An already authorized in-flight response or downloaded/rendered pixels cannot be
retroactively erased. This is request-time access control, not instant cancellation.

## 11. Ordering / Cover

Positions: committed 0..N-1, maximum eight; position 0 is cover.
Reorder: exactly complete current unique parent refs; invalid/duplicate/foreign/
extra/missing/empty-for-nonempty rejected; same/reverse/swap/empty/single supported.
Delete resequence: cover/middle/final/only deletion promotes next cover correctly.
Uniqueness: actual MySQL unique(parent,position); temporary 8..15 then flush final
0..7 inside one locked transaction. Forced failure after intermediate flush rolls
back both reorder/delete, preserves exact prior rows/order/files and session use.
DB checks allow temporary positions but cannot enforce aggregate count/contiguity
or immutable state against privileged direct SQL; application locks enforce these.

## 12. DB/Storage Compensation

Save failure: adapter owns partial-save cleanup; no metadata authority created.
DB flush/constraint/commit failure: rollback, compensate only the newly saved object;
session remains usable; genuine public-ref collisions have bounded retry only.
Final current authority/quota change after storage: reject metadata and compensate.
Delete failure: DB failure preserves metadata/files; physical cleanup failure AFTER
metadata commit leaves unreachable orphan, safe ref-only alert, never restores it.
Orphan handling: report-only missing refs, one-way orphan/pending fingerprints;
no raw paths/keys, no evidence inventory, no destructive default.
Crash recovery: save->metadata or metadata-delete->physical-delete interruption
can leave orphan; ambiguous COMMIT + compensation can leave missing object/row.
No cross-system ACID/background recovery guarantee. Commit/connection failures
modeled with fault injection, not destructive network/process kills on development.
An AFTER-commit request-spool cleanup error returns safe 503; retain committed
image and refetch owner collection, never retry arbitrary upload automatically.
Two existing fault tests now inject at root SessionTransaction.commit for their
own session AFTER storage/metadata; all original rollback/orphan/privacy assertions
retained rather than weakened by the new read-only admission commit.

## 13. Concurrency

Eight-image race: real independent MySQL sessions; 6+4, 7+3 and 8+2 schedules never
commit >8; rejected saved objects compensated; zero..n-1 final positions.
Upload/archive and upload/revocation: final locked metadata revalidation prevents
late state/account/onboarding/approval loss; no product resurrection.
Catalog deactivation: owner maintenance allowed but public bytes hidden.
Delete/reorder, delete/delete, reorder/reorder and upload/delete preserve safe
serial outcomes and unique ordering; pure DB deadlock retry only.
Runs: complete inherited selector extended by new tests, 89 passed x 3;
1299 deselected per run; no flakes/failures.
Selector includes real InnoDB races AND resource/atomic publication tests; it also
matches one safe-I/O test through “traceback”. Do not interpret all 89 as MySQL-only.
New coverage: eight InnoDB schedules + two unit resource/filesystem concurrency
cases + one newly matching error case over prior 78.

```powershell
foreach ($run in 1..3) {
  .\.venv\Scripts\python.exe -m pytest -q -k 'concurrency or concurrent or racing or race or _vs_ or duplicate_registration or delayed_resend or delayed_reset_delivery or deadlock'
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

## 14. Frontend Security

Authenticated preview: central Bearer-header HTTP -> bounded MIME-checked Blob;
temporary object URL, never tokens in image URLs/query/DOM attributes.
Blob cleanup: deletion/replacement/error/unmount/logout/logout-all/account switch;
late responses session-version fenced; aborted/failed fetch cannot attach old pixels.
Query caching: owner ID + session version + slug/ref keys, private flag, gcTime 0,
no automatic mutation retry; eviction includes cold mutation-seeded private keys.
Logout/account switching: real live private Blob revoked; B cannot view A's still
existing image; stale/in-flight API responses rejected by central session fence.
No persistent private image metadata/pixels/tokens in localStorage/sessionStorage.
Single-flight ref prevents double click; error refetch handles ambiguous outcomes.
Independent repeated/manual HTTP uploads are NOT idempotent. No general idempotency
service added. Image mutations do not invalidate/reset unsaved product detail form.
304 frontend tests including prior delayed-response/session/cache/UX cases pass.

## 15. API Privacy

Internal IDs/storage keys/paths: absent from public and owner image JSON/URLs/
headers/error/log outputs; parent-qualified opaque refs only.
Public refs: img- plus 32 random hex (128-bit), bounded, immutable, unique;
repository max eight collision attempts, noncollision IntegrityError not swallowed.
Owner fields: ref, position, url, mime_type, width, height, file_size, created_at.
Public fields: ref, position, url only; zero-image list valid.
Response headers: authoritative rebuilt MIME, nosniff, no-store, no-cache,
no-referrer including 403/404/422 and other image errors; no original filename.
URL privacy: canonical public slug/ref routes; no token/key/user UUID or arbitrary
remote image fetch input. Seller evidence namespace/service/grant/audit stays
private. Cross-namespace/traversal/native-junction and evidence audit tests pass.
Scoped actual-runtime-secret-value scan finds no exposure in Phase 10 text/diff;
synthetic fixtures are not runtime credentials. Not an exhaustive secret/PII DLP tool.

## 16. Database and Migration

Revision a10b2c3d4e5f over f9a1b2c3d4e5; current/sole head match.
No drift: alembic check reports no new upgrade operations.
Constraints: actual 11 columns; seven checks; three unique constraints;
RESTRICT listing FK. No bytes/name column and no destructive earlier-row changes.
Fresh-base migration: disposable empty base -> Phase 10 passes.
Downgrade/upgrade: disposable Phase 10 -> Phase 9 -> Phase 10 passes, prior 15
tables preserved; additional product/catalog/seller/profile/auth scoped cycles pass.
Development database was NEVER downgraded; historical migrations unedited.
Only new migration's extra EOF blank trimmed, proven by reconstructing baseline hash.
MySQL 8 compatibility: inspect CHECK/REGEXP_LIKE/locks/uniques/FK uses; enforced
CHECK semantics require appropriate MySQL 8 version (8.0.16+). Actual environment
9.4.0; Workbench 8.0 is NOT server 8. TARGET MYSQL 8 ENVIRONMENT NOT VERIFIED.
Inherited rollback-to-base index/FK limitation c91e4a7b2d6f remains separate.

```powershell
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py --product-images --products --catalog --seller-verification
```

## 17. Performance

Decode concurrency: two nonblocking slots held through decode/orientation/encoding.
Memory behavior: input/envelope/output/axis/pixel limits; rolled disk spools; still
multiple RGBA surfaces/encoder buffers can allocate hundreds of MiB per job.
No measured production peak RSS, native decoder wall-time preemption or destructive
stress test claim. Input timeout does not bound native encode CPU time.
Storage I/O: immutable fsynced publication and bounded <=10 MiB read, no binaries
in DB; filesystem independent from metadata transaction, explicit compensation.
N+1: bounded ordered metadata collection query, no storage-byte fetch per image
during product serialization; service responses reuse loaded rows. Source inspection,
not a production-load benchmark/query-profiler certification.
Admission controls: cheap peer/header/auth/user/current owner/quota before intake;
no SQL locks during slow input. Initial actual-upload transaction still locks
authority/parent during sanitize/save, an intentional contention/capacity limitation.
Local budgets are bounded-memory but process-local; deployment sizing required.

## 18. Backend Regression

Baseline reported 1344; final freshly passed 1388.
Phase 10 targeted: 197 (prior 153 + 44).
Security targeted: 733 (prior 689 + 44), spanning auth/session/account/seller
evidence/challenge/catalog/profile/product/image/error/storage security.
New cases: 44 = 16 unit + 20 API/ASGI + 8 real-InnoDB adversarial cases.
Removed/weakened tests: 0. Two commit-injection locations corrected, assertions kept.
Failures/skips: 0. One upstream Starlette TestClient/httpx deprecation per pytest run.
Python compilation/import smoke/Ruff --no-cache/pip check all pass.
A generated Ruff cache panic (“wrong package cache”) occurred; uncached full lint
passed, no source/ignore rule changed to suppress it. No cache/artifact deletion.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/unit/test_product_image_security.py tests/integration/test_product_images.py tests/integration/test_product_image_concurrency.py tests/unit/test_product_image_adversarial_audit.py tests/integration/test_product_image_adversarial_audit.py tests/integration/test_product_image_adversarial_concurrency.py
.\.venv\Scripts\python.exe -m compileall -q app tests scripts alembic
.\.venv\Scripts\python.exe -m ruff check --no-cache app tests scripts alembic
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off
```

## 19. Frontend Regression

Baseline/final: 304 passed in 19 test files; 0 failed/skipped.
TypeScript, ESLint and production build pass after final EOF-only cleanup.
The repository has no typecheck npm script; initial invocation failed for that
reason. Corrected to installed tsc -b (also included in build); no package edit.
Build Vite 8.1.5, 349 modules; no Tailwind migration/version-pin/install change.

```powershell
npm.cmd test -- --run
node_modules\.bin\tsc.cmd -b
npm.cmd run lint
npm.cmd run build
```

## 20. Live MySQL / HTTP / Storage

155 real MySQL 9.4/Uvicorn/filesystem checks pass.
Lifecycle: synthetic registration/auth/onboarding/private seller evidence review,
verified sellers, draft JPEG/PNG/WebP + actual HTTP/1.1 chunked fourth PNG without
Content-Length, ordered/owner bytes, reorder/cover, publish/public canonical bytes,
pause/deny/republish, current seller revoke/deny/restore, cross-seller denials,
cover deletion, archive/deny/owner cleanup.
Synthetic cleanup: exact synthetic metadata/parent/users/catalog rows removed,
both isolated media roots removed; owned servers stopped; no real provider called.
Fingerprints: all 16 pre-audit table counts and ordered-row SHA-256 unchanged after
all suites, live/browser and report-only audit. Legitimate user data preserved;
this is row-data verification, not a claim AUTO_INCREMENT/log files never advanced.
Counts: users 4; user_roles 4; phone codes 3; refresh_tokens 7; cities 6;
catalog_write_lock 1; the other ten tables 0, including product listings/images.
Default product/evidence physical files 0. Quiescent report-only storage audit:
image_rows 0, issues [], report_only true, no files/DB mutation.

```powershell
.\.venv\Scripts\python.exe scripts/audit_security_http.py
.\.venv\Scripts\python.exe scripts/audit_product_media.py
```

## 21. Real Browser

PASS: actual Chrome headless with disposable profile and real Vite/Uvicorn/MySQL.
27 UI checks plus 50 setup checks = 77 total; original implementation claimed 21.
Four decoded private previews, cover/gallery/canonical bytes, refresh bootstrap,
pause/republish, cover deletion/archive, mobile no horizontal overflow, actual
living private preview before logout, all created Blob URLs revoked, no persistent
private state, account B isolation and credential-free address bar.
Synthetic DB/media/profile cleanup passes; owned frontend/backend stopped.
No user browser profile, credential screenshots or persistent token artifacts.
Limitations: not all browsers/platforms, assistive tech, mobile devices or production
TLS/proxy deployment. Unit delayed-response/account-change tests complement Chrome.

Resume gate: keep two private images, display one, hold the other HTTP 200 at the
Chrome response boundary, sign out, sign in as B, release A's response, confirm the
same network request finishes, then check after React frames that no old preview
or additional Blob URL exists. This tests late completion, not merely cancellation.
The first RED harness attempt and final GREEN attempt both preserved all data and
cleaned synthetic media/servers. No failed attempt is concealed or called a PASS.

| End-to-end boundary | Evidence |
|---|---|
| UI renders | Four decoded initial previews; one live preview while the second request is held |
| Client -> API | Real owner GET paused by CDP at response stage with status 200 |
| API -> data | Synthetic verified seller and committed private image metadata in real MySQL/storage |
| Data -> response | Held authorized bytes released after account B login; matching Network.loadingFinished |
| Response -> UI | Zero private images and no new Blob URL after late completion/React frames |

Chrome's [Fetch interception protocol](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/)
provides the scheduling gate; no production code or fake API response was substituted.

## 22. Docker / NGINX

Runtime: ENVIRONMENT BLOCKED, docker/nginx executable unavailable.
Ingress limit: scoped product-image collection exactly 10,551,296 bytes; default
other/evidence 6m unchanged; no storage static mount or evidence location overlap.
Mismatch: prior 6m-vs-10MiB configuration corrected, statically regression-tested.
Required deployment action: nginx -t, container startup, real valid-boundary/
oversize 413 tests, buffering/spool quotas/read timeouts/TLS/cache behavior.
Direct Uvicorn/live success is NOT proxy verification. NGINX documents body-size
rejection as 413; deployment behavior must still be tested.
[NGINX body-limit reference](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).

## 23. Dependencies

Python: pip check green; fresh pip-audit zero known advisories.
Pillow: 12.3.0, JPEG/WebP/zlib decoder support verified.
npm production audit: zero vulnerabilities, exit 0.
npm full audit: exit 1, 5 High + 2 Moderate affected nodes, TWO distinct root
advisories rather than seven independent vulnerabilities:

- braces 3.0.3, affected <=3.0.3, High nested-pattern stack exhaustion,
  GHSA-vfj7-8cjw-p6xm. Propagates through chokidar/micromatch/fast-glob/Tailwind.
  [Reviewed advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
- postcss-selector-parser 6.1.4, affected <7.1.6, Moderate flat-selector quadratic
  CPU exhaustion, GHSA-rj75-hqrm-r3gf, via postcss-nested/Tailwind.
  [Reviewed advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf).

Known advisories remain explicit production/security blockers, not waived by
production-only audit zero. Separate dependency migration task; no Tailwind 4.
Installed Tailwind 3.4.19; Vite 8.1.5; React 19.2.7; TypeScript 6.0.3.
Manifest root matches lock; all 326 installed entries match lock, 33 optional
platform packages absent as expected. package.json/package-lock unchanged.
Audit uses normal HTTPS npm registry, strict-ssl true and node --use-system-ca
(machine trusted certificates). No TLS/certificate bypass or registry change.

## 24. OpenAPI

Fresh local/development/production-safe schemas: 59/63/57 operations
(52/56/50 paths). Exactly six image operations; five declare owner auth, one public.
Strict required single-file multipart binary schema; strict owner/public fields;
no image internal IDs/keys/tokens/query credentials or duplicate operation IDs.
Production exposes no fake development-provider routes. Seller evidence retains
its intended private authenticated grant/read routes, never an anonymous route.
Phase 11 feed/search/order/payment/chat operations absent. Import smoke passed.
Schema-safe production generation is NOT production provider/storage readiness.

## 25. Clean Code

Layering verified in actual production diff; no auth/filesystem in repositories,
no authorization in storage, no direct client ownership authority.
Duplication: service _upload_context centralizes added preflight + existing upload/
final checks; public predicate remains ProductService.public_view, not duplicated.
Function complexity: explicit short service methods and narrow intake/parser seam,
no speculative rewrites/giant universal abstraction introduced.
Unsafe abstractions: none added; private parser owned-file seam acknowledged/tests.
Broad exceptions limited to safe HTTP unexpected error mapping, owned resource
cleanup/compensation/ref-only alerts; known statuses preserved, not all failures 422.
Reference retries limited to actual public-ref 1062 index conflicts; pure DB
deadlock scopes do not retry binary I/O.
Architecture findings: no additional confirmed defect beyond A01-A06; maintain
known non-ACID/host-trust/process-local/capacity limitations. Scoped OWASP API1/2/3/4/
5/6/8/9 and ASVS access/validation/session/data/error/config controls covered;
no exhaustive ASVS compliance/certification or all-category claim.

## 26. Documentation

Created: this exact 30-section independent audit.
Updated: product-images API, image-storage threat model, original Phase 10 report
(pointer only, historical numbers preserved) and current project status.
Known limitations: explicit I01-I09, ingress runtime/MySQL8, resource/distributed
controls, non-ACID recovery, no idempotence/retroactive pixel erasure.
Singular product-image-api.md already links to the full API; no document moved.
No Phase 1-9 report rewritten; no unnecessary implementation documentation churn.

## 27. Files Changed by Adversarial Review

29 review-specific files below. This includes 11 EOF-only hygiene edits, two
corrected existing fault-injection locations and documentation, not 29 new features.
Original implementation remains a separate 65-file baseline.

Each review change is classified below as COMPLETE. The NGINX configuration fix
is complete statically, with its optional runtime check explicitly environment
blocked. The previously insufficient browser late-completion coverage now passes;
no incomplete local fix or unresolved Phase 10 application defect remains.
This resume changed five already-inventoried files: product_image_browser_checks.py,
test_product_image_adversarial_audit.py and the three requested report/status files.
All other paths, including the additive migration and unrelated artifacts, retain
their resume-start hashes. No new filename entered the 70-file Phase 10 manifest.

| Filename | Original issue | Change | Test / verification | Classification |
|---|---|---|---|---|
| `backend/alembic/versions/a10b2c3d4e5f_product_images.py` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Migration reconstruction hash proves EOF-only change; no-drift and disposable migration cycles. | Complete |
| `backend/app/api/v1/products/image_dependencies.py` | Incomplete multipart, parser I/O and cleanup failures escaped correct boundaries. | Terminal callback parser, owned-spool cleanup, safe statuses, authenticated service preflight before intake. | Six parser exit cases; four truncated envelopes; safe I/O and cleanup HTTP failures. | Complete |
| `backend/app/api/v1/products/image_routes.py` | Yield cleanup ran after response start. | Use function-scoped upload dependency. | Cleanup failure returns safe 503 before headers; committed image retained. | Complete |
| `backend/app/common/product_image_rules.py` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 1388 tests, image/security suites, compile/Ruff and untracked whitespace check. | Complete |
| `backend/app/core/http_input.py` | Body-limit errors needed a typed distinction. | Add RequestBodyLimitExceeded; retain existing byte/deadline/spool rules. | Exact/over-limit upload and parser error tests. | Complete |
| `backend/app/core/product_image_security.py` | Invalid tokens could occupy intake slots; error responses lacked headers. | Defer intake through trusted scope callback until real auth/preflight; stamp all image response headers. | Invalid-token slow bodies, pre-body denials and 403/404/422 header tests. | Complete |
| `backend/app/repositories/product_image_repository.py` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 1388 tests, image/security suites, compile/Ruff and untracked whitespace check. | Complete |
| `backend/app/schemas/product_image.py` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 1388 tests, image/security suites, compile/Ruff and untracked whitespace check. | Complete |
| `backend/app/services/product_image_service.py` | Network admission occurred before authoritative owner/quota checks. | Shared _upload_context and read-only preflight; release SQL locks before input; retain final locked revalidation. | Pre-body ineligible/foreign/full denials, real MySQL quota and authority races. | Complete |
| `backend/scripts/audit_product_media.py` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 1388 tests, image/security suites, compile/Ruff and untracked whitespace check. | Complete |
| `backend/scripts/audit_security_http.py` | New live helper needed the engine and synthetic identity. | Pass exact synthetic engine/email context to image workflow. | Live HTTP and browser cleanup/fingerprint gates. | Complete |
| `backend/scripts/product_image_browser_checks.py` | Logout checks ran after all previews had been deleted. | Keep two images; verify actual unmount/remount, displayed Blob and held 200 response released after account switch; assert no stale Blob restoration. | 27 real Chrome UI assertions. | Complete |
| `backend/scripts/product_image_http_checks.py` | Live workflow lacked HTTP chunking and actual seller-revocation assertions. | Chunked fourth image and narrowly scoped synthetic seller revoke/restore checks. | 155 fresh live HTTP checks and exact cleanup. | Complete |
| `backend/tests/integration/test_product_image_adversarial_audit.py` | Multipart/admission/error/resequence failures lacked realistic coverage. | 20 API/actual ASGI cases, including completed-file transport disconnect/spool closure; synthetic data and exact cleanup. | 20 green cases, including reproduced RED-to-GREEN findings. | Complete |
| `backend/tests/integration/test_product_image_adversarial_concurrency.py` | Quota and final-authority timing needed stronger real InnoDB probes. | 8 independent-session forced-schedule cases from 6/7/8 images, authority loss and catalog changes. | 8 green cases; combined concurrency selector 89 x 3. | Complete |
| `backend/tests/integration/test_product_images.py` | Admission commit changed where injected commit faults fired. | Target root SessionTransaction.commit for this session after storage/metadata, preserving every compensation assertion. | 197 image-targeted tests; no weakened/deleted assertions. | Complete |
| `backend/tests/unit/test_product_image_adversarial_audit.py` | Storage, metadata, parser and resource contracts lacked adversarial probes. | 16 controlled cases: namespace confusion, metadata, decode capacity, spools, native junction, atomic collision and NGINX. | 16 green cases, including native Windows junction. | Complete |
| `documentation/api/product-images-api.md` | Contract did not describe strict completion, admission and ambiguous cleanup outcomes. | Document admission order, parser rules/statuses, headers, non-idempotence and proxy cap. | Source/OpenAPI/live contract cross-check. | Complete |
| `documentation/CURRENT_PROJECT_STATUS.md` | Current summary referenced the earlier gate. | Add dated final audit status and blockers; retain older dated sections. | Counts/Git/runtime cross-check against final results. | Complete |
| `documentation/phases/PHASE_10_FINAL_ADVERSARIAL_AUDIT.md` | Independent report did not exist. | Create exact 30-section findings/gates/original-review manifest. | 30 headings, all 70 Phase 10 paths and separate 13-artifact preservation check. | Complete |
| `documentation/phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md` | Historical gate could be mistaken for the new audit. | Append superseding audit pointer; retain original results/manifest. | Historical content preserved; Markdown/link review. | Complete |
| `documentation/security/image-storage-security.md` | Threat model needed independent fixes and limitations. | Describe pre-auth slot defense, parser seam, cleanup ambiguity and unverified deployment. | Security suite and manual source/report consistency review. | Complete |
| `frontend/src/components/products/ProductImageManager.tsx` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 304 tests, TypeScript, ESLint, build and untracked whitespace check. | Complete |
| `frontend/src/components/products/PublicProductGallery.tsx` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 304 tests, TypeScript, ESLint, build and untracked whitespace check. | Complete |
| `frontend/src/features/productImages/api.ts` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 304 tests, TypeScript, ESLint, build and untracked whitespace check. | Complete |
| `frontend/src/features/productImages/schemas.ts` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 304 tests, TypeScript, ESLint, build and untracked whitespace check. | Complete |
| `frontend/src/features/productImages/types.ts` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 304 tests, TypeScript, ESLint, build and untracked whitespace check. | Complete |
| `frontend/tests/unit/product-images.test.tsx` | One extra blank line at EOF in an original untracked Phase 10 file. | Remove only that blank; no code/schema/revision change. | Full 304 tests, TypeScript, ESLint, build and untracked whitespace check. | Complete |
| `infrastructure/nginx/nginx.conf` | 6m ingress contradicted 10 MiB image contract. | Scoped product-image cap 10551296 bytes; retain other/evidence 6m limits. | Static contract test; runtime explicitly blocked. | Complete scoped fix; runtime ENVIRONMENT BLOCKED |

Original 65-file Phase 10 implementation manifest (baseline inventory, not newly
created during this adversarial review; per-file original rationale remains in the
original report):

```text
.gitignore
README.md
backend/.dockerignore
backend/.env.example
backend/README.md
backend/alembic/versions/a10b2c3d4e5f_product_images.py
backend/app/api/v1/products/dependencies.py
backend/app/api/v1/products/image_dependencies.py
backend/app/api/v1/products/image_routes.py
backend/app/api/v1/products/routes.py
backend/app/api/v1/router.py
backend/app/common/product_image_rules.py
backend/app/core/config.py
backend/app/core/http_input.py
backend/app/core/product_image_security.py
backend/app/core/product_security.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/product_image.py
backend/app/repositories/product_image_repository.py
backend/app/schemas/product.py
backend/app/schemas/product_image.py
backend/app/services/product_image_sanitizer.py
backend/app/services/product_image_service.py
backend/app/services/product_image_storage.py
backend/app/services/product_service.py
backend/scripts/audit_product_media.py
backend/scripts/audit_public_handle_migration.py
backend/scripts/audit_security_http.py
backend/scripts/product_image_browser_checks.py
backend/scripts/product_image_http_checks.py
backend/tests/conftest.py
backend/tests/integration/test_product_concurrency.py
backend/tests/integration/test_product_image_concurrency.py
backend/tests/integration/test_product_images.py
backend/tests/integration/test_product_listings.py
backend/tests/product_image_fixtures.py
backend/tests/unit/test_product_image_security.py
backend/tests/unit/test_public_handles.py
documentation/CURRENT_PROJECT_STATUS.md
documentation/README.md
documentation/api/product-api.md
documentation/api/product-image-api.md
documentation/api/product-images-api.md
documentation/architecture/backend-architecture.md
documentation/architecture/database-design.md
documentation/architecture/frontend-architecture.md
documentation/architecture/system-architecture.md
documentation/phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md
documentation/security/image-storage-security.md
documentation/workflows/product-workflow.md
frontend/README.md
frontend/src/app/queryClient.ts
frontend/src/components/products/OwnerProductImage.tsx
frontend/src/components/products/ProductImageManager.tsx
frontend/src/components/products/PublicProductGallery.tsx
frontend/src/features/productImages/api.ts
frontend/src/features/productImages/hooks.ts
frontend/src/features/productImages/schemas.ts
frontend/src/features/productImages/types.ts
frontend/src/features/products/schemas.ts
frontend/src/pages/public/ProductDetailsPage.tsx
frontend/src/pages/seller/EditProductPage.tsx
frontend/tests/unit/product-images.test.tsx
frontend/tests/unit/product-pages.test.tsx
```

Five files newly entering the Phase 10 working-tree manifest during THIS review
(the NGINX file already existed committed; only its modification is new):

```text
backend/tests/integration/test_product_image_adversarial_audit.py
backend/tests/integration/test_product_image_adversarial_concurrency.py
backend/tests/unit/test_product_image_adversarial_audit.py
documentation/phases/PHASE_10_FINAL_ADVERSARIAL_AUDIT.md
infrastructure/nginx/nginx.conf
```

Complete final Phase 10 changed-file manifest = those disjoint lists: 70 files,
38 modified tracked + 32 untracked new. All review-specific paths are included.
The 13 unrelated artifacts below are excluded, not hidden or deleted.

## 28. Unrelated Artifact Preservation

Expected artifacts: 13. Preserved YES; modified NO; deleted NO; accidentally staged NO.
Before/after SHA-256 matches for every file; inspected metadata/hashes without edits.

```text
output/pdf/unishop-full-architecture-flow.pdf
tmp/pdfs/build_unishop_architecture.py
tmp/pdfs/rendered/page-01.png
tmp/pdfs/rendered/page-02.png
tmp/pdfs/rendered/page-03.png
tmp/pdfs/rendered/page-04.png
tmp/pdfs/rendered/page-05.png
tmp/pdfs/rendered/page-06.png
tmp/pdfs/rendered/page-07.png
tmp/pdfs/rendered/page-08.png
tmp/pdfs/rendered/page-09.png
tmp/pdfs/rendered/page-10.png
tmp/pdfs/rendered/page-11.png
```

## 29. Final Git State

HEAD 204d85f8fc6ceed59166939905241ab4f74d3e32, branch feature/authentication.
Staged 0. Modified tracked 38. Untracked Phase 10 32.
Unrelated untracked 13. Total untracked 45; total changed paths 83; deleted 0.
git diff --check PASS. All 70 Phase 10 text files separately checked for trailing
whitespace and extra blank at EOF (ordinary Git diff does not cover untracked).
No historical migration diff. New additive migration only final blank trimmed.
Actual runtime-secret-value scan clean; real .env/media/build/venv ignored, not staged.
Commit NO. Push NO. No destructive/reset/restore/clean operation performed.
All substantive production/configuration changes and EOF cleanup preceded final
full regression. Subsequent changes are this report/status pointers only.

## 30. Final Verdict

Image security sound YES; storage boundary sound YES; ownership sound YES;
visibility sound YES; ordering sound YES; transaction/compensation sound YES
within documented non-ACID/ambiguous outcome semantics; concurrency sound YES;
frontend cache isolation sound YES; migration sound YES for verified MySQL 9.4
and required disposable cycles; architecture sound YES; regression intact YES;
existing data preserved YES; unrelated artifacts preserved YES.
Ready to commit Phase 10 YES. Phase 11 may begin after commit YES, with a separate
user request. Production ready NO; outstanding production blockers are not waived.

UniShop China Phase 10 Product Images and Storage passed its final adversarial audit across upload security, image decoding, filesystem isolation, authorization, public visibility, DB/storage compensation, concurrency, frontend privacy, architecture, migrations, and regression. Phase 10 is ready to commit. Production readiness is not claimed.
