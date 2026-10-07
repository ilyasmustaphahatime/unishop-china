# Phase 8 — Cities, Categories and Minimal Admin Foundation

Verified 2026-10-07 (Asia/Shanghai). Scope: Phase 8 only. Results below are observed
local evidence, not production certification. No staging, commit or push.

## 1. EXECUTIVE RESULT

Phase 8 implementation complete: **YES**. Local Phase 8 gate passed: **YES**.
Ready for Phase 9 development: **YES**. Production ready: **NO**.

Findings, counting root issues rather than npm's transitive dependency nodes:

- Critical: 0.
- High: 1 unresolved pre-existing build dependency root advisory (braces);
  1 additional inherited dependency issue resolved (source-map-js).
- Medium: 1 unresolved inherited build dependency root advisory
  (postcss-selector-parser); 1 Phase 8 database defense-in-depth issue resolved.
- Low: 0 unresolved Phase 8 findings; 1 selector-state defect resolved.
- Informational: 3 verification/tooling observations: browser unavailable,
  Docker/NGINX runtime unavailable, third-party TestClient deprecation warning.

No unresolved Critical/High/Medium issue introduced by Phase 8 was found in the
tested implementation. This is a bounded review, not a claim that no vulnerabilities
can exist. Full npm audit is **not clean**: its remaining build-graph advisories are
explicit production blockers, not waived or described as PASS. Local functional,
security regression, migration, concurrency and preservation checks passed.
Existing production/environment exclusions remain separate.

## 2. GIT BASELINE

Branch: `feature/authentication`.
Starting HEAD: `0a79e9bca1e2abcd51eee5c21d4f14397f2b803c`.
Starting subject: `fix: complete phase 7 seller verification security hardening`.
Remote: `origin`, https://github.com/ilyasmustaphahatime/unishop-china.git.
Initial working tree: clean. Local origin tracking ref equals starting HEAD.
A fresh remote advertisement was not established; do not infer a fresh remote sync.
Existing Phase 1–7 work was retained; only necessary integration/helpers changed.

## 3. ARCHITECTURE

City model: internal UUID/timestamps, immutable unique public slug, English/Chinese
names and province labels, China-only country code, activation and bounded ordering.
Category model: internal UUID/timestamps, globally unique slug, English/Chinese
names, optional description, parent reference, activation and bounded ordering.
Profile relation: nullable indexed `city_id` FK with RESTRICT deletion; legacy
`city` text remains a historical/backout label, not runtime authority.

Service structure: explicit CityService and CategoryService own rules and whole
transactions. Repository structure: CityRepository, CategoryRepository and
CatalogAuditRepository own reusable queries/locks. Routes validate and delegate.
Admin foundation: backend endpoints only, using existing bearer authentication and
current locked DB roles; no full admin UI and no privilege provisioning endpoint.
Audit model: internal AdminCatalogAudit coupled to mutations, not public responses.
A singleton database CatalogWriteLock serializes infrequent, bounded catalog writes
across workers. It is deliberately not a generic CRUD framework or in-memory lock.

## 4. DATABASE MIGRATION

New revisions: `d8e9f0a1b2c3` and `e8f0a1b2c3d4`.
Down revisions: `c7d8e9f0a1b2` and `d8e9f0a1b2c3`, respectively.
Alembic sole head/current: **e8f0a1b2c3d4**.
Development upgrade: PASS. Isolated downgrade: PASS. Upgrade-after-downgrade:
PASS. Alembic history inspected; `alembic check`: no new upgrade operations.

The first revision creates four catalog tables, seeds six deterministic cities
once, preflights unknown legacy labels **before MySQL's auto-committing DDL**, adds
the profile FK and backfills by exact known display label. It refuses unknown
values without guessing or printing row data. Original columns/rows are preserved.
The second revision follows a reproduced red test for nullable composite parent
keys: SQL CHECK accepted UNKNOWN and MySQL skipped a partially-null FK. An explicit
parent-completeness check now closes that gap. The applied first revision was not
rewritten to conceal this fix.

Existing profile preservation: verified with three isolated historical profiles
(two with city labels), exact label retention and unknown-label refusal before any
catalog table is created. Development has no pre-existing profile rows, so nonempty
backfill evidence comes from this isolated test, not a vacuous development claim.
Phase 6, Phase 7 and challenge-expiry downgrade/upgrade cycles also passed in the
disposable instance. No development downgrade, reset or truncate was performed.
Downgrade is a test/backout tool, not a safe automatic eraser of new catalog data;
it refuses legacy-incompatible city labels. Back up and review before any real
deployment/backout. Runtime tested here is **MySQL 9.4.0**, not a MySQL 8 certification.

## 5. CITIES

Seeded cities: Qingdao/青岛 (Shandong), Beijing/北京, Shanghai/上海,
Shenzhen/深圳 and Guangzhou/广州 (Guangdong), Hangzhou/杭州 (Zhejiang).
Slug policy: immutable lowercase ASCII, 2–63 chars, letter first, single-hyphen
segments, reserved names rejected. DB binary-collated unique constraint prevents
collisions; canonical API validation rejects uppercase/encoded/unsafe aliases.

Public API: GET `/api/v1/cities` and `/api/v1/cities/{slug}`, active rows only.
Admin API: list/create/metadata patch/activate/deactivate under `/api/v1/admin/cities`.
Activation behavior: explicit action, no hard-delete endpoint. Capacity 200 total
rows including inactive. Profile assignments resolve active current state under a
row lock. Retired cities remain displayable on existing profiles; new assignments
are rejected, including an explicit attempt to reassign the same inactive slug.
Display labels come from the referenced catalog; admin renames therefore update
display without rewriting every profile or changing its stable slug/reference.

## 6. CATEGORIES

Hierarchy model: relational parent plus composite FK to `(id, level)`.
Max depth: two (root and child). Cycle/self-parent/depth prevention: service checks,
database level/check constraints, complete parent keys, RESTRICT composite FK and
serialized graph mutations. A node with children cannot become a child.
Slug uniqueness: global within categories, binary unique index, immutable through API.

Public API: active two-level tree plus detail by slug; children of inactive parents
are hidden defensively. Admin API: flat list including inactive, create, metadata
update/reparent, activate and deactivate. Activation behavior: activate parent
first; deactivate active children first. Invalid transitions are rejected, never
silently cascaded. Capacity 500 total rows. Categories intentionally start empty.
No listing/category assignment or product functionality was introduced.

## 7. PROFILE / ONBOARDING

Old behavior: six hardcoded display labels accepted by application/DB/frontend.
New behavior: server-managed FK authority; PATCH field `city` carries a public slug
or null. Backfill preserves known historical labels exactly; unknown labels stop
migration safely. Own response retains display `city` and adds `city_slug` and
`city_active`; public response still exposes only its minimal display contract.

Compatibility: the write payload intentionally changes from `"Qingdao"` to
`"qingdao"`. Deploy client and API together; there is no silent legacy fallback.
The frontend uses the shared dynamic CitySelect for edit/onboarding with loading,
safe error/retry, empty and retired-city states. A controlled value fixes the
initial async-options historical-selection defect. Metadata-only edits omit
unchanged city assignment. First completion needs an active city; deactivation
does not undo completed onboarding. Clearing a required field still invalidates it.
Data preserved: YES, confirmed by development fingerprints and isolated backfill.

## 8. ADMIN AUTHORIZATION

Authentication: existing validated Bearer subject, not ambient cookies or body IDs.
ACTIVE check: current user row locked in the service transaction.
DB role authority: current ADMIN membership reloaded/locked, not client flags or
stale JWT role claims. Revoked role behavior: 403 before reads/writes; suspended,
banned, deleted/missing accounts rejected. Tests cover these states for both domains.
Mass-assignment protection: strict schemas and explicit persistence allowlists;
IDs, role/status, actor, timestamp, audit and activation fields cannot be supplied
through metadata bodies. No role grants, synthetic admin or credentials remain.

## 9. AUDIT LOGGING

City actions: CREATED, UPDATED, ACTIVATED, DEACTIVATED.
Category actions: CREATED, UPDATED, REPARENTED, ACTIVATED, DEACTIVATED.
Every successful action, including repeated explicit activation requests, records
server-derived actor/action/resource slug/type/time and changed field **names**.
No raw bodies, field values, credentials or private documents are audit payloads.

Transactional coupling: one service-owned transaction; mutation and audit flush
and commit together. Audit-failure rollback: tested for each action, reparenting,
insert failure and commit failure; no success response or half-applied data.
Audit table is internal and has no public endpoint. Actor FK retains the event if
an actor is eventually deleted. Operational audit retention/export remains a
production decision, not an added background system.

## 10. SECURITY

| Risk reviewed | Enforcement/evidence |
|---|---|
| BOLA/IDOR and function authorization | Own-profile subject derived from bearer; catalog admin DB checks; normal/cookie-only/revoked/inactive users denied |
| Mass assignment / property leakage | Strict bodies, persistence allowlists and explicit minimal response DTOs; frontend rejects leaked fields |
| SQL injection | Parameterized SQLAlchemy/repository queries; SQL-shaped text is inert data |
| Unsafe Unicode / XSS | Bounded plain text, control/bidi/format checks; React text rendering; no HTML interpretation |
| Slug traversal/collision | Shared canonical validators, reserved names, percent-path refusal and DB unique indexes |
| Rates / malformed JSON | Peer budgets before parsing; actual-byte 16 KiB/15-second bounds; malformed-body exhaustion tests |
| Stale state / revoked privilege | Current locking reads bypass earlier authentication snapshots; same transaction owns authority and mutation |
| Cache bleed | Public catalog keys separate from private authenticated cache; logout/account-switch regression retained |
| Audit failure / migration corruption | Transaction rollback fault injection and isolated unknown-label/round-trip tests |
| URL privacy | Only public slugs/handles navigate; no new internal UUID or secret query/path parameters |
| Error/log safety | Fixed 404/409/422/503 responses; submitted values, SQL, traces and secrets not reflected/logged |

Public peer budget: 180/minute. Admin pre-parse peer budget: 90/minute; authenticated
user budget: 30/minute plus 90/peer/minute. Forwarded headers cannot pick the peer.
All are bounded process-local structures; a shared limiter remains a production blocker.
Private no-store, CORS/origin/referrer, JWT/session/CSRF and seller evidence controls
remain intact. Seller challenge expiry/renewal, badge privacy and audit-before-bytes
tests pass; evidence credentials remain header-only and audit failure prevents bytes.

Review follows least privilege, current authorization and response allowlisting
principles in the [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
and [API3 property-level authorization guidance](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).
This is not formal OWASP/ASVS certification.

Repository/diff and the most recent eight commits were scanned for actual local
secret values (read only in memory, never output) and high-confidence key patterns:
no match. Scope is bounded; this is not an exhaustive all-history entropy scan.
No real .env, credentials, private evidence or generated test artifacts are in the
changed-file manifest. All server-side text remains untrusted even after validation.

## 11. CONCURRENCY

Eight real-MySQL multi-session cases: duplicate city and category creation;
city deactivation versus profile assignment; opposing reparent attempts; parent
deactivation versus child creation; disjoint admin metadata updates; concurrent
activation/deactivation for each domain.

Runs: complete eight-case suite passed **three consecutive times** (24 executions).
An additional 17-case race/audit-rollback selection passed three times (51 executions).
Failures: zero in final runs. Unique/FK/active-state/audit checks passed.
Deadlock handling: shared existing policy retries only a whole rolled-back InnoDB
1213 transaction, at most three attempts, including wrapped savepoint-cleanup causes.
No arbitrary error/timeout retry or external side-effect retry. Catalog order is
actor -> role -> singleton -> resource; profile assignments lock user/profile/city.
Finite stress testing supports the design; it is not a proof of all possible schedules.

## 12. BACKEND TESTS

Full count: **983 passed**, zero failed/skipped (baseline 883).
Phase 8 targeted count: **100** (92 API/security + 8 concurrency).
Additional final selections: 144 catalog/seller/challenge cases passed; 246
profile/auth/session/URL/evidence/security cases passed. All baseline tests remain
in the suite; fixtures/contracts changed only for the intentional relational city API.
Python compile/import, Ruff, pip check and pip-audit: PASS.
Warning: one third-party Starlette TestClient/httpx deprecation; no suppression.

Reproduction from `backend` (activate `.venv` first):

```powershell
python -m pytest -q --tb=line
python -m pytest tests/integration/test_catalog_api.py tests/integration/test_catalog_concurrency.py -q
1..3 | ForEach-Object { python -m pytest tests/integration/test_catalog_concurrency.py -q }
python -m compileall -q app tests scripts alembic
python -m ruff check --no-cache app tests scripts alembic
python -m pip check
python -m pip_audit --progress-spinner off
python -m alembic current
python -m alembic heads
python -m alembic history
python -m alembic check
python scripts/audit_public_handle_migration.py --seller-verification --catalog
python scripts/audit_security_http.py
```

Run mutation/integration suites sequentially against this development database,
not simultaneous suites that compete with each other's preservation fixtures.

## 13. FRONTEND TESTS

Full count: **211 passed** in 15 files (baseline 187).
TypeScript: PASS. ESLint: PASS. Production Vite build: PASS.
Frontend contract tests: 24 new cases cover strict public shapes, API calls, invalid
slugs, hierarchy consistency, private-field rejection, dynamic/loading/error/empty/
historical city behavior, inert category rendering and public/private cache separation.
Existing onboarding/profile/logout/account-switch/URL regressions also pass.
Full frontend checks reran successfully **after** the verified source-map patch.

```powershell
npm test -- --run
.\node_modules\.bin\tsc.cmd -b --pretty false
npm run lint
npm run build
npm audit
npm audit --omit=dev
```

The last two commands have distinct results: full audit retains blockers; omit-dev
is clean. Use trusted system CAs if required locally, never disable TLS validation.
For local UI/API startup: from backend run
`python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`;
from frontend run `npm run dev -- --host 127.0.0.1`.

## 14. LIVE MYSQL / HTTP

Checks: **79**, including 15 new catalog checks and the complete earlier live
authentication/profile/seller workflow. Result: PASS on real MySQL 9.4.0 and loopback
Uvicorn, not mocks. Synthetic cleanup: PASS; owned exact rows/temporary evidence
removed, temporary server stopped. Real SMS/email not sent; local fake delivery used.
Data preservation: PASS. Final integrity checks: zero profile-city or category-parent
orphans, invalid hierarchy rows or active-child/inactive-parent combinations.

All ten original table hashes/counts equal the pre-migration baseline. All fourteen
table hashes equal the post-migration baseline after testing. The six city rows and
singleton lock are intentional migration additions. Roles are stored in user_roles,
not a separate roles table.

| Table | Final count | Final SHA-256 aggregate fingerprint |
|---|---:|---|
| users | 4 | `891bef3bf220acafe1b66fb708a89bfaf3c92ee2f1d2da384d3b37d6fade2a9d` |
| user_roles | 4 | `be38e6e535ea4f631251e5cbe9903b8090db6f1d4d3d5e19d2bb23d11c83fa26` |
| phone_verification_codes | 3 | `c0c2eaa4a03ddbcbe06d79bbd19f754aa9fe0e0424b577ce34a1924eec694344` |
| refresh_tokens | 7 | `e72016e35f65c47878e515f531ad671eeb3a29a6b69dea942fa430dd6411c2bc` |
| password_reset_codes | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| email_verification_codes | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| user_profiles | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| seller_verifications | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| seller_evidence | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| seller_verification_audit | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| cities | 6 | `34aa919e3c4ce4ec79d3fd15aa19c1673eb5ed415bb9e0d01ee4f522b4825e50` |
| categories | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| admin_catalog_audit | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| catalog_write_lock | 1 | `e28610836ab702cd35495751839961e9fae54fec4ee18dc4b314862c18c3d104` |

Aggregate fingerprints contain no row values or PII. Nonempty profile/category
scenarios were exercised synthetically and cleaned up; final zero rows are expected.

## 15. OPENAPI

Operation count: **45 local**, **49 with all development inbox routes**, **43
production-config schema-only**. Duplicate operation IDs: zero in each variant.
Four public and ten admin catalog operations added. Internal ID exposure: no new
public/internal-ID navigation; strict response allowlists; admin routes authenticated.
Phase 9 routes present: **NO**. Existing seller private request contracts are retained.
Production schema generation is not production deployment/runtime verification.

## 16. DEPENDENCIES

pip check: PASS. pip-audit: no known vulnerabilities. Verified installed Python
versions include PyJWT 2.15.1, urllib3 2.8.0, SQLAlchemy 2.0.51, FastAPI 0.139.2 and
PyMySQL 1.2.0. No Python dependency change was needed in this phase.

Fresh npm audit initially found 8 nodes (6 High, 2 Moderate). A narrow compatible
`source-map-js` patch **1.2.1 -> 1.2.2** resolved
[GHSA-68fv-2mgg-jv7q / CVE-2026-93749](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
Both parents permit ^1.2.1, and the lock diff changes only this package's version,
HTTPS URL and integrity. package.json unchanged. Installation succeeded with
`node --use-system-ca`, normal HTTPS and `--strict-ssl=true`, not a certificate bypass.

Lock/root declarations and all **326 installed package versions** matched; absent
optional platform packages are not counted as installed. Tailwind remains 3.4.19;
braces 3.0.3; Axios 1.20.0; brace-expansion 5.0.12; Undici 7.29.1.
Full tests/typecheck/lint/build/audits reran after installation.

Final npm audit: **NON-CLEAN, 5 High + 2 Moderate nodes**, two root advisories:

- **braces 3.0.3**, [GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm):
  affected <=3.0.3, no patched braces version listed; recursive-pattern stack
  exhaustion, CWE-674. npm CVSS 3.1 score 7.5; GitHub CVSS 4 score 8.7. Propagates
  through chokidar, micromatch, fast-glob and tailwindcss: five High graph nodes,
  not five independent vulnerabilities.
- **postcss-selector-parser 6.1.4**,
  [GHSA-rj75-hqrm-r3gf / CVE-2026-104844](https://github.com/advisories/GHSA-rj75-hqrm-r3gf):
  affected <7.1.6, patched 7.1.6, quadratic selector parsing, CVSS 5.9. Also affects
  postcss-nested; tailwindcss already counted High. Existing parents require ^6.x;
  forcing 7.x is a cross-major override, not the compatible patch used above.
  Newly identified in this audit but already present in the unchanged baseline
  build graph. Advisory reachability requires parsing untrusted selectors; this
  app does not accept user CSS for its build. Still retained as a production blocker.

npm audit --omit=dev: **0 findings**, exit 0. Full audit remains exit 1.
No Tailwind 4 migration, force-fix, insecure registry, TLS bypass or unverified pin.
Resolve the remaining Tailwind build graph in a separate reviewed dependency task.

## 17. BROWSER

**ENVIRONMENT BLOCKED**. The browser skill was used to attempt the required supported
browser connection, but it failed before any tab/session was available. Therefore
no fresh real-browser profile/edit/onboarding/category/address-bar/back-forward
PASS is claimed. Component/DOM tests and live HTTP checks are separate evidence,
not a substitute for browser runtime verification. No standalone browser bypass.

## 18. DOCKER / NGINX

**ENVIRONMENT BLOCKED**. Docker and nginx commands were unavailable; the standard
Docker Desktop CLI path was absent. No image build, container startup or nginx
runtime test is claimed. Static review and existing Docker-context/security tests
passed. NGINX remains an API/frontend proxy, not a new private-file/source alias;
backend .dockerignore excludes secrets, environments, logs and private uploads.
No unrelated infrastructure rewrites were made.

## 19. CLEAN-CODE REVIEW

Duplicate logic found: transaction/admin authorization would otherwise repeat
existing seller/profile behavior. Refactors performed: shared transaction/deadlock
policy and current-role/user checks; one catalog slug validator per language; reused
plain-text validation, rate-limit helper, audit writer and CitySelect.
No copied generic CRUD framework or new cache infrastructure.

Largest new functions reviewed: service methods at most 13 physical lines; route
handlers 3 lines; ASGI boundary 41; explicit migration upgrade 66; live catalog
workflow 26. The longer boundary/migration procedures have one clear responsibility.
Routes contain no direct SQL. React handles presentation/form orchestration, never
authoritative eligibility/activation/hierarchy decisions. No multiple commit owners.
Broad catches are confined to rollback/rethrow or sanitized API boundaries and are
commented; no silent success on error. Public category tree uses one SQL query,
city list one query, with deterministic ordering and relevant indexes.

Remaining maintainability concerns: API write-contract deployment coordination;
bounded singleton-write throughput is appropriate for reference data but must be
revisited if catalogs become high-volume; public query cache can be stale for 60s,
so server validation is mandatory. Some existing annotations/style are intentionally
retained rather than widening this phase into a repository rewrite.

## 20. DOCUMENTATION

Files updated/added: this report, CURRENT_PROJECT_STATUS.md, api/profile-api.md and
api/catalog-api.md. Accuracy: current schemas, two-revision chain, inactive semantics,
limits, endpoints, tests, fingerprints and actual dependency results documented.
Historical status evidence is explicitly labeled, not rewritten as current.
Known limitations: production dependencies/operations and browser/container gaps
below. Phase 9 is only a next authorized development phase, not implemented here.

## 21. FILES CHANGED

**62 files: 32 modified, 30 new, 0 deleted.** Every path is relative to the
project root. New files remain untracked; existing modifications remain unstaged.

- `backend/alembic/versions/d8e9f0a1b2c3_catalog_foundation.py` — Add catalogs/audit/mutex, deterministic city seeds and guarded profile backfill.
- `backend/alembic/versions/e8f0a1b2c3d4_catalog_parent_completeness.py` — Close the composite-parent SQL NULL constraint loophole additively.
- `backend/app/api/v1/catalog/__init__.py` — Define the catalog API package.
- `backend/app/api/v1/catalog/dependencies.py` — Reuse authentication/rate controls and sanitize catalog operation failures.
- `backend/app/api/v1/catalog/routes.py` — Expose 14 thin public/admin catalog operations.
- `backend/app/api/v1/profiles/routes.py` — Translate inactive/unknown city failures into a safe 422.
- `backend/app/api/v1/router.py` — Mount public and administrator catalog routers.
- `backend/app/common/catalog_slugs.py` — Centralize canonical catalog slug validation and reserved-name policy.
- `backend/app/core/authorization.py` — Share locked ACTIVE-account and current DB ADMIN-role checks.
- `backend/app/core/catalog_security.py` — Limit peer requests before parsing and bound actual body bytes/time.
- `backend/app/core/transactions.py` — Share transaction ownership and bounded InnoDB deadlock retry.
- `backend/app/main.py` — Install the pre-parse catalog request boundary.
- `backend/app/models/__init__.py` — Register catalog metadata for SQLAlchemy/Alembic.
- `backend/app/models/catalog.py` — Define City, Category, AdminCatalogAudit and CatalogWriteLock constraints.
- `backend/app/models/profile.py` — Replace the hardcoded allowlist with an indexed city FK; preserve the historical label.
- `backend/app/repositories/catalog_repository.py` — Centralize parameterized catalog reads, locks and minimal audit inserts.
- `backend/app/schemas/catalog.py` — Strict request allowlists and minimal public/admin DTOs.
- `backend/app/schemas/profile.py` — Accept city slugs and expose own-profile city_slug/city_active.
- `backend/app/services/catalog_service.py` — Explicit city/category business rules, hierarchy locks and atomic audit writes.
- `backend/app/services/profile_service.py` — Resolve active cities transactionally and preserve retired-city/onboarding semantics.
- `backend/app/services/seller_verification_service.py` — Reuse extracted transaction/admin helpers without changing seller behavior.
- `backend/scripts/audit_public_handle_migration.py` — Exercise isolated catalog migration/backfill/refusal/round-trip and preserve older data.
- `backend/scripts/audit_security_http.py` — Add catalog checks and snapshot/cleanup coverage for all 14 tables.
- `backend/scripts/catalog_http_checks.py` — Add reusable live catalog workflow and exact synthetic cleanup.
- `backend/tests/conftest.py` — Reset catalog limiters to keep cases isolated.
- `backend/tests/integration/test_catalog_api.py` — Add 92 API/security/constraint/audit/profile regression cases.
- `backend/tests/integration/test_catalog_concurrency.py` — Add eight real-MySQL multi-session race cases.
- `backend/tests/integration/test_pre_phase7_security.py` — Adapt strict own-profile contracts and valid city-reference fixtures.
- `backend/tests/integration/test_profile_concurrency.py` — Preserve existing concurrency tests using slug writes and real city references.
- `backend/tests/integration/test_profile_routes.py` — Update profile write payloads to the canonical city-slug contract.
- `backend/tests/integration/test_profile_snapshot_security.py` — Update fixtures without weakening stale-snapshot regressions.
- `backend/tests/integration/test_public_handles.py` — Retain URL/privacy assertions with valid relational city fixtures.
- `backend/tests/integration/test_seller_challenge_and_public_privacy.py` — Supply the city FK required by existing seller badge fixtures.
- `backend/tests/unit/test_profile_validation.py` — Use a canonical slug in the existing text-validation case.
- `backend/tests/unit/test_public_handles.py` — Explicitly allow catalog slug paths/admin operations in OpenAPI privacy checks.
- `documentation/CURRENT_PROJECT_STATUS.md` — Publish current Phase 8 evidence and distinguish dated historical claims.
- `documentation/api/catalog-api.md` — Document endpoints, strict fields, limits, hierarchy, audits and operation.
- `documentation/api/profile-api.md` — Document the intentional city write-contract change and retirement semantics.
- `documentation/phases/PHASE_8_CITIES_CATEGORIES_ADMIN_FOUNDATION.md` — Record the complete 24-section gate, evidence, limitations and changed-file manifest.
- `frontend/package-lock.json` — Narrow compatible security patch: source-map-js 1.2.1 to 1.2.2 only.
- `frontend/src/app/router.tsx` — Add the read-only /categories route.
- `frontend/src/components/profiles/CitySelect.tsx` — Shared controlled dynamic selector with loading/error/empty/historical states.
- `frontend/src/components/profiles/ProfileForm.tsx` — Use the dynamic selector and omit unchanged historical city assignments.
- `frontend/src/features/catalog/slugs.ts` — Share frontend canonical slug validation across catalogs/profile forms.
- `frontend/src/features/categories/api.ts` — Fetch and validate public category data.
- `frontend/src/features/categories/hooks.ts` — Provide a public category query key and bounded retry/stale policy.
- `frontend/src/features/categories/schemas.ts` — Reject private/unknown fields and invalid/duplicate/deep hierarchy contracts.
- `frontend/src/features/categories/types.ts` — Derive category types from runtime schemas.
- `frontend/src/features/cities/api.ts` — Fetch and validate public city data.
- `frontend/src/features/cities/hooks.ts` — Provide a public city query key and bounded retry/stale policy.
- `frontend/src/features/cities/schemas.ts` — Define strict bounded public city response contracts.
- `frontend/src/features/cities/types.ts` — Derive city types from runtime schemas.
- `frontend/src/features/profiles/api.ts` — Map new own-profile city metadata.
- `frontend/src/features/profiles/contracts.ts` — Validate display city, slug and activation metadata separately.
- `frontend/src/features/profiles/schemas.ts` — Validate slug form values instead of a six-city enum.
- `frontend/src/features/profiles/types.ts` — Remove the hardcoded city authority and add citySlug/cityActive.
- `frontend/src/pages/public/CategoriesPage.tsx` — Render a safe read-only two-level directory.
- `frontend/src/pages/shared/OnboardingPage.tsx` — Use server-managed city selection and active-city onboarding state.
- `frontend/tests/unit/catalog.test.tsx` — Add 24 catalog contract, selector, rendering and cache-boundary cases.
- `frontend/tests/unit/profile-cache-security.test.ts` — Adapt fixtures while preserving private-cache isolation assertions.
- `frontend/tests/unit/profile-contracts.test.ts` — Cover the expanded own-profile city contract.
- `frontend/tests/unit/profile-pages.test.tsx` — Adapt profile/onboarding tests to dynamic catalog queries.

## 22. PRODUCTION BLOCKERS

- Unresolved Tailwind 3/braces High and inherited selector-parser Moderate build
  advisories; separate migration/remediation task, not accepted risk.
- Private production object storage, reviewer access, evidence retention/deletion
  and operational audit retention/export need deployment-specific validation.
- Shared/distributed rate limiter and private one-time grant/session coordination
  appropriate to multi-worker deployment remain unconfigured.
- Trusted proxy topology, HTTPS/cookies/CORS/security headers and certificate
  validation require final deployment certification; development proxies are not proof.
- Managed secrets/rotation, restricted production DB/runtime permissions and real
  notification provider configuration/validation remain operational requirements.
- Monitoring/alerting, backup restoration/disaster recovery and retention validation.
- Fresh real-browser regression environment unavailable.
- Docker/NGINX runtime verification unavailable.
- Target production MySQL-version/platform validation: local evidence is MySQL 9.4.0.
- Human review of unstaged migrations/code and coordinated frontend/backend deployment.

Production ready remains **NO**, independent of the local Phase 8 PASS.

## 23. FINAL GIT STATE

HEAD: `0a79e9bca1e2abcd51eee5c21d4f14397f2b803c`, unchanged.
Staged: **0**. Unstaged tracked modifications: **32**. Untracked new files: **30**.
Deleted: **0**. `git diff --check`: PASS. No private data/test artifacts in manifest.
Real backend/frontend .env files are ignored, untracked and unchanged.
Commit created: **NO**. Push performed: **NO**.

Final inspection commands: git status; git status --short; git diff --check;
git --no-pager diff --stat; git --no-pager diff --name-status;
git ls-files --others --exclude-standard. The full manifest above includes new
files omitted by ordinary git diff --stat.

## 24. FINAL VERDICT

Cities foundation complete: YES. Categories foundation complete: YES.
Profile migration safe: YES. Admin authorization sound: YES.
Audit integrity sound: YES. Concurrency safe within reviewed design/test scope: YES.
URL privacy intact: YES. Phase 1–7 regression intact: YES.
Existing data preserved: YES. No Phase 9 code introduced: YES.
Code maintainability acceptable: YES. Phase 9 may begin: YES.
Production readiness: NO; unresolved blockers remain explicit.

UniShop China Phase 8 Cities, Categories, and Minimal Admin Foundation passed its local implementation, regression, security, clean-code, concurrency, and data-integrity gate. Phase 9 Product Listings development may begin. Production readiness is not claimed.

