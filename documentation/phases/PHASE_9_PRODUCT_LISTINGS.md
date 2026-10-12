# Phase 9 — Product Listings Core: implementation and final gate

Historical implementation/handoff evidence follows. The subsequent
[28-section final adversarial double-check](PHASE_9_FINAL_ADVERSARIAL_AUDIT.md)
supersedes the test counts, findings and final worktree inventory below: 1,191
backend tests, 274 frontend tests, 61 concurrency cases repeated three times, and
97 live checks. It records two minimal UI repairs and an unresolved inherited
full-history rollback defect; the required Phase 9-to-8 migration gate passes.
Ready to commit Phase 9: YES. Production ready: NO. No staging/commit/push.

Verified 2026-10-09 (Asia/Shanghai). Scope is local engineering evidence, not a
production release or OWASP certification. All work starts from the verified clean
Phase 1–8 baseline and stays unstaged/uncommitted.

## 1. EXECUTIVE RESULT

Phase 9 complete: **YES**. Local gate passed: **YES**. Ready for Phase 10 development:
**YES**. Production ready: **NO**. Phase 10/11 were not started.

New Phase 9 code findings: Critical 0 / High 0 / Medium 0 / Low 0 within this review.
Inherited dependency findings: 5 High and 2 Moderate vulnerable dependency nodes
from **two root build advisories**, not seven separate root vulnerabilities.
Informational: upstream TestClient deprecation, unavailable browser/container
gates, MySQL 8 deployment unverified, conservative catalog-lock throughput tradeoff.
No security exception was waived to obtain the local result.

## 2. GIT BASELINE

Branch: `feature/authentication`. Starting HEAD:
`9cd29f81acc83433f05d49bcb24a1b2555a9e2e9`.
Tracking remote `origin/feature/authentication`: same SHA, read locally without fetch.
Initial tree: clean; no user changes required preservation/reversion.
Baseline verified before edits: 1,006 backend tests, 211 frontend tests.
No applied historical migration was edited and no dependency manifest/lock changed.

## 3. ARCHITECTURE

Model: ProductListing. Service: ProductService. Repository: ProductRepository.
Routes: public products + seller-products. Frontend: four existing placeholder
pages now implemented through feature API/hooks/Zod contracts and minimal form/badge.
Services own transactions and current authority; repositories never commit.
Existing transaction and bounded InnoDB deadlock retry conventions are reused.
Seller eligibility, onboarding fields, catalog rules and JSON bounds are shared;
no generic CRUD/audit framework, process mutex, microservice, queue or Redis.

## 4. DATABASE

Revision/current/sole head: `f9a1b2c3d4e5`; down revision `e8f0a1b2c3d4`.
Alembic current, heads, history and check: PASS; no drift.
Development upgrade: PASS. Isolated upgrade/downgrade/upgrade: PASS, prior rows
preserved; listing table disappears at e8 and is empty on recreation. Isolated prior
profile/handle/seller/challenge/catalog cycles also PASS. No working DB downgrade.

One table, three RESTRICT FKs (users/cities/categories), unique public_slug, eight
checks: slug, title/description lengths, positive bounded price, CNY, condition,
status and publication consistency. Indexes: owner(updated_at,id) ordering,
city/category FK support; unique slug lookup. No speculative search/media indexes.
Actual runtime MySQL **9.4.0**, not a MySQL 8 deployment certification.

## 5. PRODUCT MODEL

Fields only: id, seller_user_id, public_slug, title, description, price, currency,
condition, status, city_id, category_id, published_at, created_at, updated_at.
Slug: opaque `item-` + 24 cryptographic random lowercase hex characters (96 bits),
stable across edits/transitions; titles never put personal content into URLs.
ORM identity cannot rename slug/transfer seller, including expired-attribute reads.
Owner is server-derived from current Bearer identity; ID/slug are not writable.

Price: strict decimal JSON string; Decimal / DECIMAL(12,2), >0 and <=9999999999.99,
at most two decimals, no floats/exponents/NaN/infinity or silent rounding.
Output always two decimals. Currency server-fixed CNY.
Condition: new/like_new/good/fair. City/category: authoritative Phase 8 FKs;
request navigation uses public catalog slugs, not IDs.
Title NFC plain text 3–120; description 10–5,000, multiline plain text.

## 6. STATE MACHINE

DRAFT: private/editable; publish or archive.
PUBLISHED: public only if currently eligible; edit, pause or archive.
PAUSED: private/editable; republish or archive.
ARCHIVED: private owner-readable, terminal and read-only.

Allowed: DRAFT -> PUBLISHED/ARCHIVED; PUBLISHED -> PAUSED/ARCHIVED;
PAUSED -> PUBLISHED/ARCHIVED. Edit never changes state or slug.
Every other transition/repeated action returns 409. No SOLD/delete/transfer.
published_at is set on first publish only, preserved on pause/republish/archive.

## 7. SELLER ELIGIBILITY

Create/edit/publish: locked current ACTIVE account, verified email/phone, actual
VERIFIED Phase 7 attempt, valid completed onboarding. PENDING/UNDER_REVIEW/REJECTED,
missing attempt/profile, invalid required profile fields or incomplete onboarding
deny these operations. BUYER role with genuine approval works; neither a role name
nor frontend/JWT claims substitute for approval. Shared profile field policy drives
locked checks and the minimal public projection.

Loss of eligibility hides public detail immediately on its next server request.
ACTIVE owner can still list/read/pause/archive. Inactive accounts cannot use owner
operations. Retired profile city does not erase historical completed onboarding;
the listing's own publication references must nevertheless be active.

## 8. OWNERSHIP / AUTHORIZATION

Create uses authenticated owner only. Read own/list scopes seller_user_id.
Update/publish requires both own row and current eligibility. Pause/archive requires
own row and ACTIVE account, not seller approval/onboarding. All five cross-owner
operations tested: generic inaccessible resource, no modification. No product admin
bypass or ownership transfer. Authenticated unqualified users receive 403 independent
of slug; qualified cross-owners/unknown resources receive the same 404.

## 9. PUBLIC PRIVACY

Public allowlist: slug/title/description/price/CNY/condition/PUBLISHED/city/category/
published_at/seller. Seller only handle/display_name/seller_verified=true.
Hidden: internal IDs, auth email/phone, account state, roles, verification/review
references, private evidence/storage metadata, auth/session fields and owner timestamps.
Unknown/DRAFT/PAUSED/ARCHIVED/ineligible/inactive catalogs all generic 404.
Owner DTOs also omit unnecessary IDs. Queries select only safe profile labels and
eligibility flags, not full auth/private evidence entities.

## 10. CITY / CATEGORY INTEGRATION

Creation/changed assignments/publication require current active rows; child requires
current active root. Root and child are allowed, no invented leaf-only policy.
Retirement retains historical FKs/owner visibility while hiding public listings.
Partial edits need not reassign unchanged retired references. Owner can repair
references, then publish if eligible. Product locks/catalog DB mutex serialize
assignment/publication against activation/reparenting. City/category vs publish
races and old REPEATABLE READ snapshots are tested.

## 11. SECURITY

BOLA/IDOR: server identity + owned row checks for every private action.
Mass assignment: six editable fields only, extra-forbid/null rejection; empty action bodies.
SQL injection: SQLAlchemy bound expressions, no client-built SQL.
XSS: plain text server storage, escaped React rendering, no raw HTML sink.
Unicode: NFC/control/surrogate/bidi rejection, tested Chinese/emoji/decomposed text.
URL privacy: opaque listing slugs/catalog slugs/handles; Bearer and bodies, no secret URLs.
Budgets: actual-peer pre-parse read180/write90 per minute; authenticated read60/write30
per user, common peer120. Malformed JSON consumes budget, Forwarded headers cannot
spoof peer. Body actual32KiB/time15s/disconnect bounds; JSON required.
All listing/error responses no-store/no-referrer; safe 401/403/404/409/422/429/503,
no SQL/driver/request-value echo. No password/token/code/evidence/description logs.
Credential scan across all 53 changed/new files reports zero runtime secret matches.

Reviewed against [OWASP API Security Top 10 2023](https://api-security.owasp.org/editions/2023/en/0x11-t10/):
API1/3 ownership/property allowlists, API2 existing auth regressions, API4/6 bounds/
budgets, API5 no admin bypass, API8 safe failures/config blockers, API9 exact inventory.
API7/10: no URL fetching/external product providers introduced. Input/encoding,
authorization, session, data protection and error controls follow the
[ASVS security verification framework](https://owasp.org/projects/asvs). This targeted
mapping is not a claim of full ASVS certification or production approval.

## 12. TRANSACTIONS

Create: user/verification/profile checks -> catalog mutex/references -> nested
slug insertion -> safe DTO -> single service commit.
Update: current authority -> own listing lock -> catalog mutex/changed references ->
allowlisted fields/flush -> DTO -> commit.
Publish: current authority -> own listing -> catalog mutex/current references ->
persisted field validation -> state/first timestamp -> flush/DTO/commit.
Pause/archive: ACTIVE user -> owned row -> state -> catalog mutex/DTO -> commit.
All exceptions rollback the unit of work. Injected post-mutation view failure leaves
original data unchanged. Eight slug retries use savepoints only for named unique
collision; other failures do not retry. Whole pure-DB operations retry existing
bounded 1213 deadlocks only. No external side effect is retried.

## 13. CONCURRENCY

13 listing cases: shared slug collision; publish/publish; publish/pause from draft
and paused; publish/archive; pause/archive; edit/archive; city/category retirement
vs publish; stale city/category/eligibility snapshots; disjoint partial edits.
All valid serialized outcomes; no impossible lifecycle, lost disjoint fields,
duplicate slug, stale authorization, or published-against-retired reference.

Three combined **35-case** race runs passed (13 listing + prior catalog/profile/
seller and refresh rotation case), in addition to targeted runs. No concurrent
suite shared a working DB test fixture; all committed race data cleaned by exact
synthetic IDs/slugs. Same-field concurrent edits remain documented last-writer-wins.

## 14. BACKEND TESTS

Baseline: **1,006**. Final: **1,170 passed**. Phase 9 targeted: **164**
(137 API/MySQL + 13 concurrency + 14 unit cases). Failures/skips: **0/0**.
Existing auth/profile/seller/catalog/architecture regressions remain green.
One unchanged upstream Starlette/httpx TestClient deprecation warning.
Python compile/import, Ruff --no-cache, pip check, pip-audit: PASS.
Ruff initially hit a corrupt package-root cache panic; --no-cache passed all files,
without source suppression, rule disabling, cache deletion or package changes.
Early CHECK tests corrected to assert MySQL 3819 OperationalError; historical API/
frontend inventories were updated only for the authorized new routes/pagination.

## 15. FRONTEND

Baseline 211; final **267 passed in 18 files**, 56 new Phase 9 cases.
TypeScript: PASS (tsc -b). ESLint: PASS. Production Vite build: PASS.
Actual hidden loopback Vite startup: PASS; root and four SPA paths returned 200;
served API client receives configured VITE_API_BASE_URL. Test server stopped.
This HTTP/module check does not execute the app in a real browser.
Four pages, catalog-driven form, bounded own collection/all lifecycle states,
escaped public detail, immutable archive, strict schema/URL validation and safe errors.
Owner identity + session-version private keys; logout clears cache, account switch
cannot restore old drafts, late owner API responses are rejected. Public failed
refetch hides earlier visible data rather than rendering stale hidden listings.
No tokens/drafts in localStorage/sessionStorage. React/jsdom tests are not browser QA.

## 16. LIVE MYSQL / HTTP

**97 checks PASS** through real loopback Uvicorn/MySQL, including registration,
phone/email verification, profile/onboarding, actual Phase 7 evidence/review approval,
catalog/admin, password reset/change, sessions/logout, and Phase 9 lifecycle.
Draft -> edit -> hidden404 -> publish -> public200 -> pause404 -> republish ->
archive404 -> terminal409. Cross-owner read/edit denied; public seller contract minimal.
Exact synthetic cleanup PASS; owned products removed before owned users/catalogs;
temporary private evidence directory cleaned; server stopped.
All 14 pre-existing table counts/ordered SHA-256 digests unchanged; new listing table
empty after tests/live/races. No real user/category/city deletion or reset/reseed.

## 17. PERFORMANCE

Owner list executes one bounded listing query with joined city/category/parent,
plus fixed auth/current-user/catalog-lock overhead. No per-item seller/catalog query
and no count query; limit+1 yields next_offset. Stable updated_at DESC,id DESC order.
Public detail has one joined visibility query/EXISTS predicate, no evidence query.
Known concerns: catalog mutex contention across owner reads/writes at scale,
offset pagination has bounded but increasing scan cost and can move under concurrent
edits. No premature Redis/cache/search architecture; benchmark for intended scale.

## 18. OPENAPI

Local **53**, all-fake development **57**, production-config schema **51**.
Exactly eight new operations in each; all earlier path/operation and component schema
contracts unchanged. Duplicate operation IDs 0. Product paths have only strict opaque
slug parameters; bounded limit/offset only for own collection. Internal-ID product
routes 0; image/storage/feed/search/admin-product/deal/chat routes 0.
Production schema generation is not deployment/runtime proof.

## 19. DEPENDENCIES

No dependency or version-pin changes. pip check PASS; pip-audit 0 advisories.
326 actually installed frontend package versions match package-lock; package/root
dependencies and devDependencies consistent. Tailwind **3.4.19**, braces **3.0.3**,
postcss-selector-parser **6.1.4** installed and verified.

Full npm audit: exit1, **5 High / 2 Moderate nodes**, unresolved inherited blockers.
Root advisories:
- braces **GHSA-vfj7-8cjw-p6xm**, stack-exhaustion DoS via deep patterns, affects
  <=3.0.3; inherited via Tailwind 3 -> chokidar/micromatch and fast-glob.
- postcss-selector-parser **GHSA-rj75-hqrm-r3gf**, quadratic flat-selector CPU
  exhaustion, affects <7.1.6; inherited via postcss-nested/Tailwind 3.

Affected nodes are braces/chokidar/fast-glob/micromatch/tailwind (High) and
postcss-nested/postcss-selector-parser (Moderate). Separate dependency migration task;
no force-fix, TLS bypass, insecure registry, or unverified pin. npm audit --omit=dev:
exit0, **zero vulnerabilities**. Audits used node --use-system-ca with normal HTTPS
verification; no npm install was needed, no Tailwind 4 migration performed.

## 20. BROWSER

**ENVIRONMENT BLOCKED**, not PASS. Required browser:control-in-app-browser skill
connection failed before runtime setup because its tool environment omitted sandboxPolicy.
No unsupported browser/Playwright fallback. jsdom unit tests/build and live API gate
do not certify rendered browser behavior.

Pending manual browser checklist: sign-in/refresh routes, create draft with actual
catalogs, own list and all actions, terminal archive, anonymous public visible/hidden
states, failed/stale eligibility actions, escaped Unicode/HTML-shaped text, invalid
slugs/no private URLs, logout/account-switch cache, mobile controls/focus/accessibility.

## 21. DOCKER / NGINX

**ENVIRONMENT BLOCKED**: docker/nginx commands unavailable, no runtime PASS claimed.
Static inspection: /api/ proxy preserves new listing endpoints, / forwards SPA
navigation to existing Vite frontend; same-origin/public routes require no special
UUID route. Existing Dockerfile/Compose remain development tooling, not a hardened
production static build/TLS deployment. No infrastructure rewrite in this phase.

## 22. CLEAN-CODE REVIEW

Routes stay thin (63 lines for all eight handlers); service owns lifecycle/authority,
repository handles parameters/joins/locks/collisions. Explicit DTOs/writable field
allowlist; shared eligibility/catalog/onboarding/body rules prevent policy duplication.
Unused future media/search/admin-product placeholders remain unmounted.
No generic base repository, new global framework, duplicated auth client, or
speculative fields. Broad exception catching is limited to safe outer HTTP boundaries
and synthetic audit tooling; domain failures propagate and rollback. No intentional
layer violations. Model/service unit-of-work persistence follows existing architecture.

## 23. DOCUMENTATION

Created: this report and product-api.md. Updated: root/backend/frontend READMEs,
CURRENT_PROJECT_STATUS, backend/frontend architecture, database-design.
Earlier dated phase evidence is historical and preserved, not relabeled as Phase 9.
Run from backend, configured local .env/MySQL:
`.\\.venv\\Scripts\\python.exe -m alembic upgrade head`,
`.\\.venv\\Scripts\\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers`.
From frontend: `npm.cmd run dev -- --host 127.0.0.1`; VITE_API_BASE_URL must target
the configured backend /api/v1 and CORS must allow the actual frontend origin.
Tests: `python -m pytest -q`; `npm.cmd test -- --run`.
Disposable cycle: `python scripts/audit_public_handle_migration.py --products --catalog --seller-verification`.
Synthetic live gate: `python scripts/audit_security_http.py`.

## 24. PRODUCTION BLOCKERS

- Both inherited Tailwind 3 build advisories remain unresolved security blockers.
- Private production object storage, reviewer access and evidence retention/deletion/
  operational audit retention/export require configuration and validation.
- Shared/distributed rate limiting and private one-time grant/session coordination
  for multi-worker deployment are not configured.
- Trusted proxy topology, HTTPS/cookie/CORS/security headers/certificates need
  deployment verification; local dev reverse proxy/build are not proof.
- Managed secrets/rotation, restricted production DB/runtime grants and actual
  delivery providers require deployment-specific configuration/validation.
- Monitoring/alerting, retention, tested backup restoration/disaster recovery pending.
- Browser and Docker/NGINX runtime verification are environment-blocked.
- Target MySQL 8/platform compatibility unverified; local tests use MySQL 9.4.0.
- Human review of unstaged migration/code and coordinated frontend/backend deployment.
- Listing mutex/pagination throughput requires scale-specific validation.
No release waiver; production readiness **NO** independent of local functional PASS.
Images/feed are intentionally absent, not broken Phase 9 functionality.

## 25. FILES CHANGED

**53 total: 39 modified tracked / 14 new / 0 deleted**, attributable to Phase 9.
No .env, package/lock, historical migration, private upload, or generated build/test
artifact is in the changed-file manifest.

| Status | File | Reason |
|---|---|---|
| New | `backend/alembic/versions/f9a1b2c3d4e5_product_listings.py` | Add only listing table, frozen checks, indexes and RESTRICT FKs. |
| New | `backend/app/api/v1/products/dependencies.py` | Reuse Bearer identity/HMAC budgets and map safe domain/transport errors. |
| Modified | `backend/app/api/v1/products/routes.py` | Implement eight thin listing endpoints with strict contracts. |
| Modified | `backend/app/api/v1/router.py` | Mount public and owner listing routers only. |
| New | `backend/app/common/product_slugs.py` | Generate and validate opaque immutable 96-bit listing references. |
| Modified | `backend/app/core/authorization.py` | Expose current locked approved-seller authorization, separate from draft-review eligibility. |
| Modified | `backend/app/core/catalog_security.py` | Reuse bounded JSON reader without changing Phase 8 ingress budgets. |
| New | `backend/app/core/http_input.py` | Share actual-byte/time/disconnect bounds across catalog/listing ingress. |
| New | `backend/app/core/product_security.py` | Limit malformed requests before JSON parsing and reject oversized/encoded inputs. |
| Modified | `backend/app/main.py` | Install listing ingress boundary and no-store headers. |
| Modified | `backend/app/models/__init__.py` | Register listing metadata for runtime/Alembic. |
| Modified | `backend/app/models/product.py` | Implement listing-only model, enums, invariants and immutable ORM identity. |
| Modified | `backend/app/repositories/catalog_repository.py` | Add current category-by-ID lookup for parent checks. |
| Modified | `backend/app/repositories/product_repository.py` | Bound joined reads, scope ownership and retry only unique-slug collisions. |
| Modified | `backend/app/repositories/seller_verification_repository.py` | Share approved-attempt EXISTS predicate without changing prior badge behavior. |
| Modified | `backend/app/schemas/product.py` | Strict create/PATCH contracts, decimal-string prices and safe DTOs. |
| Modified | `backend/app/services/catalog_service.py` | Reuse active city/category/parent policy for listings. |
| Modified | `backend/app/services/product_service.py` | Own listing transactions, current eligibility, BOLA, state transitions and visibility. |
| Modified | `backend/app/services/profile_service.py` | Expose shared completed-onboarding rules for locked/minimal public projections. |
| Modified | `backend/README.md` | Replace stale starter guidance with verified backend commands and gate tooling. |
| Modified | `backend/scripts/audit_public_handle_migration.py` | Extend disposable migration harness with listing round trip and preservation. |
| Modified | `backend/scripts/audit_security_http.py` | Extend synthetic live workflow and exact cleanup/fingerprints to listings. |
| New | `backend/scripts/product_http_checks.py` | Exercise real HTTP draft/edit/publish/pause/republish/archive and privacy/BOLA. |
| Modified | `backend/tests/conftest.py` | Track listing table in rollback/preservation assertions. |
| New | `backend/tests/integration/test_product_concurrency.py` | Add 13 independent MySQL race/current-read regressions with exact cleanup. |
| New | `backend/tests/integration/test_product_listings.py` | Add 137 real MySQL API, security, lifecycle, privacy, bounds and rollback cases. |
| New | `backend/tests/unit/test_product_contracts.py` | Add 14 pure contract/slug/input-bound cases. |
| Modified | `backend/tests/unit/test_public_handles.py` | Extend existing inventory guard only for approved slug routes and bounded owner pagination. |
| New | `documentation/api/product-api.md` | Document every listing endpoint, request/response and security/lifecycle rule. |
| Modified | `documentation/architecture/backend-architecture.md` | Describe listing responsibility/lock ordering and conservative mutex tradeoff. |
| Modified | `documentation/architecture/database-design.md` | Document additive listing table, new head and preservation. |
| Modified | `documentation/architecture/frontend-architecture.md` | Document listing routes, private caches, strict contracts and request-time visibility. |
| Modified | `documentation/CURRENT_PROJECT_STATUS.md` | Prepend current Phase 9 results; preserve historical phase evidence. |
| New | `documentation/phases/PHASE_9_PRODUCT_LISTINGS.md` | Persist complete 27-section gate, evidence and every changed-file reason. |
| Modified | `frontend/README.md` | Document frontend commands, four listing routes and retained release blockers. |
| Modified | `frontend/src/app/router.tsx` | Mount exactly four listing pages; owner cleanup routes bypass ProfileGate. |
| Modified | `frontend/src/components/layout/AuthenticatedLayout.tsx` | Add listing links and responsive wrapped navigation. |
| Modified | `frontend/src/components/products/ProductForm.tsx` | Accessible catalog-driven plain-text/decimal form, partial patches and immutable archive UX. |
| Modified | `frontend/src/components/products/ProductStatusBadge.tsx` | Render only supported listing state. |
| Modified | `frontend/src/features/products/api.ts` | Reuse centralized client, strict runtime DTOs, version fences and safe errors. |
| Modified | `frontend/src/features/products/hooks.ts` | Identity/session-scoped private queries and fenced lifecycle mutations. |
| Modified | `frontend/src/features/products/schemas.ts` | Runtime validate editable inputs and separate public/private response contracts. |
| Modified | `frontend/src/features/products/types.ts` | Derive minimal listing types from runtime contracts. |
| Modified | `frontend/src/pages/public/ProductDetailsPage.tsx` | Minimal escaped public detail; hide stale data after failed refetch. |
| Modified | `frontend/src/pages/seller/AddProductPage.tsx` | Implement create-draft page with eligibility guidance. |
| Modified | `frontend/src/pages/seller/EditProductPage.tsx` | Implement owner lifecycle controls and archived read-only detail. |
| Modified | `frontend/src/pages/seller/SellerProductsPage.tsx` | Implement bounded owner collection with all states and safe slug links. |
| Modified | `frontend/src/routes/routePaths.ts` | Allow only exact listing routes; retain query/fragment/credential rejection. |
| Modified | `frontend/tests/unit/development-route.test.tsx` | Update historical route inventory for four approved Phase 9 routes. |
| New | `frontend/tests/unit/product-contracts.test.ts` | Add 41 price/input/privacy/slug/URL/error contract cases. |
| New | `frontend/tests/unit/product-pages.test.tsx` | Add nine form, pagination, lifecycle, XSS, catalog and stale-public UI cases. |
| New | `frontend/tests/unit/product-session-security.test.ts` | Add six identity/session/cache/late-response security cases. |
| Modified | `README.md` | Describe Phase 9 scope, routes, migration head and release boundaries. |

## 26. FINAL GIT STATE

HEAD `9cd29f81acc83433f05d49bcb24a1b2555a9e2e9`, unchanged.
Staged 0; unstaged tracked 39; untracked 14; deleted 0.
git diff --check: PASS, including final doc/manifest verification.
Commit created: **NO**. Push performed: **NO**. No staging/reset/restore/clean commands.
Real .env and dependency files remain unchanged; runtime secrets never printed.

## 27. FINAL VERDICT

Product domain, ownership, lifecycle, seller authority, catalog integration, exact
prices, public privacy, concurrency, architecture and regression: **YES** within
the documented local gate. Existing data preserved: **YES**. URL privacy: **YES**.
No Phase 10 code introduced: **YES**. No Phase 11 code introduced: **YES**.
Phase 10 development may begin: **YES**, separately requested. Production ready: **NO**.

Follow-up completion check (2026-10-09): reran the full backend suite (1,170 passed,
one unchanged upstream warning), full frontend suite (267 passed), TypeScript,
ESLint, production build, Python compile, Ruff --no-cache, pip check and pip-audit:
all PASS. Fresh npm audits reproduce the two inherited build advisories above;
production-only audit remains clean. Alembic current/sole head remains
`f9a1b2c3d4e5`; history and no-drift check PASS. All 15 table counts and ordered
fingerprints match immediately before/after this rerun; product_listings remains
empty. The 53-file manifest matches the worktree, staged files remain zero and
HEAD is unchanged. The earlier isolated migration, 97-check live workflow and
three repeated concurrency gates were not separately rerun in this follow-up.
No application, dependency, credential or deployment change was needed; browser
and container runtime blockers remain unresolved.

### Safe data fingerprint evidence

Digests match pre-edit baseline for the first 14 tables; product_listings is the
intentional new empty table. Alembic version changes intentionally and is not an
application-data fingerprint. Hashes contain no row values or credentials.

| Table | Final rows | Ordered SHA-256 |
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

UniShop China Phase 9 Product Listings Core passed its local implementation, architecture, business-logic, security, regression, concurrency, and data-integrity gate. Phase 10 Product Images and Storage development may begin. Production readiness is not claimed.
