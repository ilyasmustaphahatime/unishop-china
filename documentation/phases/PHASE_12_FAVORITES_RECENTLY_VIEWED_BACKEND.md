# Phase 12 — Favorites & Recently Viewed Backend

Implementation evidence, 2026-10-19. This report distinguishes implementation
verification from the independent final audit and later human Git closure.

## 1. Phase purpose

Give authenticated users private saved-product lists and explicit, bounded
viewing history using the existing FastAPI/SQLAlchemy/MySQL modular monolith.
These associations never grant access to hidden products or seller evidence.

## 2. Scope and Git baseline

Initial branch `feature/authentication`, committed HEAD
`eb563b80b21bd70bdfe00875aaacb3fd69078b13`, synchronized with its existing remote.
Initial tracked/index state clean; exactly 13 protected artifacts untracked.
Backend-only tables, contracts, repositories, services, routes, cursors, security
boundaries, tests and documentation. No dependency upgrades, frontend feature,
anonymous tracking, public counts, recommendations, Phase 13, staging, commit or
push. Final implementation is intended to remain unstaged at that same HEAD.

## 3. Architecture

`api/v1/me/*_routes.py` handles HTTP and trusted dependencies. Strict schemas live
in `schemas/product_personalization.py`. Feature services own policy and the
existing transaction/deadlock boundaries; repositories contain SQL, no commits or
HTTP exceptions. `product_card_projection.py` and `services/product_card.py`
extract the existing browse projection/serializer for reuse. Phase 11B query SQL
and bound parameters were compared against committed HEAD for five representative
sort/filter/cursor cases: no differences. No broad Phase 11B refactor.

## 4. Database ERD

`users.id` → `product_favorites.user_id` ← composite unique association →
`product_favorites.product_listing_id` → `product_listings.id`.
`product_recent_views` independently has the same two parents. Neither table
duplicates product titles, prices, slugs, seller information or media metadata.

## 5. Table schemas

| Table | Composite primary key | Timestamp |
|---|---|---|
| `product_favorites` | `(user_id CHAR(36), product_listing_id CHAR(36))` | non-null `favorited_at DATETIME(6)` |
| `product_recent_views` | `(user_id CHAR(36), product_listing_id CHAR(36))` | non-null `last_viewed_at DATETIME(6)` |

Types match the existing UUID parent columns. UTC application timestamps are
stored without an offset in MySQL and returned as explicit UTC association times.
Inherited charset/collation follows existing table conventions. No surrogate ID,
JSON relationships, denormalized product data or speculative counters.

## 6. Foreign keys and indexes

Four explicitly named FKs reference `users.id` and `product_listings.id`, all
`ON DELETE CASCADE`. Each table has a `(user_id, timestamp, product_listing_id)`
index and an explicit listing-only FK index. Reverse scans support recent time
ordering; public-slug tie ordering may use a bounded per-user sort. No claim that
the public-slug tie-breaker is fully covered by the product-ID index. Physical
parent deletion cascades; lifecycle changes do not delete associations.

## 7. Migration

New revision `c12d3e4f5a6b`, parent `b11b2c3d4e5f`, is the only new migration.
It creates only the two Phase 12 tables/indexes/constraints. Historical migrations
are untouched. Development MySQL 9.4 was upgraded forward only; current and sole
head are `c12d3e4f5a6b`, and `alembic check` reports no new upgrade operations.

A cached official MySQL 8.4.11 image supplied a disposable loopback-only runtime,
with generated credentials kept out of logs and source. Full historical upgrade
to Phase 11B, representative existing seller/profile/roles and 12 listings,
Phase 12 upgrade → downgrade to Phase 11B → re-upgrade all passed. Existing row
fingerprints and `SHOW CREATE TABLE` definitions stayed identical except the
expected Alembic version. Representative association writes, duplicate-pair/FK
rejection, both CASCADE paths, indexes and exact `123456` microsecond round-trip
passed. No development downgrade, database drop or history rewrite occurred.

Reproduction on a **disposable** configured database, from `backend`:
`python -m alembic upgrade b11b2c3d4e5f`, seed representative prior data,
`python -m alembic upgrade head`, verify, `python -m alembic downgrade b11b2c3d4e5f`,
verify prior data/schema, `python -m alembic upgrade head`, then
`python -m alembic current`, `heads`, and `check`. Never use this downgrade cycle
against development data.

## 8. API contracts

See [the complete API contract](../api/favorites-recently-viewed-api.md).

| Method/path under `/api/v1` | Result |
|---|---|
| PUT `/me/favorites/{slug}` | 200 `{"favorited":true}` |
| DELETE `/me/favorites/{slug}` | 204 |
| GET `/me/favorites` | favorites page |
| POST `/me/favorites/lookup` | bounded boolean membership map |
| POST `/me/recently-viewed/{slug}` | 204 |
| GET `/me/recently-viewed` | history page |
| DELETE `/me/recently-viewed/{slug}` | 204 |
| DELETE `/me/recently-viewed` | 204 |

All eight require existing Bearer authentication. Only lookup accepts a JSON body:
1–50 unique valid `product_slugs`, no other fields. Lists accept only canonical
`limit` 1–50 (default 24) and a maximum-512-character signed cursor. Other commands
are bodyless and reject query parameters. There is no user-ID input.

## 9. Favorites rules

Only a currently public product can be saved. Repeated PUT succeeds without a new
row or changing the original timestamp, including when at quota. Stored hidden
associations count toward the cap and remain retained, but cannot be affirmatively
looked up or listed until public again. Removal is idempotent, current-user scoped
and permitted for hidden products; unknown/non-favorited slugs return the same
204. Quota errors do not evict saved items.

## 10. Recently Viewed rules

Explicit POST verifies public eligibility and performs a single-pair MySQL
upsert. `GREATEST(existing, observed)` prevents stale observations replacing a
newer timestamp. Retention removes only the current user's oldest excess rows.
Repeated delete/clear is safe; clear actually deletes history and never favorites.
Public product GET remains read-only. No automatic frontend recording is claimed.

## 11. Product visibility integration

Shared `publicly_visible()` applies within SQL before LIMIT for lists, identity
checks and lookup. DRAFT, PAUSED, ARCHIVED, ineligible/suspended/unverified seller,
incomplete onboarding, inactive city/category/parent all remain hidden. Tests
compare against canonical public details, preserve hidden rows, then republish
and verify reappearance. No-image products are valid; cover reorder reads current
public image references. Neither private evidence nor internal storage keys enter
the projection or response.

## 12. Authentication and authorization

`get_current_user` provides trusted identity; ordinary buyers need no seller
approval. Missing/invalid/expired tokens and unavailable accounts follow existing
401 conventions for syntactically valid requests. Every read, lookup, delete,
prune and clear constrains `user_id` from that identity. Writes additionally lock
and re-check the ACTIVE actor through `lock_active_user`. Independent buyer tests
prove cross-user reads/deletes/clears and cursor replay cannot access another
user's lists. Client fields cannot choose ownership.

## 13. Cursor design

`PersonalizationCursorCodec` derives a stable HMAC-SHA256 key from existing
validated shared browse-signing configuration (development can derive from JWT),
using `unishop-personal-lists-v1`. Separate context and page signature domains
prevent browse/JWT/list confusion. Payload contains version, keyed context digest,
UTC timestamp and public slug, never a raw user/product UUID. Context binds user,
list purpose and limit. Canonical base64url, exact keys/types, duplicate-key/date
validation and constant-time comparisons reject malformed, tampered, rotated,
cross-user, cross-list, public-browse and changed-page-size tokens. Key rotation
intentionally invalidates prior private cursors. No per-instance random key.

Pagination orders `(timestamp DESC, public_slug DESC)`, reads `limit+1`, and emits
no total count. Stable equal-timestamp datasets paginate without missing/duplicate
items. Mutating history or eligibility between requests is not a snapshot.

## 14. Quotas and retention

`PERSONAL_FAVORITES_LIMIT`: default/max 500, minimum 1.
`PERSONAL_HISTORY_LIMIT`: default/max 100, minimum 1.
Hidden rows count toward both stored sets. Favorites never silently evict; new
over-cap saves return 409. History keeps the newest bounded set. Timestamp ties
for pruning use private product ID; public pagination ties use public slug.
Reduced configured limits are supported within those fixed maximum working sets.

## 15. Concurrency strategy

All personal writes lock the same actor User row first, keeping serialization
per user rather than global. Current `FOR UPDATE` association reads see committed
quota/history after lock waits even when authentication opened a MySQL REPEATABLE
READ snapshot earlier. Composite keys enforce unique pairs independently.

Real Uvicorn/MySQL 8 races A–E each passed three rounds: duplicate favorite keeps
one row/original timestamp; distinct saves at cap cannot overflow; repeated view
creates one row; concurrent distinct views obey retention and isolate other
users; clear versus record produces a transaction-order-consistent empty/single
new-view result. The live gate uses small configured caps 5/4, while integration
tests exercise actual defaults 500/100.

## 16. Transaction ownership

Feature services use existing `transaction()` and `retry_deadlock()`. Repositories
never commit. Authentication's existing read transaction is handled by the shared
unit-of-work helper rather than an unsafe unconditional rollback. Writes,
retention and commits are atomic; repository and commit failure tests prove
rollback preserves committed state. Only InnoDB 1213 whole-transaction failures
are retried, maximum three attempts; no broad/infinite retry or external side
effect. Public identity checks use normal visibility snapshots without locking
other sellers' User rows.

## 17. Privacy and data retention

All personal successes/errors use no-store/no-cache/no-referrer. No public
personal-list route, favorite count, anonymous activity recording, external
analytics or private identifiers/media are added. No token, cursor, password,
verification code or association contents are logged by the new HTTP boundary.
Hidden rows are retained privately; history clear physically removes current-user
rows. Product image reads independently enforce current eligibility.

## 18. Errors and validation

401 authentication/account; generic 404 hidden/nonexistent save/record; 409 cap;
400 invalid cursor; safe 422 body/query/slug; 413 actual body/query byte limit;
408 input timeout; 415 lookup content type; 405 unsupported method; 429 budget
with Retry-After; 503 unexpected service/database failure. Early input boundaries
can reject malformed requests before authentication. Responses never echo driver
messages, SQL, untrusted request values or hidden lifecycle metadata.

## 19. Rate limits and bounds

Existing `InMemoryRateLimiter` and authenticated identity hashing are reused.
Pre-parser peer: 240 reads/min or 120 writes/min. Authenticated shared peer:
180/min; per-user reads 120/min or writes 60/min. Malformed JSON still spends the
early peer budget. Body maximum 4,096 actual bytes; raw query maximum 1,024 bytes;
input time maximum 15s. Unknown/repeated query parameters, nonempty bodyless
commands, extra fields and duplicate lookup slugs fail safely. Trusted origin PUT
preflight is supported. Distributed controls remain deferred to Phase 19.

## 20. Testing results

| Gate | Result |
|---|---|
| New focused unit tests | 48 passed, 0 failed/skipped |
| New real-MySQL integration tests | 93 passed, 0 failed/skipped |
| Combined focused Phase 12 | 141 passed |
| Full backend final run | 1,599 passed, 0 failed/skipped, 120.18s |
| Existing public-identifier/OpenAPI focused gate | 68 passed |
| Phase 12 real Uvicorn/MySQL 8.4.11 | 204 assertions passed; five races × three rounds |
| Existing complete HTTP security workflow on MySQL 8.4.11 | 161 assertions passed |
| Frontend compatibility | 387 tests / 22 files passed |
| Frontend TypeScript / ESLint / production build | all passed |
| Python compile / Ruff --no-cache / pip check | all passed |
| pip-audit | no known vulnerabilities |
| Python type checker | none configured; no invented gate |
| Alembic current / heads / check | one head `c12d3e4f5a6b`, no drift |
| Disposable migration/schema/integrity cycle | passed on MySQL 8.4.11 |

The first full run had 1,598 pass and one outdated OpenAPI allowlist assertion
still forbidding favorites. That test was extended narrowly for the eight approved
authenticated operations, public slug patterns and bounded private queries; its
68-test focused gate passed. No production behavior was weakened to satisfy it.
One inherited Starlette/httpx TestClient deprecation warning remains. No test was
removed or silently skipped. Full npm audit retains inherited 5 High / 2 Moderate
affected build nodes; production-only npm audit has zero findings. No dependency
manifest/lock changes or forced fixes.

Reproduce from `backend`: `.venv\Scripts\python.exe -m pytest -q`,
`-m compileall -q app scripts tests alembic`, `-m ruff check . --no-cache`,
`-m pip check`, `-m pip_audit --progress-spinner off`. The targeted files are
`tests/unit/test_product_personalization.py`, `test_personalization_services.py`,
and `tests/integration/test_product_personalization.py`. The opt-in live gate is
`python -m scripts.personalization_http_checks --allow-development-synthetic-writes
--race-runs 3`; it requires a loopback development DB, seeds only synthetic rows,
uses real login/Uvicorn, and verifies exact cleanup. Existing live regression:
`python -m scripts.audit_security_http` uses its existing loopback/development guard.
From `frontend`: `npm test -- --run`, `npx tsc -b`, `npm run lint`, `npm run build`,
`npm audit`, `npm audit --omit=dev`.

## 21. Security checks

Passing negative tests cover BOLA/IDOR, account switching, cursor user/purpose
replay, tampering and signing key rotation, hidden-status/catalog/seller
differential, projection privacy, SQL parameter binding, lookup uniqueness and
limits, malformed/oversized requests, quotas, cache headers, rates, transactional
failure and user-scoped retention/clear. Existing seller-evidence/image HTTP
security also passed. No new dependency or private media exposure was introduced.
This is implementation verification, not the separate final adversarial audit.

## 22. Query performance

Each list performs one association-driven public projection SELECT for 1, 24 and
50 returned items, independent of result count. Including existing authentication,
tests observe at most three SELECTs. Lookup uses one bounded membership query for
up to 50 slugs. SQL applies user/visibility/keyset before `limit+1`; no OFFSET,
per-page COUNT, N+1, full graph hydration, or Python visibility filtering. Quota
locks at most 501 association rows; history at most 101. Index presence checked
on MySQL 8. No unnecessary marketplace-scale benchmark or capacity claim.

## 23. Data preservation and protected artifacts

All 16 preexisting development data-table counts and full-content SHA-256
fingerprints exactly match the baseline captured before implementation. Users 4,
roles 4, profiles 1, refresh tokens 9, phone codes 3, cities 6 and catalog lock 1
remain intact; the remaining preexisting data tables remain empty. The only
expected schema-state change is Alembic advancing to `c12d3e4f5a6b` and two new
empty association tables. Synthetic HTTP rows cleaned exactly on disposable
MySQL; rollback-based development fixtures preserved their baseline after every
test. Both configured private-storage trees remain empty and unchanged (zero
files); report-only `audit_product_media` returned zero image rows and no issues.
All child Uvicorn processes stopped. Only the newly created disposable MySQL
container was stopped and retained for possible review; no other runtime changed.

The following SHA-256 baseline values were recorded before implementation and
matched exactly after the final development regression. All 13 files still exist,
remain untracked/unstaged, and have zero modifications or deletions.

| Protected path | SHA-256 |
|---|---|
| `output/pdf/unishop-full-architecture-flow.pdf` | `F535B7703BA8962A6A37A34DD1E4F180D984E302A9EF0F13FF8E369B16B75278` |
| `tmp/pdfs/build_unishop_architecture.py` | `4DDA59ADC49DEA386F524393FE6302BE332133F0A4F72BED1DEABFD0CA4C3571` |
| `tmp/pdfs/rendered/page-01.png` | `D9256564C46324898EBE7C901EACD45D9C93053A9886B571537266BDBC45F7B1` |
| `tmp/pdfs/rendered/page-02.png` | `7BE9E52C25EA8ABDA05B9E0B79F47BB4E2BD532A3BA840F5E2B4C81AA3D72F50` |
| `tmp/pdfs/rendered/page-03.png` | `97B51766023C5FA7AF1894D6C8CFE2C7D1F6258916F4FDD62DFAEF0A0D20A936` |
| `tmp/pdfs/rendered/page-04.png` | `1EA753CFDFE3EE00C7F4F2CD9579AE78B3B06F2F7C11B940ED4121F7EF5BFAE2` |
| `tmp/pdfs/rendered/page-05.png` | `E16E7DF37300CE06798D044F8B87536C6EA5503EF312D7E549C685384CF32F8E` |
| `tmp/pdfs/rendered/page-06.png` | `D64019C131A5C04CB4BCF70EA91E160B0CBCAA2DCD0E3C82076F03083518C986` |
| `tmp/pdfs/rendered/page-07.png` | `5203FB5ADA9F691C68DAB165C2B74C0130827CCB50077C4931341033E05C6E62` |
| `tmp/pdfs/rendered/page-08.png` | `85FA0D00A9C78C2E4CF242696643A124DC245523E198467711CB158D29713032` |
| `tmp/pdfs/rendered/page-09.png` | `C034B0C8D9BD10AB085BF5776FC6EEB5F285370D7E5A811E96048D57370CDF82` |
| `tmp/pdfs/rendered/page-10.png` | `EF6B99542D8359C929E433F4DFEE9CF2D69A8C4B1EA567713854E99C7FC38B9D` |
| `tmp/pdfs/rendered/page-11.png` | `95E1490B14E6B3B489FA9311EB7F8B2B3732C07D9436F392785EC13BCA66073E` |

## 24. Known limitations

Mutable lists are not snapshots; timestamps/eligibility can change between pages.
Per-user account locks deliberately serialize short writes and can contend with
other account operations. Caps are bounded portfolio-scale policy, not a capacity
certification. Personal cursors are signed, not encrypted, and contain only the
caller-visible timestamp/public reference plus a keyed opaque context. Changing
the signing key invalidates them. Distributed limits, private production object
storage and deployed operational verification remain separate release work.

## 25. Future frontend integration

Use existing in-memory Bearer authentication, explicitly POST history only after
public details display successfully, and invalidate private caches on account
switch/logout. Respect 409 caps, 429 Retry-After and restart invalidated cursors.
No Favorites/History UI, frontend cache change or anonymous tracking is included.

## 26. Complete changed-file manifest

Expected scoped inventory: 11 modified tracked paths + 24 new paths = 35.
Protected `output/` and `tmp/` artifacts are excluded. Verification: **F** = focused
141 tests, **B** = full backend, **H** = live HTTP, **M** = migration/integrity,
**S** = compile/Ruff, **D** = documentation contract/link review.

| Path | State | Purpose | Verification |
|---|---|---|---|
| `backend/.env.example` | MODIFIED | document numeric caps, no secret values | F/S |
| `backend/app/api/v1/router.py` | MODIFIED | register both `/me` routers | F/B/H/S |
| `backend/app/core/config.py` | MODIFIED | validated bounded cap configuration | F/B/H/S |
| `backend/app/main.py` | MODIFIED | early private boundary, no-store namespace and PUT CORS | F/B/H/S |
| `backend/app/models/__init__.py` | MODIFIED | register new metadata models | F/B/M/S |
| `backend/app/repositories/product_browse_repository.py` | MODIFIED | reuse extracted public card projection, same browse SQL | F/B/H/S |
| `backend/app/services/product_browse_service.py` | MODIFIED | reuse identical public card serializer | F/B/H/S |
| `backend/tests/conftest.py` | MODIFIED | include personal tables in rollback preservation snapshots | F/B/S |
| `backend/tests/unit/test_public_handles.py` | MODIFIED | allow exact Phase 12 public-slug/private pagination contracts | B/S |
| `documentation/CURRENT_PROJECT_STATUS.md` | MODIFIED | current implementation and actual gates | D |
| `documentation/README.md` | MODIFIED | link Phase 12 records | D |
| `backend/alembic/versions/c12d3e4f5a6b_personal_product_associations.py` | NEW | the only additive Phase 12 migration | M/S |
| `backend/app/api/v1/me/__init__.py` | NEW | authenticated namespace package | F/B/S |
| `backend/app/api/v1/me/dependencies.py` | NEW | trusted identity, private budgets/query parsing/error boundary | F/B/H/S |
| `backend/app/api/v1/me/favorites_routes.py` | NEW | four favorite HTTP operations | F/B/H/S |
| `backend/app/api/v1/me/recently_viewed_routes.py` | NEW | four history HTTP operations | F/B/H/S |
| `backend/app/core/personalization_security.py` | NEW | pre-parser actual-byte/time/peer bounds | F/B/H/S |
| `backend/app/models/product_favorite.py` | NEW | unique saved association mapping | F/B/M/S |
| `backend/app/models/product_recent_view.py` | NEW | unique private history mapping | F/B/M/S |
| `backend/app/repositories/favorites_repository.py` | NEW | bounded, user-scoped save/read/lookup/delete SQL | F/B/H/S |
| `backend/app/repositories/product_card_projection.py` | NEW | shared safe card/identity eligibility SQL | F/B/H/S |
| `backend/app/repositories/recently_viewed_repository.py` | NEW | monotone upsert, current reads and scoped history SQL | F/B/H/S |
| `backend/app/schemas/product_personalization.py` | NEW | strict private contracts and UTC times | F/B/H/S |
| `backend/app/services/favorites_service.py` | NEW | save idempotency/quota/transaction orchestration | F/B/H/S |
| `backend/app/services/personalization_cursor.py` | NEW | private user/purpose/limit-bound signed keysets | F/B/H/S |
| `backend/app/services/personalization_errors.py` | NEW | safe domain error contract | F/B/S |
| `backend/app/services/product_card.py` | NEW | shared public serializer, no private fields | F/B/H/S |
| `backend/app/services/recently_viewed_service.py` | NEW | explicit view/retention/clear transactions | F/B/H/S |
| `backend/scripts/personalization_http_checks.py` | NEW | guarded synthetic real HTTP and 3× races with exact cleanup | H/S |
| `backend/tests/integration/test_product_personalization.py` | NEW | 93 MySQL/HTTP/security/integrity cases | F/B/S |
| `backend/tests/unit/test_personalization_services.py` | NEW | 10 stateful policy/commit/rollback cases | F/B/S |
| `backend/tests/unit/test_product_personalization.py` | NEW | 38 cursor/schema/SQL cases | F/B/S |
| `documentation/api/favorites-recently-viewed-api.md` | NEW | caller-facing contracts/errors/privacy | D |
| `documentation/architecture/ADR_PHASE_12_PRIVATE_PRODUCT_LISTS.md` | NEW | bounded associations/locks/cursor decisions | D |
| `documentation/phases/PHASE_12_FAVORITES_RECENTLY_VIEWED_BACKEND.md` | NEW | implementation evidence, complete inventory and limits | D |

The two existing Phase 11B implementation paths changed only to share the public
projection and serializer; public browse visibility, hints, paging, search and
contract remain compatible. The historical public-handle test changes only its
obsolete endpoint allowlist to verify the newly authorized operations.

## 27. Remaining blockers

No known new Critical/High/Medium feature finding from implementation checks.
Inherited development npm findings remain: braces `<=3.0.3`,
GHSA-vfj7-8cjw-p6xm (high), propagated through chokidar/fast-glob/micromatch and
Tailwind 3; postcss-selector-parser `<7.1.6`, GHSA-rj75-hqrm-r3gf (moderate),
through postcss-nested. Audit counts are 5 High / 2 Moderate affected dependency
nodes, not seven independent root advisories. Production-only npm and Python
audits have zero findings. No Tailwind migration, insecure registry/TLS option or
dependency update was performed.

Independent final Phase 12 audit and separate human Git closure are still
required. Production object storage, distributed controls, deployed browser/
Docker/NGINX/operations acceptance and inherited dependency migration remain
release work; this backend implementation does not certify production readiness
or one-million-user capacity. Python type checking is not configured. No mandatory
Phase 12 runtime check was blocked by lack of MySQL 8 infrastructure.

## 28. Final implementation verdict and Git state

**IMPLEMENTED — PENDING FINAL AUDIT AND GIT CLOSURE.**

Ready for independent final audit: **YES**. Production ready: **NO**.
All mandatory local implementation gates passed. Current branch remains
`feature/authentication`; HEAD remains
`eb563b80b21bd70bdfe00875aaacb3fd69078b13`. Scoped inventory is 11 modified tracked
and 24 new Phase 12 paths (35 total), plus 13 excluded protected artifacts.
No staged files, unexpected deletions, credential-pattern findings or whitespace
errors. No commit, push, frontend feature or Phase 13 work. API/ADR contracts
were checked against generated OpenAPI and source. Implementation-time layering
review found no confirmed new defect; a separate final adversarial audit has not
been performed in this task.

**PASS — PHASE 12 IMPLEMENTED AND READY FOR INDEPENDENT FINAL AUDIT**

## Backend Concepts Demonstrated

| Concept | Actual implementation |
|---|---|
| Composite primary key | `models/product_favorite.py` and `product_recent_view.py` identify one row by current user + product. |
| Foreign key | Phase 12 migration references real `users`/`product_listings` UUID columns with CASCADE. |
| Unique association | Composite PK prevents repeated favorite/history pairs at database level. |
| Transaction | Both feature services use `core/transactions.py` to commit the complete policy or roll back. |
| Upsert | `RecentlyViewedRepository.upsert` uses MySQL ON DUPLICATE KEY UPDATE plus GREATEST. |
| Idempotency | Favorite PUT preserves save time; DELETE/clear safely succeed repeatedly. |
| Row locking | `lock_active_user` serializes the current actor; repository FOR UPDATE reads current association state. |
| Race conditions | The live script proves duplicate, quota, retention and clear/record races across three rounds. |
| Authentication | `personal_user` depends on the existing `get_current_user` Bearer validation. |
| Authorization | Every repository operation filters the trusted user's identity, never a client-selected owner. |
| BOLA/IDOR | Two-buyer tests prove one user's read/delete/clear/cursor cannot address another's data. |
| Keyset pagination | Both repository pages seek strictly below the prior timestamp/public-slug pair. |
| Signed cursor | `PersonalizationCursorCodec` authenticates versioned user/list/limit context and position. |
| N+1 query | Shared card projection obtains public seller/catalog/cover fields in one page SELECT. |
| Database index | Per-user time/product and listing FK indexes bound personal reads and referential work. |
| Service layer | Favorites/history services coordinate cap, locking, serialization and transactions. |
| Repository layer | Separate repositories own parameterized SQL, never HTTP errors or commits. |
