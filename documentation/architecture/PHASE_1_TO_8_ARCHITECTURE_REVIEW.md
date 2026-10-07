# UniShop China — Phase 1 through Phase 8 architecture review

Date: 2026-10-07. Scope: implemented Phase 1-8 code; architecture, business logic,
security boundaries, maintainability and regression. No Phase 9 implementation.
Branch: feature/authentication. Starting HEAD: 0a79e9bca1e2abcd51eee5c21d4f14397f2b803c.
Existing dirty Phase 8 work was inventoried before edits: 32 modified + 30 new files.
A SHA-256 inventory of 618 existing tracked/untracked source files, full OpenAPI
for three configurations and all 14 database-table fingerprints was captured first.

## 1. EXECUTIVE VERDICT

| Gate | Verdict |
|---|---|
| Architecture healthy | YES, local implemented scope |
| Business logic healthy | YES |
| Code maintainability healthy | YES; bounded debt remains |
| Security boundaries healthy | YES, local application regression; not deployment certification |
| Ready for Phase 9 | YES, separately authorized development only |
| Production ready | NO |

Seven confirmed code/document findings were fixed: Critical 0, High 0, Medium 3,
Low 4. Existing dependency findings remain unresolved: one High root advisory
(braces), one Moderate root advisory (selector parser), affecting seven dependency
nodes. Five informational/deferred categories are tracked in section 28. Severity
is not assigned to stylistic preferences or inflated by counting transitive nodes
as seven independent vulnerabilities. No current application Critical/High defect
was confirmed; this is not proof that every vulnerability is absent.

| Finding | Severity | Evidence and disposition |
|---|---|---|
| AR01: locked auth queries reused cached identity state | Medium | Six real-MySQL reproductions failed before fix, passed after; refresh/phone/reset/email current reads now refresh identities. Reproduced repository precondition, not an asserted fresh-request exploit. |
| AR02: duplicated owned-auth commit branches lacked explicit Session recovery | Medium | Three failed-commit unit cases failed before fix; shared helper now rolls back failed final commit. Savepoint semantics preserved. |
| AR03: admin queue evidence SELECT per request | Medium | Four-request query budget observed four SELECTs before, one after. Fixed bounded batch loading. |
| AR04: private cross-feature rate/text helper imports | Low | Auth/profile/seller/catalog neutral algorithms extracted without sharing domain policy. |
| AR05: route-to-route error import and route-to-storage grant orchestration | Low | Mapper extracted; authorized service issues opaque grant, with redemption recheck intact. |
| AR06: ingress core imported size constant from feature storage service | Low | Existing constants moved to common, no limit change. |
| AR07: placeholder/stale architectural/current-scope docs | Low | Replaced actual architecture placeholders; corrected README/frontend/current status with historical evidence retained. |

## 2. CURRENT ARCHITECTURE MAP

### Model established before edits

Backend: main middleware -> mounted routers -> identity/origin/rate dependencies ->
strict schemas -> explicit services -> repositories/SQLAlchemy -> MySQL. HTTP
cookies/headers belong to routes. Seller grant issuance crossed the route/storage
boundary; seller service contained owner/queue/audit queries and per-row evidence
loading. Profiles directly queried the seller badge. Auth owned-transaction helpers
were duplicated; caller-composed login/reset helpers had different semantics.
Private profile validation/rate imports and a route-to-route error import crossed
feature boundaries. This model guided the narrow changes, not a desired rewrite.

### Current request flows

```text
Backend:
HTTP -> CORS/ingress/safe errors/cache headers -> mounted API
     -> Bearer identity / peer-user limits / Origin-CSRF dependencies
     -> strict Pydantic -> domain service / locked authoritative checks
     -> repository or provider/storage adapter -> SQLAlchemy/MySQL

Frontend:
src/app/router -> page/components -> feature hook -> feature API + Zod
               -> centralized API/session Axios clients -> FastAPI
Auth state: memory-only Zustand identity/token/session-version
Server state: TanStack Query private user-scoped vs public catalog/profile keys
```

Cross-cutting: configuration, credential/code hashing, JWT/session security,
neutral text/slug/image limits, safe HTTP mapping, pre-parse boundaries, transaction
policies and logging redaction. Admin is a privileged transport surface into seller
and catalog modules, not another CRUD domain. Auth owns six tables, profiles one,
seller three, catalog three plus its write-lock table: 14 in total. See section 17.
Future product/chat/review models/services/pages are scaffolding, not mounted or
implemented features. The actual frontend uses src/app/router and src/services.

## 3. PHASE-BY-PHASE ARCHITECTURE REVIEW

| Phase | Architecture / business logic | Security / maintainability / findings |
|---|---|---|
| 1 | Shared SQLAlchemy metadata, explicit auth models and Alembic chain; UUID/FK/unique constraints. | Dedicated MySQL account, validated environment URL, pre-ping. No schema or historical migration changed here. |
| 2 | Registration service owns duplicate checks, buyer role and optional phone challenge; provider dispatch is post-transaction. | Argon2 hashing, strict privileged-field rejection, parameterized queries, unique DB authority, peer budget; safe conflicts. Registration behavior retained. |
| 3/3B | Phone service/repository plus SmsSender; durable code state and development-only fake inbox. | Attempts/expiry/replay and loopback/owner controls; raw code never persisted/logged. Locked cached reads corrected (AR01). No real Tencent delivery claim. |
| 4/4C | Login/access JWT, database identity, refresh families, CSRF cookies, logout; centralized memory-only React sessions. | Fixed claims/algorithms, current ACTIVE authority, rotation/reuse revocation and session-version fencing. AR01/AR02 harden locked refresh reads and failed commits. Stateless access lifetime residual documented. |
| 5/5E | Reset/change/email services, purpose-separated challenges, durable attempt updates and delivery activation workflows. | Atomic password/session/reset invalidation and cross-purpose/user rejection. AR01/AR02 current reads/recovery fixed; provider workflows intentionally remain separate. |
| 6 | Profile service/repository and own/public DTOs, lazy unique profile and server onboarding. | User locks/current profile reads, mass-assignment rejection, private caches; public visibility excludes incomplete/inactive users. Seller badge query moved to owning repository. |
| 6.1 | Immutable public handles and deliberate navigation/privacy policy. | No UUID compatibility alias, allowlisted redirects, private identifiers in bodies; current-read and URL privacy regressions retained. |
| 7 | Explicit PENDING -> UNDER_REVIEW -> VERIFIED/REJECTED, new retry after rejection, private adapter and transactional audit. | Eligible owner/admin checks, no self-review, three kinds, expiring/renewable draft challenge, immutable submission and audit-before-release. AR03/AR05/AR06 corrected bounded queries/coupling. |
| 8 | CityService/CategoryService, minimal admin transport, shared locked admin policy and catalog mutex. | Active assignments, retired-city history, max depth two, DB constraints, activation ordering, strict slugs/fields, audit atomicity. Neutral helpers corrected AR04; no new catalog/product behavior. |

All phases have zero unexplained regression failures. This is not a claim that
every backend workflow has a complete React form: several auth pages are placeholders.

## 4. LAYERING

Route violations fixed: direct private storage grant issuance and importing another
route's mapper. Routes still parse multipart input/cookies/headers and map DTOs;
decoding an upload is a transport/input boundary, not seller state transition logic.
Service violations fixed: seller owner/queue/badge/audit SELECT/writer logic moved
to its repository. Services deliberately retain entity construction/add/flush/delete
inside their unit of work; introducing generic CRUD would obscure invariants.
Repositories do not import API/services or perform final commits. Schema violations
fixed: private profile text validator consumed by other domains. No confirmed
frontend-authoritative security or duplicated server-state store was found.

Seller require_admin performs an early database role check for rejection before
expensive work. This is a dependency policy check, not the final authority; the
seller service independently locks/rechecks ACTIVE/current role through commit.
core/authorization intentionally uses user persistence. These are documented
application-policy boundaries, not falsely described as pure generic utilities.

## 5. BUSINESS INVARIANTS

| Invariant | Enforcing code | Regression evidence |
|---|---|---|
| Only ACTIVE users authenticate/use protected operations; JWT roles never grant authority alone | auth_service, auth dependencies, UserRepository, core/authorization, service locks | pre_phase7_security, phase_5e_integrated_auth_security, catalog_api, seller_evidence_access_security |
| Registration cannot assign roles/status/verified state | schemas/auth + registration service + unique users/roles constraints | auth_routes, pre_phase7_security privileged-field matrix |
| Passwords/codes/tokens are hashed; purposes and owners cannot cross | core/security, session_security, auth repositories and reset/email/phone services | phase_5e_integrated_auth_security; password/reset/email/phone suites |
| Refresh rotation is single-use and reuse revokes family, preserving unrelated families | refresh_session_service + token_repository | refresh_session_routes, concurrent rotation and integrated auth races |
| Owned operations recover failed commits; composed helpers cannot commit caller work | core/transactions; caller-owned login/reset helpers | transaction_boundaries (9), full auth integration and commit-failure tests |
| Locked authority reads replace stale identity-map values | locked user/profile/catalog/seller and six auth queries | auth_locked_reads (6), profile_snapshot_security, catalog stale-authority races |
| One own profile and immutable public handle | profile_repository, UserProfile constraints/listeners, common/public_handles | profile concurrency, public_handles, profile_snapshot_security |
| First onboarding needs name and active city; retired cities do not revoke prior completion | profile_service and locked CityService resolution | catalog_api and catalog_concurrency; profile_routes |
| Public profiles exclude incomplete/inactive accounts and private fields | profile_repository public join, ProfileService projection, PublicProfileResponse | profile_routes, public_handles, seller_challenge_and_public_privacy |
| Seller draft/start/upload/submit needs verified email and phone, never client flags | lock_active_user(eligible), seller service | seller_verification, seller_evidence_access_security, eligibility races |
| One non-rejected seller attempt; retry is a new attempt | service state checks; generated active_slot unique constraint | seller_verification, seller_verification_concurrency |
| Submit requires all three images and a live handwritten challenge | service require_live_challenge + evidence set | seller_challenge_and_public_privacy and seller races |
| Renewal is draft-only, removes old handwritten evidence and rejects stale upload code | seller transition/upload challenge checks | renewal/expiry/rollback/renewal race tests |
| Submitted/final evidence is immutable; current admin cannot self-review | upload/review locks and state checks | seller_verification, seller_evidence_access_security, concurrency |
| Private evidence requires actor-bound one-use grant and current owner/admin authority | service issue/read + StorageProvider + _locked_evidence | seller_evidence_access_security plus architecture_regressions owner/admin/other cases |
| Audit commits before buffered image bytes leave the service | read_evidence transaction and mapper | seller_evidence_access_security read-audit/commit failure; live owner/admin download/replay |
| Public seller badge reveals boolean only, not reason/IDs/evidence/keys | seller repository EXISTS + public DTO | seller_challenge_and_public_privacy; live minimal contract |
| Only active cities can be newly assigned; history survives retirement | locked CityService.resolve_profile_city | catalog_api and profile-city/deactivation races |
| Catalog slugs immutable, canonical and no hidden ID alias | common/catalog_slugs, schemas/catalog, explicit service allowlists | catalog_api invalid/reserved slug/mass-assignment/encoded path tests |
| Category hierarchy at most two; no self/cycle or active child under inactive parent | CategoryService + mutex + level/composite FK/checks | catalog_api raw-DB constraint cases and catalog_concurrency |
| Every admin catalog write has minimal audit in same transaction | catalog_mutation, record_change, CatalogAuditRepository | catalog_api every-operation audit failure/commit failure/reparent rollback |
| Malformed JSON/forwarded headers cannot bypass peer limits | evidence_security/catalog_security and auth ingress dependencies | pre_phase7_security, seller_evidence_access_security, catalog_api, authenticated_rate_limits |
| User input is inert data and validation never reflects secrets | strict DTOs, SQLAlchemy bind parameters, safe_validation_errors, React text | auth validation, catalog unicode/SQL-shaped text and frontend privacy tests |

Test family names denote files under backend/tests/integration or unit. Empty
future-module scaffolds do not count as implemented invariant coverage.

## 6. TRANSACTION ARCHITECTURE

Owner: public service operation. Commit locations: Session.begin contexts or
the owned-auth helper's one explicit final commit after an existing read/savepoint.
get_db never commits. Repositories flush/conditionally update; collision handling
can use savepoints without claiming the final transaction. No route commits.

Rollback: refresh/email/password-change preserve existing operation-savepoint
semantics on body rejection, but now explicitly rollback if final commit fails.
Profile/seller/catalog additionally rollback outer state on failure. This difference
is deliberate compatibility, not an accidental universal helper. Dependency cleanup
still closes/rolls back a failed request. Login/reset composition remains distinct.

Audit coupling: seller transitions and catalog writes insert metadata into their
own transaction. Evidence is read/validated into a bounded buffer under locks,
then EVIDENCE_READ commits before returning bytes; audit failure means no response
bytes, not an assertion that storage was never read. Local storage upload rollback
and replaced-file cleanup are compensations, not an impossible DB/filesystem atomic
commit. Cleanup failures emit a fixed event without key/exception payload.

Problem/fix AR02: three copied existing-transaction commit branches lacked explicit
failed-commit recovery. First attempt to reuse the full-rollback helper changed
caller fixture/savepoint semantics and was rejected by nine integration failures.
The final two-layer helper preserves both existing contracts; targeted/full suites
pass. No test was weakened to accommodate the failed refactor.

## 7. AUTHORIZATION ARCHITECTURE

| Surface | Authority and object/property policy |
|---|---|
| Public health/cities/categories | Minimal safe public projection; active catalog visibility; peer limits |
| Registration/login/recovery | Strict schemas, credential/current account checks, opaque recovery responses, scoped limits |
| /auth/me and authenticated verification/password change | Valid Bearer + current ACTIVE identity; subject derived server-side; no client account flags |
| Own profile/onboarding | Actor subject selects own profile; no body/path owner selector; locked ACTIVE recheck |
| Public profile | Canonical public handle, active/completed visibility, minimal DTO; no private joins exposed |
| Seller owner actions | Current ACTIVE + eligibility + owned attempt/state; client cannot change authority/status |
| Seller evidence read | Owner or current DB ADMIN, hidden-other 404, actor-bound one-use header grant, redemption recheck/audit |
| Seller review/queue | ACTIVE current DB ADMIN; self-review denied; no implicit role provisioning |
| Catalog admin | ACTIVE current DB ADMIN under locks through commit; strict allowlisted mutations/audit |

Authentication is not authorization. Cookie possession alone does not authorize
Bearer-only feature routes. Client-supplied roles/IDs/audit fields are forbidden.
BOLA/IDOR and role revocation/inactive-state regressions pass. UI RoleRoute and
ProtectedRoute are explicitly not security controls.

## 8. MODULE COUPLING

Static direct runtime import graph: 171 Python modules, no direct cycles; no
repository -> API/service edges. TYPE_CHECKING-only ORM annotations excluded.
Frontend static import scan: 193 TypeScript modules, no detected relative/@ static
cycles; compiler/build additionally pass. These scans are guidance, not proof
against every dynamic import, barrel edge or monkeypatch runtime path.

Reduced coupling: private profile helpers -> neutral common/API modules;
admin route -> seller error module; ingress size constant -> common; private grant
orchestration -> seller service; public badge -> seller repository-owned projection.
Profile -> catalog city policy and profile -> seller boolean query remain deliberate,
narrow cross-domain dependencies. Services do not reach into each other's transition
implementation. ORM relationships remain in the same monolith database.

## 9. SPAGHETTI-CODE REVIEW

Largest orchestration hotspots are auth dependencies/routes and email delivery
activation/reset workflows. They are verbose because distinct credential, cookie,
provider-failure and lock branches are explicit, not because they hide a universal
state machine. Existing small early returns and named policies make flows traceable.
No giant file was rewritten for a line-count metric.

Deep nesting is mostly bounded validation/provider compensations. Shared identity
limiting, text rules and owned transaction duplication were extracted; domain status
checks remain visible. Seller response mapping is now pure, not a hidden SELECT per
item. Constants retain named capacities/expiry/budgets; no new magic timeouts.
Storage compensation and commit owners are documented. No major unresolved
spaghetti area was identified as a Phase 9 architecture blocker.

## 10. DUPLICATION REVIEW

Consolidated: actual-peer/HMAC-user limiting algorithm; NFC/control normalization;
byte/pixel limits; identical owned-auth commit handling; shared seller HTTP mapper;
seller persistence queries and response loading. Domain budgets, namespaces, text
caps/control differences and catalog/seller error messages remain domain-owned.

Intentionally separate: login/reset caller composition vs public operation commits;
phone/email/reset code activation and rejection semantics; seller vs catalog audit
events/shape; city vs category lifecycle policies; public vs private frontend query
keys/contracts. Generic unification would blur security or business meaning.
No confirmed harmful duplicate frontend auth/server state was found.

## 11. ABSTRACTION REVIEW

Useful existing abstractions: provider/storage interfaces, strict DTOs, repositories,
SQLAlchemy unit of work, domain services, centralized HTTP clients and Query hooks.
New helpers contain identical mechanics only and keep policy at call sites.
No over-engineered framework existed that required removal.

Rejected: GenericRepository[T], GenericService[T], universal CRUD, WorkflowEngine,
EventBus/CQRS, aggregate framework and microservices. Current state/transactions
are local and traceable; those would obscure authority/locks and complicate a small
team. No Redis, queue or large dependency/framework migration was introduced.

## 12. AUTH DOMAIN

Structure: routes/dependencies -> auth, phone, reset/change/email, refresh/token
services -> user/role/challenge/session repositories -> MySQL; delivery adapters
are injected. Policies remain distinct (generic recovery vs authenticated mutation).
Problems: AR01 stale locked identities, AR02 repeated failed-commit branch.
Refactors: six current locking queries refresh state; three owned helpers consolidated;
shared authenticated limits. Unauthenticated registration/login/phone/reset budgets
retain their existing body/identifier-specific policies.

Access JWTs remain short-lived/stateless: refresh/logout/reset/change revoke
refresh authority, not already-issued access JWTs globally. Backend still rechecks
ACTIVE/database roles. Immediate all-access revocation/versioning is a product/
deployment decision, not silently added here. No complete production identity
provider, MFA or delivery certification is claimed.

## 13. PROFILE DOMAIN

One profile per user; immutable public handle. User-row lock serializes lazy
creation/update/completion. Required fields are checked server-side. Current city
resolution locks the catalog row; retired-city history remains visible/completed.
Public profile mapping is explicit, not raw ORM serialization.
Refactor: seller repository owns boolean badge EXISTS. Profile does not invoke
seller transition services or expose review/evidence metadata.
Cross-domain city projection/policy calls remain intentionally narrow.

## 14. SELLER VERIFICATION DOMAIN

```text
eligible owner -> PENDING draft -> three images + live challenge -> UNDER_REVIEW
                       |                                      |
                 renew draft challenge                 independent DB admin
                 remove old code image                VERIFIED or REJECTED
                                                            |
                                               REJECTED permits new draft
```

No automatic role grant/listing permission on approval. Unique non-rejected slot
and one evidence per kind support invariants independently of UI.
Storage: bounded decoded/rebuilt JPEG/PNG, private random keys, metadata stripping,
path containment/symlink defenses and actor-bound single-use grants. Only local
development adapter exists; non-development fails closed. No public bucket/CDN key.
Auditing: minimal transition/read event; audit transaction failure withholds success
and image bytes. Filesystem compensation remains explicit operational debt.

Refactors: repository query boundaries, one batch per 50-row queue, pure response
mapping, service grant issuance and separate shared mapper/neutral size constant.
Submitted/final state, lock ordering, eligibility and expiry behavior remain intact.

## 15. CATALOG DOMAIN

Cities: immutable slug; active new assignments, no destructive retirement of
existing profiles, capacity 200. Categories: roots/children max depth two, capacity
500, no self/cycles, parent-first activation/child-first deactivation.
Admin: no dashboard/role-grant API; locked ACTIVE/current DB ADMIN.
Audit: changed field names/server metadata only, coupled to successful write.
Single DB write-lock row serializes hierarchy/capacity across workers; row locks
serialize city assignment/deactivation. Raw DB composite-parent NULL case was
already corrected by the existing additive Phase 8 e8 migration, not this review.
Refactor: neutral validation/rate helper; only misleading authenticated 429 wording
corrected. No slug/status/public response schema or frontend migration needed.

## 16. FRONTEND ARCHITECTURE

Features isolate API/contracts/hooks; reusable UI components do not own security
authority. TanStack server state vs memory-only Zustand auth state remains distinct.
Private keys/cache reset and session-version guards prevent user-switch data reuse;
public city/category caches can survive logout intentionally. Requests flow through
centralized token/cookie transports, not per-page auth logic. Responses are validated
before rendering; user content is text. Seller file inputs/grants stay private memory.
No frontend refactor was necessary; all initial Phase 8 frontend work is byte-identical.
Auth UI placeholders and missing admin dashboard remain explicitly documented.
Browser runtime is not certified by unit/jsdom/build success.

## 17. DATABASE / ORM

Fourteen mapped tables, explicit FKs/unique/state checks/indexes; schemas avoid
accidental relationship serialization. Auth owns users, roles, phone/reset/email
codes and refresh records; profiles one; seller three; catalog cities/categories/
audit plus mutex. One-to-one profile uniqueness, immutable handles, seller computed
active slot and evidence-kind uniqueness are present (not hypothetical future work).

Queries: parameterized SQLAlchemy; locked entity queries refresh state; scalar
authority reads cannot reuse an ORM role object's stale attributes. Public categories
are one bounded list query, no recursive loading. Seller evidence queue is now one
batch query. Service-owned ORM add/flush operations do not introduce hidden commits.
Category response parent lookup is bounded in-memory O(n²) at n <= 500, not an SQL
N+1; dictionary optimization can wait for demonstrated workload.

Migration integrity: current/head e8f0a1b2c3d4, one linear chain of ten revisions,
alembic check no drift. Historical migrations and both existing Phase 8 revisions
are byte-identical to review start. Isolated catalog/backfill/unknown-label refusal,
challenge expiry, seller, public-handle and profile round-trips pass. No development
schema mutation/drop/reseed or new migration was needed.

## 18. CONCURRENCY

Locks: current user/role rows, profile rows, refresh/challenge rows, seller
attempt/evidence and sorted actor/owner user locks; catalog DB mutex plus row locks.
Only pre-existing pure DB whole-operation deadlock retries retained (1213, bounded).
No storage/provider call was wrapped in an automatic replay.

Repeated gate: **33 passed per run, three runs, 99 executions**, zero failures.
Files: profile_concurrency, seller_verification_concurrency, catalog_concurrency,
phase_5e_integrated_auth_security, plus the explicit concurrent-refresh node.
Includes refresh rotation/reuse, password/challenge cross-feature races, profile
creation/update/completion, challenge renewal/evidence/submission/review, catalog
hierarchy/city assignment/role revocation. Existing races in other files also ran
in the full suite. New cached-identity cases simulate DB-side change within an
isolated transaction; they are not falsely labelled six new concurrent HTTP races.

## 19. TEST ARCHITECTURE

Before: 983 backend passed, 211 frontend passed. After: 1006 and 211.
New 23: 4 architecture queue/grant, 6 locked identity, 4 budget, 9 transaction cases.
No old test removed/skipped/weakened or asserted security behavior relaxed.

Coverage strengths: real MySQL constraints/locking, negative role/object/property
matrices, audit commit/insertion failure, malformed requests, token/cross-purpose
cases, Query/session and privacy contracts. Unit mocks target commit/rejection
mechanics, supplemented by real DB workflows. Repository current-read reproductions
and query budgets failed before fixes. New ticket service cases prove authorization
and opaque output; existing route/live cases prove its end-to-end API behavior.

Fixtures: outer transaction/create_savepoint + rollback with count/user-ID guards;
race/live fixtures own exact synthetic IDs and clean only those. Final 14-table
ordered hashes are stronger than count-only guards. Limitation: some test modules
share factories/config across integration files, and historical fixtures' built-in
snapshots do not hash every row individually. Local races must run sequentially,
not parallel independent suites against the same development database. Refactoring
all fixtures or inventing tests for empty future scaffolds was unnecessary.

## 20. CODE QUALITY CHANGES

| Refactor / files | Old structure / why it mattered | New structure / preserved behavior / proof |
|---|---|---|
| Four auth repositories + auth_locked_reads | FOR UPDATE could return already-loaded stale revocation/attempt data. | populate_existing on six locked reads; same queries/locks/contract. Six red-before/green-after cases and full auth/race gates. |
| core/transactions + refresh/email/change services + transaction_boundaries | Three copied owned transaction helpers; failed final commit did not explicitly recover Session. | Shared owned helper plus separate full-rollback wrapper; caller-composed flows untouched. Nine unit cases, affected integration and full suites. |
| seller repository/service + profile service + architecture_regressions | Seller inline discovery/audit/queue/badge and hidden per-response evidence SELECT. | Domain-owned repository queries, pure DTO mapping and bounded batch. Four-row evidence SELECT budget 4 -> 1, safe fields retained; public badge/privacy and races pass. |
| api/rate_limits + auth/profile/seller/catalog dependencies | Identical peer/HMAC mechanics and private profile import; misleading catalog error. | Neutral mechanic, domain budgets/callbacks/namespaces retained; catalog wording documented. Four new cases, full malformed/forwarded/limit matrices. |
| common/plain_text + three schemas | Other domains imported private profile validator. | Same NFC/control algorithm; field caps/newlines/catalog stricter controls remain local. Existing schema/API negative tests and full suites. |
| common/evidence_limits + core ingress/storage/seller route | Core ingress imported feature adapter for constant. | Neutral unchanged 5 MiB/12M-pixel constants; sanitization/limits/security tests unchanged and passing. |
| seller routes/errors/admin route + service | Route issued private storage ticket; reviewer imported another route. | Authorized service returns opaque ticket after successful authorization transaction; redemption still rechecks. Mapper verbatim in errors. Owner/admin/other tests + live download/replay/audit gate. |
| Eight docs, including this report | Placeholders and stale scope/count/head/route wording. | Factual current architecture and evidence; old dated Phase 8 counts retained as history; full manifests and production limits. No runtime behavior change. |

API schemas/operation IDs are identical in all three configurations. Only human
catalog 429 detail changes from profile to catalog wording; no status/header/budget
or response shape changed. No dependency/schema/frontend change by this review.

## 21. BACKEND REGRESSION

**1006 passed, 0 failed, 0 skipped; one upstream StarletteDeprecationWarning**:
httpx-based TestClient is deprecated upstream. It does not indicate an application
assertion failure; migrating that compatible test client is a separate dependency
task. Baseline 983 + explicitly documented 23 new cases = 1006.
Affected focused suites passed (190 after transaction correction; 170 after shared
boundary extraction), followed by complete final regression. Python compile,
Ruff and pip check pass; pip-audit has no known findings.

## 22. FRONTEND REGRESSION

**211 passed in 15 files**. TypeScript no-emit, ESLint and production tsc/Vite build
pass. Existing Phase 8 frontend code and lockfile were not touched by this review.
326 installed package versions match lock entries, zero mismatches; npm ls is valid.
Tests are local/jsdom, not a new real-browser certification.

## 23. LIVE MYSQL

**79 checks passed** using real MySQL plus a temporary loopback Uvicorn process,
fake delivery in memory and synthetic records. Includes root/health/database,
registration/login, phone/email, profile/city/onboarding/public visibility, seller
draft/uploads/submission/private owner/admin reads/audit/review, city/category
lifecycle/audit, reset/change/logout. Real providers were not contacted.
Cleanup exact and complete; temporary server stopped.

Baseline/final counts and ordered SHA-256 digests are identical for all 14 tables:

| Table | Rows | Unchanged SHA-256 |
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

No secret/personal row data is included. Fingerprints confirm development preservation
for this run, not all future concurrent operational writes or backup recovery.

## 24. SECURITY REGRESSION

Auth/refresh/password/phone/email, current ACTIVE/database role, own-object access,
strict mass assignment, public DTO privacy, URL privacy and private cache tests pass.
Seller grants remain actor-bound, one-use, header-only on credential-free URLs.
Storage keys/file hashes/identity images/rejection/private review fields are not
public profile/catalog data. Audit failure prevents image release; stale challenge
and post-submission mutation remain rejected. Catalog role revocation/current
account and audit failure matrices pass. Real configured environment secrets were
checked against tracked/untracked source: zero occurrences; backend/.env not tracked.
Logs remain fixed safe events/metadata, not password/token/code/document values.

Control review uses [OWASP ASVS](https://owasp.org/projects/asvs) and
[OWASP API Security Top 10 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/)
as reference frameworks, not a certification:
API1/3 ownership/property DTOs; API2 auth/session/challenges; API4 bounded upload/
body/capacity/rates; API5 current DB admin; API6 durable sensitive-workflow budgets;
API7 no user-directed remote fetch in implemented workflows; API8 fail-closed config/
safe headers/remaining deployment gates; API9 explicit mounted OpenAPI inventory;
API10 controlled delivery/storage interfaces and sanitized failures. ASVS topics
reviewed include validation, authentication, sessions, authorization, files, safe
errors/logging and configuration. Deployment/network/operational controls are not
fully assessed; do not interpret local tests as ASVS level conformance.

## 25. PERFORMANCE SANITY

Admin queue evidence N+1 removed: one bounded locked SELECT for up to 50 attempts,
instead of one per response. SQL event test verifies four attempts/12 evidence rows
and identical safe fields. Category trees remain one bounded query; no recursive ORM
serialization. Public seller badge is one boolean EXISTS, not a private entity load.
No extra password hashing/token validation, unbounded table load or retry loop was
introduced. Existing bounded catalog list/capacity reads are intentional; O(n²)
in-memory parent lookup can wait for demonstrated scale (maximum 500 categories).

## 26. DEPENDENCIES

Python: pip check and pip-audit pass; no requirements/installed version change here.
Node: installed lock consistency passes (326 packages); full audit exits nonzero
for **5 High + 2 Moderate nodes**, two inherited build-graph root advisories.
Production-only npm audit exits zero. Zero production-only findings is not
permission to deploy with the unresolved build-chain blocker.

- [braces GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm):
  installed 3.0.3, affected <=3.0.3; stack-exhaustion DoS. Five High nodes:
  braces, chokidar, micromatch, fast-glob, tailwindcss.
- [postcss-selector-parser GHSA-rj75-hqrm-r3gf / CVE-2026-104844](https://github.com/advisories/GHSA-rj75-hqrm-r3gf):
  installed 6.1.4, affected <7.1.6; CPU-exhaustion complexity. Two Moderate nodes:
  postcss-selector-parser and postcss-nested; Tailwind is already in the High count.
  Patch 7.1.6 crosses the present ^6 parent contract.

Tailwind remains 3.4.19. No Tailwind 4, cross-major override, npm audit fix or major
migration. Existing verified Phase 8 source-map-js 1.2.2 patch retained byte-for-byte.
Audits used node --use-system-ca with registry.npmjs.org HTTPS and strict-ssl=true;
TLS/certificate verification was not disabled or bypassed. No install attempt or
dependency pins were needed for this architecture review.

## 27. DOCUMENTATION

Created this 31-section decision/review artifact. Updated README, CURRENT_PROJECT_STATUS,
backend/system/database architecture placeholders, frontend architecture and catalog
API. Corrected implemented Phase 8 scope, migration head, frontend routes/server-state,
UI placeholders, catalog 429 wording and current 1006-test evidence. Phase 8's original
983-test completion record and older dated security evidence remain historical, not
silently rewritten as this run's result. Remaining future-feature placeholder docs
are not claims of available marketplace behavior.

## 28. TECHNICAL DEBT

Must fix before Phase 9 development: **no confirmed unresolved application architecture
blocker**. Phase 9 is a new authorized task, not part of this review. Maintain these
constraints when adding listings: active/eligible/current authority, object ownership,
strict field allowlists, service-owned transaction and minimal public/private DTOs.

Can wait (informational):
1. Split auth dependency/router files only when a cohesive maintenance need appears;
   do not unify purpose-specific workflows by filename size.
2. Move shared test factories into scoped fixtures and broaden per-test row digests;
   retain real multi-session integration tests.
3. Bounded in-memory category parent indexing if real workload warrants it.

Production-only/deployment blockers (also informational where environment, not code severity):
4. Browser supported-runtime verification remains unverified/environment-blocked;
   prior tool environment failure is not relabelled as passed. Docker and NGINX
   commands are unavailable on this machine; configuration tests are not runtime proof.
5. Private production object storage, retention/reviewer access, distributed rate/grant
   behavior, trusted proxy/TLS/cookies, real delivery, managed secrets, monitoring,
   backup/recovery and MySQL 8 target verification require a separate release gate.

In addition, both dependency root advisories in section 26 remain explicit
production/security blockers, not accepted risk. Stateless access-token revocation
latency is an existing documented design/product choice; no credential-version
migration was silently introduced. Missing auth forms/admin UI remain future scope.

Future extraction candidates: isolated delivery/storage adapters, shared test
factories and cohesive auth HTTP dependency groups. No microservice extraction is
recommended for present complexity.

## 29. FILES CHANGED BY THIS REVIEW

**38 files: 29 existing files modified and 9 new review files.** Eight of these were
already Phase 8 work; their existing functional changes were preserved. The other
54 initial Phase 8 files are byte-identical to review start. Classification uses the
618-path pre-edit SHA-256 inventory, not merely git diff against the old committed HEAD.

| File | Review attribution | Classification | Reason |
|---|---|---|---|
| `README.md` | Modified | docs | Correct implemented scope, current migration, UI placeholders and release limits. |
| `backend/app/api/rate_limits.py` | New | refactor/security | Neutral actual-peer plus HMAC-user budget algorithm; preserve domain callbacks. |
| `backend/app/api/v1/admin/seller_verification_routes.py` | Modified | refactor | Import seller HTTP error mapping from errors, not a route module. |
| `backend/app/api/v1/auth/dependencies.py` | Modified | refactor/security | Delegate identical authenticated email/password-change budgeting. |
| `backend/app/api/v1/catalog/dependencies.py` | Modified; existing Phase 8 file | refactor/security | Use shared budget algorithm and correct misleading catalog 429 wording. |
| `backend/app/api/v1/profiles/dependencies.py` | Modified | refactor/security | Use neutral shared authenticated budgeting; preserve profile limits/errors. |
| `backend/app/api/v1/seller_verification/dependencies.py` | Modified | refactor/security | Remove private profile-helper import; preserve seller budgets/errors. |
| `backend/app/api/v1/seller_verification/errors.py` | New | refactor | Extract unchanged safe HTTP exception translation for seller/admin routes. |
| `backend/app/api/v1/seller_verification/routes.py` | Modified | refactor/security | Delegate grant issuance to authorized service; use neutral size/error modules. |
| `backend/app/common/evidence_limits.py` | New | refactor | Neutral existing byte/pixel limits shared by ingress and image storage. |
| `backend/app/common/plain_text.py` | New | refactor/security | Move existing NFC/control validation without changing field-specific policies. |
| `backend/app/core/evidence_security.py` | Modified | refactor | Remove reverse dependency on storage service for the upload byte limit. |
| `backend/app/core/transactions.py` | Modified; existing Phase 8 file | refactor/security | Consolidate identical owned transactions; recover failed commits without changing savepoint contracts. |
| `backend/app/repositories/email_verification_code_repository.py` | Modified | security | Refresh cached entity state in both locked challenge queries. |
| `backend/app/repositories/password_reset_code_repository.py` | Modified | security | Refresh cached entity state in locked reset-code query. |
| `backend/app/repositories/phone_verification_code_repository.py` | Modified | security | Refresh cached entity state in locked user/phone challenge queries. |
| `backend/app/repositories/seller_verification_repository.py` | Modified | refactor/performance | Own owner/queue/badge/audit queries; batch locked evidence for one review page. |
| `backend/app/repositories/token_repository.py` | Modified | security | Refresh cached revocation state in locked refresh-token query. |
| `backend/app/schemas/catalog.py` | Modified; existing Phase 8 file | refactor/security | Import neutral text validator, not private profile schema helper. |
| `backend/app/schemas/profile.py` | Modified; existing Phase 8 file | refactor/security | Use extracted identical shared text validator; retain profile policy. |
| `backend/app/schemas/seller_verification.py` | Modified | refactor/security | Use neutral text validator for rejection reasons. |
| `backend/app/services/email_verification_service.py` | Modified | refactor/security | Use shared owned-auth transaction with failed-commit recovery. |
| `backend/app/services/password_change_service.py` | Modified | refactor/security | Use shared owned-auth transaction with failed-commit recovery. |
| `backend/app/services/profile_service.py` | Modified; existing Phase 8 file | refactor | Delegate boolean seller badge query to seller-owned projection. |
| `backend/app/services/refresh_session_service.py` | Modified | refactor/security | Use shared owned-auth transaction; login composition remains caller-owned. |
| `backend/app/services/seller_verification_service.py` | Modified; existing Phase 8 file | refactor/security/performance | Pure response mapping, repository-owned queries/batched queue and authorized ticket issuance. |
| `backend/app/services/storage_service.py` | Modified | refactor | Import neutral byte/pixel constants; retain storage interface and sanitization. |
| `backend/tests/integration/test_architecture_regressions.py` | New | test | Four queue query-budget/response and owner/admin/other grant cases. |
| `backend/tests/integration/test_auth_locked_reads.py` | New | test/security | Six real-MySQL cached-identity current-read regressions. |
| `backend/tests/unit/test_authenticated_rate_limits.py` | New | test/security | Four actual-peer, HMAC-domain, rejection/retry and missing-secret cases. |
| `backend/tests/unit/test_transaction_boundaries.py` | New | test | Nine owned-auth commit-recovery/commit-owner cases. |
| `documentation/CURRENT_PROJECT_STATUS.md` | Modified; existing Phase 8 file | docs | Add current architecture gate; preserve earlier Phase 8/historical evidence. |
| `documentation/api/catalog-api.md` | Modified; existing Phase 8 file | docs | Document corrected domain-specific 429 detail; no contract/status/budget change. |
| `documentation/architecture/PHASE_1_TO_8_ARCHITECTURE_REVIEW.md` | New | docs | Create full 31-section evidence-backed review, invariants and both file manifests. |
| `documentation/architecture/backend-architecture.md` | Modified | docs | Replace placeholder with actual layers, ownership and transaction conventions. |
| `documentation/architecture/database-design.md` | Modified | docs | Replace placeholder with actual domain tables, constraints and migration safety. |
| `documentation/architecture/frontend-architecture.md` | Modified | docs | Correct Phase 8 routes/state and retain explicit incomplete UI/runtime limitations. |
| `documentation/architecture/system-architecture.md` | Modified | docs | Replace placeholder with verified modular-monolith/system boundaries. |

No files deleted; no frontend code/dependency file changed by this review. No
historical or Phase 8 migration changed. All new files remain untracked.

## 30. FINAL GIT STATE

HEAD remains **0a79e9bca1e2abcd51eee5c21d4f14397f2b803c**, branch
feature/authentication. Starting Phase 8: **62 files (32 modified, 30 new)**.
This review: **38 files**, eight overlap with the starting set.
Final union: **92 paths (53 tracked modified, 39 untracked), zero deleted**.
Staged: **0**. Unstaged: **53 tracked modifications**. Untracked: **39**.
git diff --check: PASS. Commit: NO. Push: NO. No staging command issued.
No reset/restore/checkout/clean was used.

Required status, short status, diff check, stat, name-status and full untracked
inventory were inspected. Git's Windows LF-to-CRLF informational warnings do not
indicate whitespace-check failures; no unrelated formatting migration was performed.

### Complete original Phase 8 manifest (pre-review)

- `backend/alembic/versions/d8e9f0a1b2c3_catalog_foundation.py` — unchanged by this review.
- `backend/alembic/versions/e8f0a1b2c3d4_catalog_parent_completeness.py` — unchanged by this review.
- `backend/app/api/v1/catalog/__init__.py` — unchanged by this review.
- `backend/app/api/v1/catalog/dependencies.py` — additionally changed by this review.
- `backend/app/api/v1/catalog/routes.py` — unchanged by this review.
- `backend/app/api/v1/profiles/routes.py` — unchanged by this review.
- `backend/app/api/v1/router.py` — unchanged by this review.
- `backend/app/common/catalog_slugs.py` — unchanged by this review.
- `backend/app/core/authorization.py` — unchanged by this review.
- `backend/app/core/catalog_security.py` — unchanged by this review.
- `backend/app/core/transactions.py` — additionally changed by this review.
- `backend/app/main.py` — unchanged by this review.
- `backend/app/models/__init__.py` — unchanged by this review.
- `backend/app/models/catalog.py` — unchanged by this review.
- `backend/app/models/profile.py` — unchanged by this review.
- `backend/app/repositories/catalog_repository.py` — unchanged by this review.
- `backend/app/schemas/catalog.py` — additionally changed by this review.
- `backend/app/schemas/profile.py` — additionally changed by this review.
- `backend/app/services/catalog_service.py` — unchanged by this review.
- `backend/app/services/profile_service.py` — additionally changed by this review.
- `backend/app/services/seller_verification_service.py` — additionally changed by this review.
- `backend/scripts/audit_public_handle_migration.py` — unchanged by this review.
- `backend/scripts/audit_security_http.py` — unchanged by this review.
- `backend/scripts/catalog_http_checks.py` — unchanged by this review.
- `backend/tests/conftest.py` — unchanged by this review.
- `backend/tests/integration/test_catalog_api.py` — unchanged by this review.
- `backend/tests/integration/test_catalog_concurrency.py` — unchanged by this review.
- `backend/tests/integration/test_pre_phase7_security.py` — unchanged by this review.
- `backend/tests/integration/test_profile_concurrency.py` — unchanged by this review.
- `backend/tests/integration/test_profile_routes.py` — unchanged by this review.
- `backend/tests/integration/test_profile_snapshot_security.py` — unchanged by this review.
- `backend/tests/integration/test_public_handles.py` — unchanged by this review.
- `backend/tests/integration/test_seller_challenge_and_public_privacy.py` — unchanged by this review.
- `backend/tests/unit/test_profile_validation.py` — unchanged by this review.
- `backend/tests/unit/test_public_handles.py` — unchanged by this review.
- `documentation/CURRENT_PROJECT_STATUS.md` — additionally changed by this review.
- `documentation/api/catalog-api.md` — additionally changed by this review.
- `documentation/api/profile-api.md` — unchanged by this review.
- `documentation/phases/PHASE_8_CITIES_CATEGORIES_ADMIN_FOUNDATION.md` — unchanged by this review.
- `frontend/package-lock.json` — unchanged by this review.
- `frontend/src/app/router.tsx` — unchanged by this review.
- `frontend/src/components/profiles/CitySelect.tsx` — unchanged by this review.
- `frontend/src/components/profiles/ProfileForm.tsx` — unchanged by this review.
- `frontend/src/features/catalog/slugs.ts` — unchanged by this review.
- `frontend/src/features/categories/api.ts` — unchanged by this review.
- `frontend/src/features/categories/hooks.ts` — unchanged by this review.
- `frontend/src/features/categories/schemas.ts` — unchanged by this review.
- `frontend/src/features/categories/types.ts` — unchanged by this review.
- `frontend/src/features/cities/api.ts` — unchanged by this review.
- `frontend/src/features/cities/hooks.ts` — unchanged by this review.
- `frontend/src/features/cities/schemas.ts` — unchanged by this review.
- `frontend/src/features/cities/types.ts` — unchanged by this review.
- `frontend/src/features/profiles/api.ts` — unchanged by this review.
- `frontend/src/features/profiles/contracts.ts` — unchanged by this review.
- `frontend/src/features/profiles/schemas.ts` — unchanged by this review.
- `frontend/src/features/profiles/types.ts` — unchanged by this review.
- `frontend/src/pages/public/CategoriesPage.tsx` — unchanged by this review.
- `frontend/src/pages/shared/OnboardingPage.tsx` — unchanged by this review.
- `frontend/tests/unit/catalog.test.tsx` — unchanged by this review.
- `frontend/tests/unit/profile-cache-security.test.ts` — unchanged by this review.
- `frontend/tests/unit/profile-contracts.test.ts` — unchanged by this review.
- `frontend/tests/unit/profile-pages.test.tsx` — unchanged by this review.

Together with section 29 this is the full 92-path changed-file union; the eight
overlapping paths are explicitly marked, not counted twice.

## 31. FINAL VERDICT

| Criterion | Verdict |
|---|---|
| Phase 1-8 architecture sound | YES |
| Business logic explicit | YES |
| Layering sound | YES |
| Transaction model sound | YES, documented owner/savepoint distinctions |
| Authorization sound | YES, authoritative backend/current DB |
| Database model sound | YES, local target/constraints/drift/isolated migration gate |
| Frontend architecture sound | YES |
| Major spaghetti code resolved | YES, no confirmed remaining Phase 9 architecture blocker |
| Over-engineering avoided | YES |
| Regression intact | YES: 1006 backend, 211 frontend, 33 x 3 race cases, 79 live checks |
| Existing data preserved | YES, 14 exact table fingerprints |
| No Phase 9 implementation introduced | YES |
| Phase 9 may begin | YES, as a separately requested task |
| Production ready | NO |

### Reproducible local gates

From backend with its existing .env and migrated development database:
```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app tests scripts alembic
.\.venv\Scripts\python.exe -m ruff check --no-cache app tests scripts alembic
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts/audit_security_http.py
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py --seller-verification --catalog
```

Repeat three times sequentially (not concurrent suites on the shared dev schema):
```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_profile_concurrency.py tests/integration/test_seller_verification_concurrency.py tests/integration/test_catalog_concurrency.py tests/integration/test_phase_5e_integrated_auth_security.py tests/integration/test_refresh_session_routes.py::test_concurrent_refresh_allows_one_rotation_then_revokes_family
```

From frontend:
```powershell
npm test -- --run
npx tsc --noEmit
npm run lint
npm run build
node --use-system-ca "C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js" audit --strict-ssl=true --registry=https://registry.npmjs.org/
node --use-system-ca "C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js" audit --omit=dev --strict-ssl=true --registry=https://registry.npmjs.org/
```

Run app locally (separate terminals, each module directory):
```powershell
# backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# frontend
npm run dev
```

UniShop China Phase 1 through Phase 8 architecture, business-logic, security, maintainability, and regression review passed. The codebase remains a clean modular monolith with explicit domain boundaries and is ready for Phase 9 Product Listings development. Production readiness is not claimed.
