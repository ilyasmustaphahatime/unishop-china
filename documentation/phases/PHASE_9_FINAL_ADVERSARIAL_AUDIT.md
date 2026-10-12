# Phase 9 — Final adversarial double-check

Verified 2026-10-09, Asia/Shanghai. Independent review of the existing UNCOMMITTED
Phase 9 implementation, not a reimplementation, release approval or OWASP
certification. Required local automated gates were rerun; environment-blocked
browser/container gates and unresolved inherited findings are not reported as PASS.

## 1. EXECUTIVE RESULT

Phase 9 double-check complete: **YES**.
Phase 9 local gate still valid: **YES**.
Ready to commit Phase 9: **YES**, after human review; no commit performed.
Ready for Phase 10 after commit: **YES** as a separately authorized development task.
Production ready: **NO**. No Phase 10/11 implementation was introduced.

Confirmed Phase 9 findings: Critical **0**, High **0**, Medium **1 fixed**, Low
**1 fixed**. Additional inherited operational finding: Low **1 unresolved**
(full historical rollback, not the required Phase 9-to-8 rollback).
Inherited npm advisories: **5 High / 2 Moderate dependency nodes**, two root
build advisories; these remain production/security blockers.
Informational limits: upstream TestClient warning; conservative catalog mutex/
offset pagination; local MySQL 9.4 instead of target 8; browser/container runtime
unavailable. No tests were weakened, removed or skipped to obtain the local result.

Final results: **1,191 backend**, **274 frontend**, **434 targeted security**
(including **185 Phase 9**), **61 concurrency cases × 3 green runs**, and
**97 live MySQL/Uvicorn checks**. All 15 development-table fingerprints unchanged.

## 2. BASELINE

Branch: `feature/authentication`.
HEAD: `9cd29f81acc83433f05d49bcb24a1b2555a9e2e9` (`9cd29f8`).
Tracking `origin/feature/authentication` matched that SHA locally; no fetch/push.
Original Phase 9 backend tests: **1,170**. Original frontend tests: **267**.
Initial working tree: **53 Phase 9 files**, 39 modified tracked / 14 untracked /
0 staged / 0 deleted. Preflight Git status/short/-sb, branch, HEAD, six-entry log,
diff check/stat/name-status and untracked inventory were inspected. No unexpected
human changes outside Phase 9 were found.

Original file SHA-256 snapshots and safe ordered database fingerprints were taken
before this review. The original Phase 9 migration and all backend production
files remain byte-for-byte unchanged by this double-check. Dependency manifests,
lockfile, credentials, existing private evidence and historical migrations remain
unchanged. Earlier [implementation report](PHASE_9_PRODUCT_LISTINGS.md) is preserved
as dated baseline evidence, with a pointer to this superseding review.

## 3. CONFIRMED FINDINGS

### P9-A01 — MEDIUM: rapid form submission could create duplicate drafts — FIXED

Area: `frontend/src/components/products/ProductForm.tsx`.
Root cause: disabling controls from TanStack mutation pending state happens after
a React render; two submit events can pass asynchronous form validation before
that pending state is rendered. Creation is intentionally non-idempotent.

Failure scenario: a rapid repeated submission during a slow POST issued **two**
valid draft creation requests. A focused regression was added first in
`frontend/tests/unit/product-pages.test.tsx`: “rapid repeated form submissions
issue only one draft request while delivery is pending”. It failed with **2 POSTs
instead of 1** before the fix.

Minimal fix: synchronous `useRef` guard in the validated event workflow, released
in `finally`. Invoke `handleSubmit` from the event callback, not during render.
This follows the event-handler use of refs described in the
[React reference](https://react.dev/reference/react/useRef). An intermediate lint
failure in the first guard wiring was corrected without suppressing lint rules.

After: regression passes; a second regression proves an explicit retry works
after failure. Full frontend tests, TypeScript, ESLint and build pass.
The guard is per mounted form, not cross-tab/server idempotency. Independent API
POSTs can still create independent drafts; inspect own listings after an ambiguous
network failure before manually retrying. No idempotency service was added.

### P9-A02 — LOW: owner list omitted required condition/update information — FIXED

Area: `frontend/src/pages/seller/SellerProductsPage.tsx`.
Root cause: the response contract contained condition and updated_at, but the list
did not render them. This is a completeness/UI defect, not an authorization flaw.
Failure scenario: an owner could not inspect those listing attributes from “My listings”.

Test-first regression: “owner list includes the listing condition and last-updated
time” failed before the rendering change. Minimal fix adds escaped condition text
and a semantic `time` element with exact ISO `dateTime`; no contract/API change.
After: both assertions and all frontend gates pass.

### INH-A01 — LOW: historical full rollback to base fails — UNRESOLVED / OUT OF SCOPE

Area: unchanged `backend/alembic/versions/c91e4a7b2d6f_add_refresh_session_fields.py`,
revision `c91e4a7b2d6f`, predecessor `a75289cfd4a9`.
Root cause: its downgrade drops `ix_refresh_tokens_replaced_by_token_id` before
`fk_refresh_tokens_replaced_by_token_id`. An EXTRA disposable head-to-base reset
attempt reproduced **MySQL 1553**. MySQL requires the supporting foreign key to be
removed before dropping its required index.
[MySQL foreign-key documentation](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)

Impact: full historical rollback cannot be certified. This is not a Phase 9
listing rollback/upgrade defect and does not prevent a fresh base-to-head upgrade.
No old migration was edited, as explicitly required. It needs a separately approved
historical-migration/rollback resolution; do not run rollback-to-base on real data.

The required permanent harness now tests an empty base-to-head build independently
of legacy/backfill/Phase 9 rollback cycles. Between these two independent cases it
resets ONLY its freshly created disposable schema, after checking its owned running
process, port and resolved `@@datadir`. No working-database reset, foreign-key
disabling or waiver of a failing Phase 9 test was used. Required head→Phase 8→head
passes. The extra full-history downgrade is explicitly NOT claimed as passing.

A suspected trailing-line-terminator contract issue did **not** reproduce; four
passing boundary regressions were retained without speculative schema changes.

## 4. PRODUCT ARCHITECTURE

Routes: `backend/app/api/v1/products/routes.py`, public and seller routers mounted
by `api/v1/router.py`. Dependencies: existing Bearer identity plus listing budgets
and safe HTTP error mapping. Service: **ProductService** (actual class name).
Repository: **ProductRepository**. Model: **ProductListing**.
Schemas: separate ProductCreate/ProductUpdate/OwnProduct/OwnProductList/
PublicProduct/PublicSeller and shared catalog response shapes.

Services own transactions, current authorization and explicit lifecycle transitions.
Repositories own parameterized SQLAlchemy queries, owned predicates, joins,
current locking reads and collision savepoints; no final commit/HTTP exceptions.
Routes contain no direct ORM queries, commits or lifecycle decisions. Frontend
pages→feature hooks→feature API/Zod→centralized Axios client→backend; no duplicate
auth client or frontend authority. Shared seller/onboarding/catalog/text/body rules
are reused rather than forked.

Every original Phase 9 production-code file was manually reviewed, including the
new migration, model/metadata, schemas, repository, service, routes/dependencies,
slugs, ingress/main integration, shared authorization/catalog/profile changes,
four frontend pages, form/badge, API/hooks/contracts/types, router/navigation and
route allowlist. Audit scripts and regression fixtures were also inspected.
Import/forbidden-scope scans and architecture tests found no route→repository/ORM
bypass, repository→route cycle or feature-policy import from neutral input helpers.
Existing services mutate ORM entities within their explicit SQLAlchemy unit of
work; that is the documented design, not an unrelated layer violation.

The 14 model fields are exactly id, seller_user_id, public_slug, title, description,
price, currency, condition, status, city_id, category_id, published_at, created_at,
updated_at. No images/thumbnails/gallery/upload/storage/search/feed/favorites/chat/
deals/payment fields or mounted endpoints were added. Earlier seller evidence
storage and documentation references are not product-media implementation.

### Business invariant → enforcement → database → regression map

Database checks support row integrity, not cross-row authorization or historical
state transitions. “None” below is explicit, not a missing claimed DB guarantee.

| Invariant | Enforcement code | DB constraint / authority | Tests |
|---|---|---|---|
| Seller identity is server-authoritative | listing_user/get_current_user; ProductService.create; repository owned predicates | users FK; identity comes from authenticated current DB user, not body | every_owner_endpoint_requires_bearer; cross_owner_every_operation_generic_not_found; mass_assignment_rejected |
| Owner cannot change | strict six-field inputs; explicit service assignments; ProductListing.immutable_identity | RESTRICT seller FK; no transfer operation; FK alone does not enforce immutability | immutable_orm_identity_and_foreign_keys_restrict; mass_assignment_rejected; additional_authority_fields_are_rejected_without_reflection |
| Slug immutable, non-PII | common/product_slugs; no editable slug; immutable_identity | uq_product_listings_public_slug; ascii_bin; ck_product_listing_slug | complete_lifecycle_price_slug_and_safe_projections; random_slug_generation_opaque_unique_and_valid; slug_collision_across_distinct_sellers_retries_database_constraint |
| Price exact Decimal | ProductCreate/Update strict decimal-string validation; Decimal(body.price); format(.2f) output | DECIMAL(12,2), ck_product_listing_price | money_round_trip_is_exact_in_database_owner_and_public_http; unsafe_price_rejected_without_rounding; price_decimal_boundaries |
| CNY server fixed | no input currency; ProductService.create fixes CNY | ck_product_listing_currency | mass_assignment_rejected; database_constraints_are_real_mysql |
| Only allowed transitions | ProductService.transition explicit allowed map; owned lock | status/publication checks validate row; transition history is service authority | state_machine_all_combinations; lifecycle_races_have_only_valid_serial_outcomes |
| ARCHIVED terminal/read-only | update rejects ARCHIVED; transition excludes ARCHIVED | None for historical transition; status CHECK bounds enum | state_machine_all_combinations; lifecycle_races_have_only_valid_serial_outcomes; archived owner page test |
| First published_at preserved | transition sets only if NULL | ck_product_listing_publication_consistency | complete_lifecycle_price_slug_and_safe_projections; double-publish race; commit_failure_preserves_listing_and_recovers_same_session |
| Publish needs current eligible seller | eligible → lock_verified_seller + completed profile for update; populate_existing | users/seller/profile authoritative rows; no cross-table CHECK | current_eligibility_public_hiding_and_owner_cleanup; stale_identity_map_cannot_publish_existing_draft |
| Publish/assignment needs active catalog | shared catalog DB mutex; CityService/CategoryService current resolve_active | RESTRICT city/category FKs; activation/hierarchy policy in service | catalog_deactivation_vs_publish_is_current_and_publicly_hidden; preexisting_repeatable_read_snapshot_cannot_authorize_stale_assignment |
| Hidden states uniformly public 404 | get_public current joined visibility predicate; safe ProductError | No public authorization DB CHECK | current_eligibility_public_hiding_and_owner_cleanup; catalog_retirement_hides_public_preserves_history_and_can_repair; state_machine_all_combinations |
| Public DTO contains no PII/internal IDs | separate explicit PublicProduct/PublicSeller; narrow projection | None; response allowlist/HTTP behavior | complete_lifecycle_price_slug_and_safe_projections; frontend strict public-field rejection; live HTTP privacy |
| Private caches do not cross accounts | identity+session-version keys, late-response fences, clearSession | None; frontend session boundary | product-session-security.test.ts and auth-session regressions |
| Failed mutation leaves no partial write | shared transaction helper rollback and recovery | ACID transaction/savepoint boundaries | failure_after_mutation_rolls_back_all_changes; five commit_failure_preserves_listing_and_recovers_same_session cases |

Backend test names in the table are prefixed `test_`; files are the product listing,
concurrency, adversarial and contract test modules listed in sections 19/26.

## 5. OWNERSHIP / BOLA

PASS. Seller B knowing A's public slug cannot owner-read, PATCH, publish, pause or
archive A's row. Owned query predicates include current authenticated user ID;
list isolation and pagination never mix owners. All owner operations require
Bearer authentication. Malformed, encoded, mixed-case and unknown references fail
safely; encoded paths are rejected before decoding can become an alias.

Qualified cross-owners/unknown resources get the same generic 404. An authenticated
unqualified caller can receive eligibility 403 independently of resource existence.
Owner DTOs omit internal product/user/city/category IDs and irrelevant private
profile/evidence/session fields. No admin bypass or client-selected seller exists.

## 6. SELLER ELIGIBILITY

Create/edit/publish: current locked ACTIVE account, verified email/phone, actual
VERIFIED Phase 7 attempt, valid completed onboarding. Missing/pending/under-review/
rejected approval and suspended/banned/deleted accounts fail using actual enums.
Roles/JWT labels/frontend badges do not substitute for approval; an approved BUYER
can qualify.

ACTIVE owner read/list/pause/archive remains allowed after verification/onboarding
loss; edit/new publish/republish is denied. Inactive accounts cannot use owner
operations. Public detail hides a formerly published listing on the next request
if account, approval, phone/email or required onboarding becomes invalid; rows are
not deleted. This is request-time visibility, not a real-time browser subscription.

Current locking reads use populate_existing. Five new retained-identity-map tests
load user/verification/profile/catalog/listing objects before another real Session
revokes account/approval/onboarding/city/category state; publish then fails
401/403/422 without changing DRAFT/published_at. Existing stale-create snapshot
tests also pass. Concurrent authority changes serialize through shared locks.

## 7. PUBLIC SLUG

Server-generated `item-` + 24 cryptographic lowercase ASCII hex characters:
96 random bits, bounded URL-safe length, unrelated to title/DB ID/owner/PII.
Unique binary-collated DB constraint is authoritative; title edits and all lifecycle
actions preserve the exact slug. Client-selected slug is rejected.

Eight bounded savepoint attempts retry ONLY MySQL 1062 identifying the named
unique-slug constraint. Forced collision then different candidate succeeds;
cross-seller collision race produces two distinct valid rows. Exhaustion gives a
safe generic 503 with rollback. A new actual unrelated FK1452 regression proves
one candidate only, active Session, and a subsequent valid create succeeds.
No orphan row/transaction or unbounded retry. Navigation uses slugs, never private
IDs/credentials; only bounded owner pagination is in listing query parameters.

## 8. PRICE / MONEY

Python **Decimal**; MySQL **DECIMAL(12,2)**, precision12/scale2, >0 and maximum
9999999999.99. JSON/frontend price stays a strict decimal string through input,
validation, persistence and response; no float arithmetic/conversion found.
Output always has two fractional digits; frontend displays that string without
persisted-value arithmetic. Currency is fixed CNY, not writable.

New exact DB/owner/public HTTP round trips: 0.01, 0.10, 0.30, 19.99, 999999.99.
Invalid zero/negative, three decimals, NaN/infinity/exponents, whitespace/empty,
null/numeric JSON/nondecimal/oversized/leading-zero forms reject without rounding.
Bounds/DB CHECKs and frontend trailing-line-terminator regressions pass.

## 9. LIFECYCLE

Allowed: DRAFT→PUBLISHED/ARCHIVED; PUBLISHED→PAUSED/ARCHIVED;
PAUSED→PUBLISHED/ARCHIVED. ARCHIVED is terminal, owner-readable, not editable.
All other transitions and repeated actions return explicit 409, including repeated
archive. No DELETE, ownership transfer, SOLD or resurrection operation.

DRAFT starts with published_at NULL. First publish assigns it; edit/pause/republish/
archive preserve it. Publish/publish race has one valid publication and one state
conflict, no inconsistent timestamp. Archive wins when it precedes a stale
publish/edit/pause lock; the final state cannot resurrect.

## 10. CITY / CATEGORY

New assignments/publication require active existing public slugs; invalid/inactive/
unknown references fail. Active root and active child-with-active-parent are valid;
no leaf-only restriction was invented. Shared Phase 8 hierarchy/activation logic
and DB mutex are reused.

Deactivation preserves rows/FKs/history/owner detail, hides public detail. Unchanged
retired references can remain during content-only edits; reassigning/publishing
requires current active references. Reactivating valid references can restore public
visibility of a still-PUBLISHED otherwise-eligible listing. Retired profile city
does not erase historical completed onboarding.

City/category retirement versus publish and stale catalog snapshots pass three
repeats. Valid serial outcomes are publication before retirement (then hidden),
or retirement first causing a denied publish; there is no stale-authorized public
listing after retirement commits.

## 11. TRANSACTIONS

Service-owned unit of work checks authority→locks row→catalog current state→validates
allowed mutation→flush/DTO→commit. All relevant failures rollback; repositories
never commit. Nested slug savepoints preserve outer authority locks.

Five new commit-failure injections cover create/update/publish/pause/archive.
Each returns safe 503, preserves original content/status/timestamps and row count,
keeps Session usable, then succeeds on an appropriate retry using that same Session.
Existing after-mutation failure also leaves no partial state. No raw SQL/constraint/
exception details reflected. Bounded existing whole-DB 1213 deadlock retry is reused;
external delivery/storage side effects are not retried.

## 12. CONCURRENCY

**61 all-project selected concurrency/race cases × 3 runs: PASS**, no failures or
flaky outcomes. A preceding integration-only selector had 60 × 3 green runs; final
all-tests selector additionally covers concurrent one-time download-ticket replay.
This is a selected race gate, not a claim that all 1,191 tests run concurrently.
It intentionally deselects 1,130 non-race cases; the separate full suite skips none.

Phase 9 race/current-read module: **19 cases**, included in every final repetition.
Covers collision across sellers; publish/publish; publish/pause from meaningful
states; publish/archive; edit/archive; pause/archive; catalog deactivation/publish;
stale-create snapshots; disjoint partial edits; five stale retained-object publish
cases; new edit/publish preservation. Existing auth/registration/verification/
reset/change/refresh/profile/handle/seller/catalog race suites remain green.

Conflicting same-field edits are intentionally serialized last-writer-wins;
disjoint patches preserve both fields. No speculative ETag/versioning framework.
Lock order: user→approved attempt→profile→listing→catalog mutex→references.
Current locked reads refresh identities and bypass stale REPEATABLE READ snapshots.

Reproducible final selector (backend PowerShell):

```powershell
$raceFilter = 'concurrency or concurrent or racing or race or _vs_ or duplicate_registration or delayed_resend or delayed_reset_delivery'
foreach ($run in 1..3) {
  .\.venv\Scripts\python.exe -m pytest -q tests -k $raceFilter
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

## 13. PUBLIC PRIVACY

Exact public fields: public_slug, title, description, price, currency, condition,
PUBLISHED status, city, category, published_at, seller.
Seller: **public_handle, display_name, seller_verified:true only**.
Catalog shapes reuse public catalog DTOs.

Actual HTTP assertions exclude internal IDs, email/phone, account status/roles,
verification IDs/documents/storage keys, passwords/hashes/tokens/session fields
and owner-only timestamps. Public query selects safe labels/flags rather than
private auth/evidence entities. Owner DTOs likewise omit unnecessary internal IDs.
Unknown/draft/paused/archived/ineligible/retired-catalog rows uniformly return
`{"detail":"Listing not found."}` 404 without hidden-state explanation.

Product/private success AND failure use Cache-Control:no-store, Pragma:no-cache,
Referrer-Policy:no-referrer. Conservative no-store avoids cached-public resurrection
after pause/archive/suspension; no new cache invalidation infrastructure.

## 14. FRONTEND SECURITY

PASS in automated component/contract/session tests; real browser remains blocked.
Identity+session-version private keys, private metadata, zero retention/staleness,
no retries, logout removal and late response/mutation fences prevent A's drafts
appearing for B. Public detail is independently keyed and hides old data after
a failed refetch; server remains authoritative.

Four routes only: /sell/new; /seller/listings; /seller/listings/:slug/edit; /p/:slug.
Owner management is outside ProfileGate for safe hide/archive after eligibility
loss; create remains inside. Direct foreign-owner edit fails at the backend,
not merely a guard. Links validate public slugs; no DB ID/token/query-fragment
credential navigation.

Plain React text escapes HTML/SQL-shaped and Unicode content; no innerHTML sink,
description logging or browser-storage draft/token state. Strict Zod contracts
match owner/public/timestamp/catalog/status/condition/price boundaries, no blind
API casts. Archived UI has no resurrection actions; server also rejects them.
The synchronous form guard now closes the proven double-submit window and releases
on errors; shared API client does not retry arbitrary failed mutation delivery.

## 15. RATE LIMITS

Create/PATCH/publish/pause/archive: shared actual-peer **90 writes/min** before
parsing; authenticated **30 writes/user/min**, plus common **120 peer/min**.
Owner/public reads: actual-peer **180/min**; authenticated owner **60/user/min**.
Namespaces/HMAC identity follow existing shared limiter behavior.

Malformed JSON, wrong content type, unauthenticated/invalid-auth/extra-field bodies
consume the preparse budget. Forwarded headers cannot spoof actual peer.
Input is bounded by actual 32KiB and 15 seconds, including chunks/timeouts/disconnects.
Safe 408/413/415/422/429 responses, no input reflection; 429 includes Retry-After.
Encoded aliases reject safely. Process-local limiters remain a multi-worker
production blocker; no Redis/distributed control was added or falsely certified.

Listing mutations require a Bearer header, not ambient refresh-cookie authority.
They do not introduce cookie-authenticated CSRF endpoints; existing credentialed
CORS and Origin/CSRF policy for refresh/logout/session flows remains tested.
No mechanical or bypassing new auth model was introduced.

## 16. DATABASE / MIGRATIONS

Current and sole head: **f9a1b2c3d4e5**, predecessor **e8f0a1b2c3d4**.
Alembic current/heads/history/check: PASS; no drift.
Disposable **empty base→head: PASS** (whole historical upgrade chain).
Disposable required **Phase 9→Phase 8→Phase 9: PASS**; prior scoped handle/profile/
seller/challenge/catalog cycles and preservation: PASS.
EXTRA full-history downgrade to base: **FAIL, inherited INH-A01**, not waived or fixed.

Actual listing schema matches model/new migration: 14 fields, DECIMAL(12,2),
ascii_bin slug/unique constraint, UUID PK, three named RESTRICT FKs,
eight CHECKs, owner updated/id ordering and city/category FK indexes.
Physical deletion of referenced user/city/category is restricted, not cascading;
account states/catalog deactivation preserve listing history.

Harness resets only its self-initialized disposable data directory/schema between
independent cases; no working DB downgrade/reseed/drop/truncate/delete.
No old migration edits. Actual local server **MySQL9.4.0**; MySQL8 deployment
compatibility remains unverified. Ordered counts/SHA-256 across all15 development
tables match the pre-review snapshot exactly; product_listings stays0.

### Safe final data preservation evidence

No row values/PII/credentials are included. Every digest below matches the before
snapshot; Alembic's version table is configuration state, not this row fingerprint.

| Table | Before = after rows | Before = after ordered SHA-256 |
|---|---|---|
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

## 17. PERFORMANCE

Seller collection performs one bounded joined listing query for city/category/
parent, plus fixed authentication/current-user/mutex overhead. No per-product
catalog/seller queries or count query; limit+1 drives next_offset. Deterministic
updated_at DESC,id DESC ordering, limit1–100/default20, offset0–100000.
Owner/public detail are joined queries; public eligibility uses a narrow EXISTS
predicate and no evidence fetch. Query-budget and pagination boundary tests pass.

No confirmed N+1 regression. Conservative catalog mutex can serialize unrelated
reads/writes; offset cost/page movement under concurrent edits is documented.
These are scale-validation limitations, not reasons for speculative caching/search
or mutex refactoring in this task.

## 18. OPENAPI

Local **53**, all-fake-development **57**, production-configured **51** operations.
Exactly **8 listing operations** per variant; duplicate operation IDs **0**.
Seven owner operations declare Bearer security; public GET intentionally does not.
Strict create/update input schemas expose only six editable fields; owner/public
response schemas are distinct. Only slug path variables and bounded owner
limit/offset query parameters: no internal-ID paths or token query parameters.

Regenerated three variants and compared with the original Phase9 snapshots:
all operation metadata inventories/component names, complete eight listing
operations and eight listing schemas unchanged. No image/storage/feed/search or
Phase10/11 operation. Production schema generation is not deployed runtime proof.

## 19. BACKEND TESTS

Before **1,170**; after **1,191 passed**, **0 failures / 0 skips**.
New **21** cases: five commit-recovery, five exact money round trips,
one real non-slug IntegrityError, four extra authority-field negatives,
five retained stale-identity publish denials, one edit/publish race.
No old test weakened or removed.

Focused cross-domain security run: **434 passed** (auth/tokens/refresh/session/
profile/snapshot/handles/seller challenge/evidence/catalog/validation/limits/
transactions/architecture/products).
Phase9 total: **185** =137 original listing API cases +15 new adversarial cases
+19 concurrency/current-read cases +14 unit contracts.
One unchanged upstream Starlette/httpx TestClient deprecation warning;
no application warning suppressed.
Python compile/import, Ruff --no-cache, pip check: PASS.

Fixtures use real MySQL for DB/locking/race/constraint behavior, independently owned
Sessions and exact synthetic cleanup. SQLite/mock-only locking proof is not used.
Full-suite fixture preservation and final development snapshots are clean.

```powershell
# From backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_product_listings.py tests/integration/test_product_adversarial_audit.py tests/integration/test_product_concurrency.py tests/unit/test_product_contracts.py
.\.venv\Scripts\python.exe -m compileall -q app alembic scripts tests
.\.venv\Scripts\ruff.exe check --no-cache app tests scripts alembic
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit
```

## 20. FRONTEND TESTS

Before **267**; after **274 passed**, 18 files, no failures/skips.
Added7: repeated-submit red→green, retry-after-failure, owner condition/time
red→green, and4 trailing-line-terminator contract cases (already passing).
TypeScript **PASS**, ESLint **PASS**, production Vite build **PASS** after final
event-handler guard wiring. No rule disabling, mass formatting or dependency change.

```powershell
# From frontend
npm.cmd test -- --run
.\node_modules\.bin\tsc.cmd -b
npm.cmd run lint
npm.cmd run build
```

## 21. LIVE MYSQL / HTTP

**97 checks PASS**, actual private loopback Uvicorn process + real MySQL, not just
TestClient. Register synthetic users; fake local phone/email prerequisites;
login/profile/onboarding; actual seller draft/three-evidence/admin approval;
catalog/admin; create/owner-read/edit; public-draft404; publish200; pause404;
republish200; archive404; terminal409; cross-owner rejection; minimal seller JSON.
Earlier reset/change/session/logout/security workflow also passes.

Exact synthetic rows/products/catalog/user cleanup **PASS**; temporary private
evidence cleanup **PASS**; server stopped **YES**; safe snapshots unchanged.
No real delivery provider contacted or legitimate user state changed.

```powershell
# Local development backend only; harness refuses non-local/non-development DB
.\.venv\Scripts\python.exe scripts/audit_security_http.py
# Creates its own disposable MySQL instance; never targets the working DB
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py --products --catalog --seller-verification
```

## 22. DEPENDENCIES

pip check **PASS**; fresh pip-audit **0 known vulnerabilities** in actual venv.
Fresh full npm audit: exit1, **5 High / 2 Moderate nodes** from two inherited roots.
Production-only npm audit --omit=dev: exit0, **0 known vulnerabilities**.
This is not a claim of a clean build ecosystem.

| Root advisory | Actual installed / affected range | Inherited build graph |
|---|---|---|
| [braces GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), High stack-exhaustion DoS |3.0.3 / <=3.0.3|Tailwind3 via chokidar/micromatch and fast-glob; High nodes braces/chokidar/fast-glob/micromatch/tailwindcss|
| [postcss-selector-parser GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf), Moderate quadratic selector CPU exhaustion|6.1.4 / <7.1.6|postcss-nested/Tailwind3; Moderate nodes postcss-nested/postcss-selector-parser|

Both remain unresolved production/security blockers for a separate dependency
migration task. **Tailwind3.4.19 retained; no Tailwind4 migration.**
No install/version pins or package/lock edits were needed. All **326 installed**
frontend package versions match lockfile;33 absent optional lock entries are
platform-specific/optional, not missing required packages. Registry is
https://registry.npmjs.org/; strict-ssl=true. Audits use node --use-system-ca and
normal HTTPS verification: no certificate/TLS bypass or insecure registry.

```powershell
# From frontend; normal HTTPS with trusted system certificate store
node --use-system-ca "$env:ProgramFiles\nodejs\node_modules\npm\bin\npm-cli.js" audit
node --use-system-ca "$env:ProgramFiles\nodejs\node_modules\npm\bin\npm-cli.js" audit --omit=dev
```

## 23. BROWSER

**ENVIRONMENT BLOCKED**, not PASS. Used the required
browser:control-in-app-browser skill; connection/bootstrap failed before runtime
because the supplied tool environment omitted sandboxPolicy. No unsupported
fallback and no passing browser claim based on jsdom/build/API smoke tests.

Pending real-browser gate: sign in→create/edit/publish→public detail→pause/
republish/archive; terminal archive; logout→second user private cache isolation;
address-bar privacy; slow/double-submit and failure retry; Unicode/escaped text;
mobile/focus/accessibility. Skill environment must be restored or a human must
record this gate before production readiness.

## 24. DOCKER / NGINX

**ENVIRONMENT BLOCKED**: docker/nginx executables unavailable.
Static current nginx review only: /api/ proxy preserves listing paths and SPA
fallback allows the four frontend routes. Existing infrastructure is development
tooling, not proof of a hardened production static build/TLS/cookie/proxy setup.
No runtime PASS or unrelated infrastructure rewrite.

## 25. DOCUMENTATION

Corrected only facts affected by this independent audit:
current counts/findings/Git inventory, API non-idempotent create/retry behavior,
historical full-base rollback warning, and links distinguishing the old handoff.
Backend/frontend architecture, routes, DTOs, money, lifecycle, eligibility and
migration claims remain consistent with implementation; READMEs contain no stale
numeric final-gate claim requiring edits. Original dated evidence is preserved.

Security review maps BOLA/identity/property authorization, input/text/parameterized
queries, resource budgets, privacy/cache/logging/error controls and inventory to
the existing OWASP API/ASVS project checklist; no formal certification claimed.
Scan of all changed/new files against actual configured secret values and existing
DB user email/phone values found **0 matches**. No .env/private upload/build/
node_modules/venv artifact in the manifest. Runtime values were never printed.

Production **NO** while inherited build advisories, private production storage,
browser/container runtime verification, shared multi-worker limiting/private-grant
coordination, managed secrets/delivery/DB privileges, HTTPS/trusted proxy/cookie/
CORS deployment validation, monitoring/retention/backups/disaster recovery,
target MySQL8 and scale validation remain open. INH-A01 separately blocks claiming
full-history rollback support; it is not waived by the Phase9 scoped local result.

## 26. FILES CHANGED BY DOUBLE-CHECK

**12 files only**, distinct from the original53 implementation files.
Two production UI fixes; four test files; one disposable tooling extension;
five documentation files. Two of these are newly introduced by the review.
No backend production, new listing migration, dependencies or historical migration
was changed by this audit.

| File | Review-only change |
|---|---|
| `frontend/src/components/products/ProductForm.tsx` |Synchronous in-flight submit guard with finally release and event-handler wiring.|
| `frontend/src/pages/seller/SellerProductsPage.tsx` |Escaped condition and semantic updated-at display.|
| `frontend/tests/unit/product-pages.test.tsx` |3 regressions: duplicate submit, explicit retry, owner condition/time.|
| `frontend/tests/unit/product-contracts.test.ts` |4 trailing-line-terminator cases; no speculative schema edit.|
| `backend/tests/integration/test_product_adversarial_audit.py` (NEW) |15 real MySQL rollback/recovery/money/FK/extra-authority tests.|
| `backend/tests/integration/test_product_concurrency.py` |6 stale-identity/edit-publish regressions added to original13.|
| `backend/scripts/audit_public_handle_migration.py` |Independent empty base-to-head/actual-schema gate and verified owned disposable reset.|
| `documentation/api/product-api.md` |Explicit create non-idempotency, form guard and retry semantics.|
| `documentation/architecture/database-design.md` |Scope rollback claims and disclose inherited full-history downgrade defect.|
| `documentation/CURRENT_PROJECT_STATUS.md` |Superseding counts/findings/blockers/Git status; old history preserved.|
| `documentation/phases/PHASE_9_PRODUCT_LISTINGS.md` |Superseding-review pointer, retain original27-section handoff.|
| `documentation/phases/PHASE_9_FINAL_ADVERSARIAL_AUDIT.md` (NEW) |This28-section report, invariant map, data evidence and separate manifest.|

## 27. FINAL GIT STATE

HEAD **9cd29f81acc83433f05d49bcb24a1b2555a9e2e9**, unchanged.
Staged **0**; unstaged tracked **39**; untracked **16**; deleted **0**.
Total **55** original implementation + double-check files.
Original53 retained;43 keep their pre-review byte hashes,10 were additionally
modified as listed in section26;2 review files are new.
git diff --check **PASS**. Local CRLF conversion notices are Git configuration
warnings, not whitespace errors. No staged deletion/new file, commit, push,
reset/restore/clean or development data destruction.
Commit created: **NO**. Push performed: **NO**.

### Full current Phase 9 + double-check changed-file manifest

Status is relative to HEAD. This combined inventory is NOT a claim that the audit
itself created all55 files; section26 is the12-file review-only attribution.

| Status vs HEAD | File |
|---|---|
| New | `backend/alembic/versions/f9a1b2c3d4e5_product_listings.py` |
| New | `backend/app/api/v1/products/dependencies.py` |
| Modified | `backend/app/api/v1/products/routes.py` |
| Modified | `backend/app/api/v1/router.py` |
| New | `backend/app/common/product_slugs.py` |
| Modified | `backend/app/core/authorization.py` |
| Modified | `backend/app/core/catalog_security.py` |
| New | `backend/app/core/http_input.py` |
| New | `backend/app/core/product_security.py` |
| Modified | `backend/app/main.py` |
| Modified | `backend/app/models/__init__.py` |
| Modified | `backend/app/models/product.py` |
| Modified | `backend/app/repositories/catalog_repository.py` |
| Modified | `backend/app/repositories/product_repository.py` |
| Modified | `backend/app/repositories/seller_verification_repository.py` |
| Modified | `backend/app/schemas/product.py` |
| Modified | `backend/app/services/catalog_service.py` |
| Modified | `backend/app/services/product_service.py` |
| Modified | `backend/app/services/profile_service.py` |
| Modified | `backend/README.md` |
| Modified | `backend/scripts/audit_public_handle_migration.py` |
| Modified | `backend/scripts/audit_security_http.py` |
| New | `backend/scripts/product_http_checks.py` |
| Modified | `backend/tests/conftest.py` |
| New | `backend/tests/integration/test_product_adversarial_audit.py` |
| New | `backend/tests/integration/test_product_concurrency.py` |
| New | `backend/tests/integration/test_product_listings.py` |
| New | `backend/tests/unit/test_product_contracts.py` |
| Modified | `backend/tests/unit/test_public_handles.py` |
| New | `documentation/api/product-api.md` |
| Modified | `documentation/architecture/backend-architecture.md` |
| Modified | `documentation/architecture/database-design.md` |
| Modified | `documentation/architecture/frontend-architecture.md` |
| Modified | `documentation/CURRENT_PROJECT_STATUS.md` |
| New | `documentation/phases/PHASE_9_FINAL_ADVERSARIAL_AUDIT.md` |
| New | `documentation/phases/PHASE_9_PRODUCT_LISTINGS.md` |
| Modified | `frontend/README.md` |
| Modified | `frontend/src/app/router.tsx` |
| Modified | `frontend/src/components/layout/AuthenticatedLayout.tsx` |
| Modified | `frontend/src/components/products/ProductForm.tsx` |
| Modified | `frontend/src/components/products/ProductStatusBadge.tsx` |
| Modified | `frontend/src/features/products/api.ts` |
| Modified | `frontend/src/features/products/hooks.ts` |
| Modified | `frontend/src/features/products/schemas.ts` |
| Modified | `frontend/src/features/products/types.ts` |
| Modified | `frontend/src/pages/public/ProductDetailsPage.tsx` |
| Modified | `frontend/src/pages/seller/AddProductPage.tsx` |
| Modified | `frontend/src/pages/seller/EditProductPage.tsx` |
| Modified | `frontend/src/pages/seller/SellerProductsPage.tsx` |
| Modified | `frontend/src/routes/routePaths.ts` |
| Modified | `frontend/tests/unit/development-route.test.tsx` |
| New | `frontend/tests/unit/product-contracts.test.ts` |
| New | `frontend/tests/unit/product-pages.test.tsx` |
| New | `frontend/tests/unit/product-session-security.test.ts` |
| Modified | `README.md` |

## 28. FINAL VERDICT

| Required invariant/gate | Verdict |
|---|---|
|Ownership sound|YES|
|Eligibility sound|YES|
|Lifecycle sound|YES|
|Money handling sound|YES|
|Catalog race handling sound|YES|
|Public privacy sound|YES|
|Frontend isolation sound|YES (automated; browser environment blocked)|
|Transaction model sound|YES|
|Concurrency sound|YES, three green61-case runs|
|Migration sound|YES for requested base-upgrade and Phase9-to-8-to-9 gates; inherited full-base downgrade NOT certified|
|Architecture sound|YES|
|Regression intact|YES|
|Existing data preserved|YES, all15 fingerprints|
|No Phase10/11 code introduced|YES|
|Ready to commit Phase9|YES, human review required; nothing staged|
|Ready for Phase10 after human commit/separate authorization|YES, not started|
|Production ready|NO|

UniShop China Phase 9 Product Listings Core passed its final adversarial double-check across ownership, lifecycle, monetary precision, catalog consistency, privacy, concurrency, migrations, architecture, and regression. Phase 9 is ready to commit. Production readiness is not claimed.

