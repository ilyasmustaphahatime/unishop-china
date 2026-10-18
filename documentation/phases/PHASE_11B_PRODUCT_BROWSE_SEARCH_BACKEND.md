# UniShop China — Phase 11B Product Browse & Search Backend

Date: 2026-10-14. Baseline: `feature/authentication` at
`f21c4c52e7570f27f2ae119c94b48324959a0e5c`. This report describes the
unstaged working tree. It does **not** claim production readiness, MySQL 8
runtime certification, or one-million-user capacity.

## 1. Executive Result

Backend browse/search is implemented and all executable local functional and
security regressions pass. **Ready for independent final adversarial audit: NO,
pending an isolated-database migration cycle and target MySQL 8 verification.**
The high common-term search latency also needs a release-scale performance
decision. Production ready: **NO**.

## 2. Git Baseline

The starting HEAD/branch matched the expected pushed Phase 11A commit. The
tracked tree and index were clean; 13 named `output/`/`tmp/` artifacts were
untracked. No source state was reset, staged, committed, pushed or deleted.

## 3. Repository Architecture Audit

The FastAPI monolith has public `GET /products/{slug}`, owner routes, MySQL
SQLAlchemy models, Phase 10 media, catalogs, verified sellers and safe request
boundaries. Previously public detail applied visibility partly in Python after
a candidate SELECT. Listing slugs and image refs are immutable public IDs;
internal UUIDs and storage keys are not public contracts.

## 4. Implemented Architecture

`browse_dependencies` parses/bounds inputs; `ProductBrowseService` owns cursor
and response composition; `ProductBrowseRepository` owns the projected SQL;
`BrowseCursorCodec` owns signing; `publicly_visible()` owns the shared policy.
No new service boundary, search daemon, frontend UI or Phase 12 feature was
introduced.

## 5. Public Browse Endpoint

Anonymous `GET /api/v1/products` is canonical, ahead of `/{slug}` in routing.
It returns `200` for an empty catalog and requires no authentication.

## 6. Request Parameters

`q`, `city`, `category`, `min_price`, `max_price`, `condition`, `sort`, `limit`
and `cursor` are documented in the [API contract](../api/product-browse-search-api.md).
Default limit 24, maximum 50. Duplicate/unknown keys are rejected.

## 7. Response Contract

`items`, `next_cursor`, `has_more`; compact public cards only. Card keys are
public slug, title, decimal-string price/CNY, condition, public city/category,
optional cover ref/URL, already-public seller summary and publication time.
No exact count, internal IDs, contact details, storage keys or evidence.

## 8. Public Visibility Reuse

Detail/media and browse now use one SQL predicate: PUBLISHED/non-null
publication, ACTIVE email/phone-verified seller, verified attempt, completed
valid profile, active city, active category and active root parent when child.
The existing generic 404 behavior is preserved. Hidden rows do not consume a
page slot or influence a continuation cursor.

## 9. Search Strategy

One MySQL FULLTEXT index on `(title, description) WITH PARSER ngram`, queried
in Boolean mode. Server-added required terms mean all supplied words are
required, preventing natural-mode union-of-bigrams false matches. Search
results use the selected chronological/price sort, not relevance. Search text
is not sent to another provider.

## 10. Multilingual Search Behavior

Committed real-MySQL tests pass Chinese, Arabic and accented Latin terms.
Seller text is not translated. MySQL ngram token size 2 means one-character
terms and language-specific stemming/synonyms are unsupported. The
[MySQL 8 ngram documentation](https://dev.mysql.com/doc/refman/8.0/en/fulltext-search-ngram.html)
supports the selected parser, but local execution was on MySQL **9.4.0**.

## 11. Search Input Security

NFC and whitespace normalization; max 160 raw characters/80 normalized,
eight words, at least two alphanumeric characters per word. Unicode word
characters/marks/spaces only; controls, bidi controls, Boolean operators and
punctuation are rejected. SQL parameters are bound, never interpolated.

## 12. Filters

Exact active city/category public slugs, exact Decimal CNY bounds, and the
existing condition enum. Category is exact-match, not implicit subtree search.
Inactive catalog rows cannot appear because visibility is SQL-enforced.

## 13. Sorting

Allowlist: `newest`, `price_asc`, `price_desc`; never client-provided SQL
columns. Public slug is the unique deterministic tie-breaker.

## 14. Keyset Pagination

No OFFSET. Strict continuation on `(published_at, public_slug)` descending or
`(price, public_slug)` in the selected direction, with `LIMIT limit+1`.
Stable data pages have no duplicates/omissions in the three-mode tests.
Mutations between requests are not snapshot-consistent and may change pages.

## 15. Cursor Security

Versioned base64url JSON plus HMAC-SHA256, canonical base64 parsing,
constant-time signature check and strict payload shape/type checks. The
cursor contains only public sort value/slug and keyed context digest, never
an internal ID or raw search term. Invalid/oversized/tampered cursors yield
generic 400.

## 16. Cursor Query Binding

A domain-separated keyed HMAC binds normalized q, city, category, Decimal
bounds, condition, sort and limit. Cross-query, filter, limit, sort and
cross-key replay fail. All instances need the same key; rotation invalidates
old cursors and clients restart at page one. A dedicated non-placeholder key
is required outside development; local-only fallback is purpose-separated
from the configured JWT secret.

## 17. Database Query Architecture

One parameterized scalar projection with joins and a correlated indexed
first-position image lookup. Product-side scalar city/category slug lookups,
`STRAIGHT_JOIN` and allowlisted `FORCE INDEX` were added after 20k-row EXPLAIN
demonstrated catalog-first plans and a 266ms rare-category scan. Recheck hints
on target MySQL 8 and different distributions.

## 18. N+1 Prevention

The 24-card integration test observed **one SELECT** for the page, including
seller, catalog and cover metadata. No per-card ORM loading or media bytes.

## 19. Index Changes

Seven additive indexes: global `(status,published_at,public_slug)` and
`(status,price,public_slug)`; matching city/category-prefix newest/price
composites; and ngram FULLTEXT on title/description. These were selected from
common/rare 20k-row query plans, not added speculatively. Existing unique
public slug, catalog and image-position indexes remain unchanged.

## 20. Alembic Migration

One revision `b11b2c3d4e5f` follows Phase 10 `a10b2c3d4e5f`; no historical
migration changed. Development DB received only forward index DDL. `current`,
`heads`, `history` and `check` pass; `check` says no new upgrade operations.
The revision was refined before commit after a rare-filter benchmark; because
the first draft had already been applied locally, its four additional final
indexes were created forward-only in development from model metadata. A fresh
upgrade runs all seven indexes from the final revision.
Upgrade/downgrade/upgrade was exercised on a disposable cloned MySQL table
and dropped afterward. **A wholly separate database cycle was not possible**:
the app user has privileges only on `unishop_china`, and Docker is unavailable.
The development database was never downgraded.

## 21. MySQL 8 Compatibility

The SQL uses documented MySQL 8 ngram FULLTEXT, Boolean MATCH and standard
MySQL index/join hints. MySQL 8 runtime testing remains **ENVIRONMENT
BLOCKED**; installed server reports 9.4.0. This is a release validation gap.

## 22. Query Plan Analysis

At 20k committed synthetic listings, EXPLAIN chose global/newest/price and
city/category-prefix composite indexes for common and rare filters, plus the
ngram FULLTEXT index for keyword queries. JSON plans still reported a filesort
under joined queries; measured ordinary and rare-filter pages stayed low
milliseconds. The search index was genuinely used, not a disguised
leading-wildcard full scan. Plan stability is not guaranteed across data
distributions or MySQL versions.

## 23. Performance Benchmark

`python -m scripts.benchmark_product_browse --rows 20000 --allow-development-synthetic-writes`:
10 samples/scenario on local MySQL 9.4.0, 24-card pages (`LIMIT 25`), committed
synthetic data fully removed. Final p50/p95 in milliseconds: newest
**1.451/5.377**, city **1.470/3.558**, rare city **0.612/0.999**,
category **1.290/3.171**, rare category **0.719/1.511**,
price ascending **2.677/5.970**, price descending **1.435/3.549**,
cursor page **3.433/10.348**, keyword **735.055/823.426**, combined keyword+
filters **737.226/761.840**. Common-term full-text latency is a measured
release concern, not evidence of million-user capacity. The diagnostic
natural-mode query matched all 20,002 synthetic rows due union bigrams;
selected Boolean mode matched the intended 2,001. Results are local, not
throughput SLOs.

## 24. Rate Limiting / Abuse Resistance

Existing public product read budget plus a browse-specific 60/minute peer
budget in the ASGI boundary. A 1,024-byte raw query cap runs before parsing;
malformed/duplicate input consumes budget. This limiter is process-local;
distributed enforcement is a production requirement.

## 25. Privacy and Authorization

Differential detail/browse tests cover suspended account, lost email/phone
verification, incomplete/invalid profile, inactive city/category/parent and
revoked seller verification. Hidden listings and seller evidence never appear.
Compiled SQL excludes password hashes, storage keys and contact fields.

## 26. Product Lifecycle Regression

Draft, paused and archived listings are absent from detail, browse and public
media. Republish uses existing lifecycle rules; no owner behavior changed.

## 27. Seller Eligibility Regression

Current verified attempt, active account and completed onboarding are checked
in the same SQL visibility predicate. The existing owner and seller suites
passed in the full backend regression.

## 28. Catalog Regression

Active city/category and active root-parent tests pass; exact public slug
filters do not create a second catalog. Existing catalog suite passed.

## 29. Product Media Regression

Cover ref follows reorder and delete, public media disappears when listing
pauses, and private seller evidence is never serialized. Phase 10 image tests
and live HTTP media checks pass. No development private media files remain.

## 30. Unit Tests

`python -m pytest tests/unit/test_product_browse.py -q`: passed as part of the
55-test focused gate. Covers Unicode normalization, Decimal bounds, codec
round trips, key rotation, malformed signed payloads and 300 random tokens.

## 31. Repository Tests

Compiled MySQL SQL assertions verify bounded LIMIT/no OFFSET, bind parameters,
Boolean MATCH, allowlisted index hints and no private selected fields. The
24-card live-MySQL statement-count test verifies one query.

## 32. Integration Tests

`python -m pytest tests/integration/test_product_browse.py
tests/integration/test_product_browse_migration.py
tests/unit/test_product_browse.py -q`: **55 passed**. Real MySQL fixtures
rollback or perform exact committed synthetic cleanup.

## 33. Adversarial Security Tests

Tampered/truncated/noncanonical/oversized/cross-query cursors, injected sort,
punctuation/SQL-shaped q, duplicate keys, overlarge query strings, rate-limit
flood and simulated DB/signing failures return safe responses. No secrets or
request values were echoed.

## 34. Pagination Correctness Tests

All three sort modes traverse seven tie-price listings at page size two with
no duplicates/omissions and a terminating null cursor. Page reads recheck
current visibility after a listing is paused.

## 35. Concurrency Tests

The same signed cursor was requested by 12 concurrent threads, repeated
three times, with identical successful page content. This is a local
application/DB check, not distributed load certification.

## 36. Full Backend Regression

After the last production-code change:
`python -m pytest -q --disable-warnings`: **1,443 passed**, one existing
warning. Live loopback Uvicorn/MySQL smoke:
`python -m scripts.audit_security_http`: **161 checks passed**, preservation,
synthetic/media cleanup and owned-server shutdown true.

## 37. Frontend Compatibility Regression

No frontend source or UI changed. `npm test -- --run`: **387 passed / 22
files**. `npm exec -- tsc -b`, `npm run lint`, and `npm run build`: pass.

## 38. Static Quality

Python `compileall` passes. `ruff check --no-cache app tests scripts/...`
passes. Default Ruff cache hit an environment cache panic once; no-cache
rerun passed and no source suppression was added. `git diff --check` reports
zero whitespace errors; Windows line-ending warnings are non-failing.

## 39. Dependency Audit

`pip check`: no broken requirements. `pip-audit`: no known vulnerabilities.
`npm audit --omit=dev`: zero. Full `npm audit`: **7 affected build nodes,
5 high/2 moderate**, through Tailwind 3's `braces` and
`postcss-selector-parser` chains. No unsafe registry/TLS setting or Tailwind
4 migration was performed. This remains a production/security blocker.

## 40. Database Preservation

All 16 development-table row-count/content SHA-256 fingerprints match the
pre-work snapshot after tests, migration probe, benchmarks and live HTTP
checks. The only persistent development DB change is the additive index
migration/head. No real database downgrade, seed rewrite or user row edit.

## 41. Media Preservation

The existing local private product-media and seller-evidence directories
contain zero files after the final checks. Test media used temporary storage;
the live HTTP harness verified physical object cleanup.

## 42. Protected Artifact Preservation

All 13 pre-existing unrelated `output/`/`tmp/` artifacts remain untracked and
unstaged; their SHA-256 hashes match the pre-work snapshot exactly.

## 43. Documentation

This Phase 11B report, the [API contract](../api/product-browse-search-api.md),
the [architecture decision](../architecture/ADR_PHASE_11B_SEARCH_PAGINATION.md),
the documentation index and current status were updated. Historical phase
reports remain untouched.

## 44. Files Changed

Modified tracked paths (20):

```text
backend/.env.example
backend/app/api/v1/products/routes.py
backend/app/core/config.py
backend/app/core/product_security.py
backend/app/main.py
backend/app/models/product.py
backend/app/repositories/product_repository.py
backend/app/services/product_service.py
backend/scripts/product_http_checks.py
backend/tests/integration/test_development_fake_sms_routes.py
backend/tests/integration/test_email_verification_routes.py
backend/tests/integration/test_phase_5e_integrated_auth_security.py
backend/tests/integration/test_product_listings.py
backend/tests/unit/test_development_fake_sms.py
backend/tests/unit/test_email_verification.py
backend/tests/unit/test_password_reset_request.py
backend/tests/unit/test_public_handles.py
documentation/CURRENT_PROJECT_STATUS.md
documentation/README.md
documentation/api/product-api.md
```

New Phase 11B paths (15):

```text
backend/alembic/versions/b11b2c3d4e5f_product_browse_indexes.py
backend/app/api/v1/products/browse_dependencies.py
backend/app/repositories/product_browse_repository.py
backend/app/repositories/product_visibility.py
backend/app/schemas/product_browse.py
backend/app/services/product_browse_cursor.py
backend/app/services/product_browse_service.py
backend/scripts/benchmark_product_browse.py
backend/tests/browse_cursor_support.py
backend/tests/integration/test_product_browse.py
backend/tests/integration/test_product_browse_migration.py
backend/tests/unit/test_product_browse.py
documentation/api/product-browse-search-api.md
documentation/architecture/ADR_PHASE_11B_SEARCH_PAGINATION.md
documentation/phases/PHASE_11B_PRODUCT_BROWSE_SEARCH_BACKEND.md
```

The 13 unrelated pre-existing artifact paths are excluded; no deletions.

## 45. Git Final State

Branch `feature/authentication`; HEAD remains `f21c4c52e7570f27f2ae119c94b48324959a0e5c`.
Expected 35 Phase 11B/report paths are unstaged; zero staged files. No commit,
push or Phase 11C work. Final status/diff checks are required before Git
closure and are recorded in the handoff response.

## 46. Known Limitations

Keysets do not snapshot changing data; ngram/Boolean search is not semantic,
one-character or translated search; target MySQL 8 optimizer behavior is not
measured; broad common-term search has a high local p95; rate limits are
per process. There is no exact count or relevance sort by design.

## 47. Initial Production Blockers (Historical)

Separate MySQL 8 and isolated migration verification; common-term search
latency at release-scale data; distributed abuse controls; private production
object storage; unresolved full npm audit Tailwind 3 advisories; Docker/NGINX
runtime and production browser/operations verification. None are waived by
the successful localhost tests.

## 48. Initial Final Verdict (Historical; superseded by Section 51)

**Phase 11B backend implementation and runnable local regression: PASS.**
**All mandatory verification gates / ready for independent final audit: NO**
because the separate-database migration cycle and target MySQL 8 runtime are
environment blocked, and common-term search needs a release performance
decision. **Production ready: NO.** Do not stage/commit/push or start the next
phase without a separate human instruction.

The initial MySQL 8, separate-database migration, and performance-release
blockers are resolved for the tested Phase 11B scope below. Production remains
not ready.

## 49. Blocker Resolution Gate (2026-10-18)

This section supersedes the initial MySQL 8, isolated-migration, and search
performance status in Sections 20, 21, 47, and 48. It preserves those earlier
results as a historical record; it does not change the production-readiness
decision.

### MySQL 8 runtime and compatibility

- Exact runtime: official `mysql:8.4.11`, linux/amd64, pulled through the
  verified Docker Hub cache. The cache and official Docker Hub amd64 manifest
  digests matched (`sha256:1f8411cc085d2f2f92060fca926746cbf97f87b76c3008e9741ad62e604c4ffa`).
- Disposable container `phase11b-mysql84`, loopback-only host port `43306`,
  one `unishop_china` database, `utf8mb4` / `utf8mb4_0900_ai_ci`,
  `ngram_token_size=2`. A temporary `DATABASE_URL` used the dedicated app user;
  generated disposable credentials were not added to repository files.
- Full historical migrations upgraded through Phase 11A and Phase 11B.
  MySQL 8 accepted the ngram FULLTEXT DDL, Boolean `MATCH ... AGAINST`, the
  cursor/keyset queries, exact Decimal range comparisons, composite indexes,
  Unicode fixture queries, and cover-image projection.
- Focused browse, migration, and cursor gate after the final multilingual test
  addition: **70 passed, 0 failed**. Clean-database full backend run:
  **1,458 passed, 0 failed, 0 skipped**. A first full run while the deliberate
  migration-preservation category seed was still present had two catalog tests
  fail because those tests assert an empty category catalog; after cleaning
  only that disposable seed, the complete suite passed without a code change.
- Real loopback Uvicorn/MySQL 8 security workflow:
  `python -m scripts.audit_security_http` — **161 checks passed**; database
  preservation, synthetic record cleanup, temporary media cleanup, and
  server shutdown all reported true. This exercised root/health/database
  health, authentication, seller flows, product browse/detail, image access,
  privacy, and catalog endpoints through HTTP.
- Compatibility verdict: **verified for MySQL 8.4.11 on the tested local
  workload**. No claim is made for every MySQL 8 minor release, production
  hosting, or production traffic distribution.

### Isolated migration/data-safety cycle

Revision `b11b2c3d4e5f` follows `a10b2c3d4e5f`. It adds six B-tree browse
indexes and one ngram FULLTEXT index on `product_listings`; it adds no columns,
tables, constraints, data rewrites, or seed data. Upgrade removes no indexes;
downgrade removes exactly those seven indexes. No historical Alembic revision
was edited.

On the disposable MySQL 8 database, representative Phase 11A data was seeded
before Phase 11B: verified seller/user/profile/role, active city and category,
published/draft/paused/archived listings, and one product-image metadata row
(no object bytes). A full table-content fingerprint was identical after
upgrade, after downgrade to `a10b2c3d4e5f`, and after re-upgrade to
`b11b2c3d4e5f`. The seven indexes were respectively present, absent, and
present. The synthetic seed was deleted afterward; the disposable database
ended with zero synthetic users/categories/listings/images and six migration-
seeded cities. No development database downgrade or reset occurred.

Final MySQL 8 checks: `alembic current` and `heads` each show the single head
`b11b2c3d4e5f`; `history` shows one Phase 11A parent; `alembic check` reports
`No new upgrade operations detected.` **Migration cycle: PASS.**

### Search-performance investigation and result

The original local MySQL 9.4.0 20k baseline in Section 23 measured
`q=bamboo` at **735.055 ms p50 / 823.426 ms p95** (10 samples; the earlier
run had no explicit warmups). Later runs on that same host database ranged
roughly 0.81–1.17 s p50 and up to 1.241 s p95. Those results are retained as
the pre-resolution baseline; they are not treated as a MySQL 8 result.

On a clean MySQL 8.4.11 index, the 20,000-row base dataset plus two special
public synthetic rows had 20,002 publicly eligible synthetic listings and no
hidden synthetic listings. Query: common Boolean term `bamboo`, newest sort,
no city/category/price filters, page size 25; 2,001 matching rows, 25 returned;
three warmups, ten measured runs; one SQL SELECT per page. Immediately after
FULLTEXT cleanup, DB execute+fetch measured **22.202 ms p50 / 24.858 ms p95**
(min 20.600, max 24.858). A same-process raw FULLTEXT query was 17.964 ms p50.
A real loopback request through single-process Uvicorn measured **29.263 ms
p50 / 58.440 ms p95** (3 warmups, 10 measurements, 15,080-byte JSON response).
The latter includes the database call, route/service work, response
serialization, and loopback HTTP; serialization was not separately timed.

The generated statement remains a parameterized, bounded scalar projection:
FULLTEXT Boolean predicate, current public-visibility predicate, indexed
city/category/user/profile/seller lookups, a correlated first-position cover
image lookup, stable `published_at, public_slug` ordering, and `LIMIT 25`.
There is no OFFSET, per-request exact count, Python filtering/sorting, or
per-card ORM graph load. The MySQL 8 `EXPLAIN ANALYZE` used
`ix_product_listings_search_ngram`; it read 2,001 matching Boolean rows and
sorted row IDs for the requested order before returning 25. The plan shows a
filesort/row-ID sort, but not a full-table scan; city/category/user/profile,
seller-verification, and image lookups use indexes. The optimizer estimated
fewer matches than the actual 2,001, so distributions still matter.

The measured bottleneck is the InnoDB FULLTEXT operation, not the visibility
joins or an N+1 query: raw FULLTEXT latency tracks most of the complete query
latency, while ordinary newest/filter/keyset pages stay in low single-digit
milliseconds on the tested host. Controlled page-query counts for 1, 24, and
50 cards are each **one SELECT**.

The benchmark churn itself exposed a maintenance effect on the disposable
MySQL 8 database: after repeated synthetic insert/delete cycles,
`INFORMATION_SCHEMA.INNODB_FT_DELETED` held **96,193** deleted document IDs.
With that backlog, a repeated 20k common-term run measured **81.411 ms p50**
(raw FULLTEXT 54.550 ms; loopback HTTP 75.652 ms). On this disposable database
only, FULLTEXT-only `OPTIMIZE TABLE` reduced the deleted-ID count to zero;
the repeated query then measured 22.202 ms p50 — a **72.7%** reduction from
the tombstone-loaded run — and HTTP measured 29.263 ms p50. This confirms
deleted-document backlog as a material contributor under benchmark churn.
No production search SQL/index change was justified by the clean MySQL 8
plans. Do not run `OPTIMIZE TABLE` against production or development as an
ad-hoc fix; a production maintenance threshold/window requires operations
review. The benchmark is explicitly synthetic-write guarded and must use an
isolated disposable database for repeated runs.

### Controlled scaling and query shapes

Before each controlled size, the disposable FULLTEXT index was optimized and
the deleted-document count checked at zero. Each run used three warmups and
ten measurements. Each synthetic benchmark generated the base number shown
plus two public special rows; the distinctive selective Boolean term
`zzqxv` returned one row. Common-term `bamboo` matched approximately 10% of
the base rows. Timings are local descriptive measurements, not SLOs:

| Base rows | Common p50 / p95 (ms) | Selective p50 (ms), rows | Newest p50 (ms) | SQL/page |
|---:|---:|---:|---:|---:|
| 1,000 | 5.830 / 7.328 | 4.863, 1 | 1.856 | 1 |
| 5,000 | 8.129 / 8.734 | 3.438, 1 | 1.865 | 1 |
| 20,000 | 26.326 / 31.555 | 3.686, 1 | 1.911 | 1 |
| 50,000 | 62.616 / 78.515 | 4.875, 1 | 2.310 | 1 |

At 20k, combined keyword+city/category/price and cursor-page shapes were also
measured; first and later keyset pages remained one SELECT. The benchmark
covers newest, selective/common keyword, city, category, city+category, price
range, ascending/descending price, combined filters, and later cursors.
100k was not run; one-million-user capacity is expressly not claimed. Repeated
local samples show expected growth with the number of FULLTEXT matches, not
an N+1 or OFFSET-related jump. Ten-sample p95/p99 are nearest-rank descriptive
values and are not statistically robust capacity percentiles.

### Correctness, security, and regression

On real MySQL 8, English (`laptop`, `phone`, `book`), accented French
(`ordinateur`, `téléphone`, `livre`, `café`), Chinese (`桌子`, `手机`, `电脑`,
`手机电脑书`), Arabic (`مكتب`, `هاتف`, `حاسوب`, `كتاب`), and mixed-script
queries passed. One-character queries are intentionally rejected by the input
minimum; no semantic translation is claimed. Pagination tests verify correct
ordering, no duplicates/omissions, current-visibility rechecks, and terminal
null cursors for newest/price-ascending/price-descending sorts. Signed cursor
tampering, malformed/oversized values and query/filter/sort replay are
rejected. Differential visibility, seller eligibility, inactive catalog,
private media, SQL-shaped input, malformed request rate limiting, and
response privacy gates passed in the 70 focused tests and 161 live HTTP checks.

Final regressions: full backend **1,458 passed / 0 failed / 0 skipped** on
MySQL 8.4.11; focused browse/cursor/migration **70 passed** after the last
Unicode fixture update; MySQL 8 live Uvicorn security workflow **161 checks
passed**. On the unchanged development DB (MySQL 9.4.0), a final repeat also
passed 161 checks with preservation and cleanup true. Media consistency audit
reported `image_rows=0`, `issues=[]`, `report_only=true`.

Frontend remains unchanged by Phase 11B: 387 tests pass, TypeScript, ESLint,
and production build pass. Full `npm audit` reports seven inherited
development/build-tool findings (five high, two moderate), while
`npm audit --omit=dev` reports zero. Verified chains are Tailwind
`3.4.19 -> chokidar 3.6.0 -> braces 3.0.3` and
`tailwindcss/postcss-nested 6.2.0 -> postcss-selector-parser 6.1.4`.
Advisories: [`braces` GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
(`<=3.0.3`, stack-exhaustion DoS, high) and
[`postcss-selector-parser` GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)
(`<7.1.6`, quadratic parsing CPU exhaustion, moderate). These are inherited,
dev/build-only, and not introduced by Phase 11B; package manifests/lockfile
are unchanged. The suggested audit remediation requires major Tailwind 4;
no unsafe install or framework migration was performed.

### Current decision and limitations

**Performance release decision: ACCEPTABLE WITH DOCUMENTED LIMITATION.** The
clean target MySQL 8 query plan is indexed, page reads are bounded, and tested
common-term latency is reasonable through 50k local synthetic base rows.
FULLTEXT deleted-document backlog can materially worsen timing after heavy
update/delete churn; operations must monitor and schedule safe maintenance.
The original host MySQL 9.4 high latency was observed, and its raw FULLTEXT
path was slow, but an isolated same-version MySQL 9.4 comparison could not be
completed because the verified image layer transfer stopped progressing. No
development database maintenance was attempted. This residual host-specific
comparison is a documented limitation, not evidence of a MySQL 8 query defect.

MySQL 8 runtime and separate migration cycle blockers are resolved. Production
readiness remains **NO**: the full npm audit findings are outstanding; a
private production object-storage backend and distributed rate limiting are
not configured; browser and Docker/NGINX production runtime checks remain
environment-blocked; and no 100k/one-million-user capacity test was run.

## 50. Blocker-Resolution File Manifest

The following existing Phase 11B paths are still new/untracked relative to
HEAD; they were refined or extended during blocker resolution. No production
route, service, schema, or repository behavior changed in this resolution
pass.

| Path | State vs HEAD | Reason | Verification |
|---|---|---|---|
| `backend/scripts/benchmark_product_browse.py` | NEW | Added warm-up and p99/min/max data, separate query-shape and keyset measurements, accurate selective/common synthetic terms, visible/hidden generated counts, EXPLAIN ANALYZE, and opt-in real Uvicorn loopback latency. | MySQL 8.4.11 runs at 1k/5k/20k/50k; real HTTP keyword runs; Python compile and Ruff. |
| `backend/tests/integration/test_product_browse.py` | NEW | Added deterministic ordering assertions and an additional mixed Chinese book-term check to the Unicode search regression. | 70 focused MySQL 8.4.11 browse/migration/cursor tests pass. |
| `documentation/phases/PHASE_11B_PRODUCT_BROWSE_SEARCH_BACKEND.md` | NEW | Preserved initial findings and appended blocker-resolution evidence, performance decision, remaining production blockers, and this manifest. | Facts cross-checked against test, migration, benchmark, audit, dependency and Git outputs. |

The original 20 modified tracked Phase 11B paths and 15 new Phase 11B paths
listed in Section 44 remain the full working-tree manifest. Protected
`output/` and `tmp/` artifacts are excluded.

## 51. Current Final Verdict

**Blocker-resolution completed: YES.**
**Ready for Phase 11B Final Adversarial Audit: YES.**
**Production ready: NO.**

The target MySQL 8 runtime, isolated migration cycle with representative
pre-existing data, search root-cause investigation, local performance
decision, pagination/privacy/security regressions, backend/frontend
regressions, data/media preservation, and synthetic cleanup gates passed.
This is readiness for a separate independent audit only; it is not the final
adversarial audit itself and does not claim production readiness or
one-million-user capacity. No Phase 12 work is authorized.
