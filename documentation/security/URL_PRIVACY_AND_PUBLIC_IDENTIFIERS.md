# Phase 6.1 — URL Privacy & Public Identifier Hardening

Phase 7 update (2026-09-25): the implementation adds a narrowly scoped, authenticated,
one-use signed evidence-download URL. It is never application navigation or a public share link;
normal responses omit evidence URLs and internal IDs. See the
[Phase 7 URL-privacy exception and controls](../phases/PHASE_7_SELLER_VERIFICATION.md).
Operation/test counts and the no-Phase-7 statements below record the earlier Phase 6.1 audit.

Audit date: 2026-09-11. Scope: existing Phase 1–6 functionality and URL privacy only.
This is a development gate, not production certification.

## 1. EXECUTIVE RESULT

Phase 6.1 complete: YES, subject to the explicitly environment-blocked fresh browser check.
Ready for separately authorized Phase 7 development: YES. Migration required: YES.

Findings resolved: Critical 0, High 0, Medium 3, Low 2.
Open Critical/High/Medium/Low URL-privacy findings: 0.
Informational limitations: 4 (browser availability, MySQL version, existing placeholder UIs,
and the existing third-party test warning).

| ID | Severity | Finding and evidence | Resolution |
|---|---|---|---|
| URL-001 | Low | Public profile UUID was carried in API/browser paths. It was already a distinct public UUID, not a secret or internal row ID; this was a mismatch with the new navigation policy. | Stable public handles, strict lookup, removed UUID routes and response field. |
| URL-002 | Medium | Fake-SMS/reset lookups carried phone/email in query strings; fake inbox consumption carried private message references in paths. Local-only access did not prevent URL/history/access-log exposure. | POST JSON bodies; existing loopback, production exclusion, email ownership and no-store controls preserved. |
| URL-003 | Low | Post-login return-path helper accepted arbitrary same-origin paths, query strings and fragments. It could propagate caller-supplied sensitive URL state. | Existing-route allowlist plus validated public handles; query/hash never forwarded. |
| URL-004 | Medium | Forced simultaneous handle collisions exposed missing-profile SELECT FOR UPDATE gap-lock deadlocks across different owners. Removing that read subsequently exposed stale REPEATABLE READ snapshots. | Final double-check restored the current locking read with populate_existing and bounded whole-transaction deadlock retry. Owning-user serialization, unique constraints and separate bounded handle-collision retries remain. See the final audit below. |
| URL-005 | Medium | npm audit reported Vitest/@vitest/mocker development-tool arbitrary-file-read advisory. | Targeted Vitest 4.1.10 -> 4.1.11 patch; matching Vitest packages and tinyrainbow transitive patch only. Both final npm audits are clean. |

Vitest advisory: [GHSA-82fw-gwwq-j7x9](https://github.com/advisories/GHSA-82fw-gwwq-j7x9).
The vulnerable standalone mocker has specific development-server exposure prerequisites;
this is not a demonstrated production application compromise.

## 2. PRE-FLIGHT

- Branch: `feature/authentication`.
- HEAD: `2fb4b63f1280959b2204f147d1f8f901325f4c0b`.
- Commit: `fix: harden pre-phase-7 security boundaries`.
- Remote tracking and fresh remote branch lookup: same commit.
- Initial tree: clean; nothing staged.
- Executed status, short status, status -sb, rev-parse, branch, five-commit log,
  diff --check, fsck --full and remote lookup before edits. All passed.
- Baseline schema revision: `f6a1b2c3d4e5`; development profiles: 0.

## 3. ROUTE INVENTORY

API paths below use `/api/v1` unless explicitly root-level.
No active application operation now declares a query parameter.
The only dynamic application path parameter is the intentionally public `handle`.

| Route / source | Identifier or secret | Public/private | In URL? | Risk / action |
|---|---|---|---|---|
| GET / (root), GET /health (root), GET /health, GET /health/database | None | Public health | No | Unchanged safe health responses. |
| POST /auth/register | Email, phone, password | Private | No; JSON body | Preserve existing validation/rate limits. |
| POST /auth/login | Account identifier, password | Private | No; JSON body | Preserve existing login and memory-only access token handling. |
| GET /auth/me | Principal and access JWT | Private | No; Authorization header | No identifier path/query. |
| POST /auth/refresh | Refresh and CSRF tokens | Private | No; cookie/header | Existing rotation/CSRF protections unchanged. |
| POST /auth/logout | Refresh and CSRF tokens | Private | No; cookie/header | Existing revocation unchanged. |
| POST /auth/logout-all | Access JWT | Private | No; Authorization header | Existing server authority unchanged. |
| POST /auth/phone/resend-code | Phone | Private | No; JSON body | Existing durable and peer limits unchanged. |
| POST /auth/phone/verify | Phone and OTP | Private | No; JSON body | Existing challenge checks unchanged. |
| POST /auth/password/forgot | Account identifier | Private | No; JSON body | Generic response unchanged. |
| POST /auth/password/reset | Identifier, reset code, new password | Private | No; JSON body | No reset URL credential. |
| POST /auth/password/change | Current/new password, access JWT | Private | No; JSON body/header | No authentication redesign. |
| POST /auth/email/resend-code | Authenticated principal | Private | No; header, empty JSON | Ownership retained. |
| POST /auth/email/verify | Code, access JWT | Private | No; JSON/header | Ownership retained. |
| GET /profile/me | Authenticated owner | Private | No; bearer principal | Own profile only. |
| PATCH /profile/me | Editable public text; authenticated owner | Mixed | No; JSON/header | Strict allowlist; cannot submit a target owner or handle. |
| POST /profile/onboarding/complete | Authenticated owner | Private | No; empty JSON/header | Server-derived completion. |
| GET /profiles/by-handle/{handle} | Public handle | Public | Yes | Strict parsing, public-read only, same hidden-state 404. |
| POST /dev/fake-sms/latest | Phone | Private/local development | No; JSON body | Former query lookup removed. |
| POST /dev/fake-sms/consume | Message reference | Private/local development | No; JSON body | Former identifier path removed. |
| POST /dev/fake-password-reset/latest | Email/phone identifier | Private/local development | No; JSON body | Former query lookup removed. |
| POST /dev/fake-password-reset/consume | Message reference | Private/local development | No; JSON body | Former identifier path removed. |
| GET /dev/fake-email/latest | Authenticated principal | Private/local development | No; bearer principal | Rejects query strings; owner-derived lookup. |
| POST /dev/fake-email/consume | Message reference and owner | Private/local development | No; JSON/header | Owner remains authenticated principal. |

The first row contains four operations; total with all fake inboxes enabled is 27.
Current local configuration mounts 23. Non-development application operations total 21.
OpenAPI JSON and the framework documentation pages describe these operations; they add
no application credential query/path parameter.

Frontend route inventory:

| Routes | State / URL treatment |
|---|---|
| /, /safety, /terms, /privacy | Static public navigation. |
| /u/:handle | Only dynamic frontend route; shareable public handle. |
| /login | Credentials submitted to fixed login API path, not navigation. |
| /sign-up, /verify-phone, /forgot-password, /reset-password | Existing placeholder pages; no query/hash credential consumption or new UI implementation. |
| /profile, /profile/edit, /onboarding | Authenticated server state; no user/profile ID in path. |
| /dev/phone-verification | Development/flag-gated; form values stay in component memory and request bodies. |
| * | Safe not-found; old /users/:publicId is not registered or redirected. |

Redirect/source classification:

- LoginForm / routePaths: allowlisted destination or validated public handle only.
- ProtectedRoute / GuestRoute: fixed login/profile navigation; return state kept in memory.
- ProfileGate / ProfileForm / OnboardingPage: fixed onboarding/profile paths; success flag in navigation state.
- AuthActions: fixed /login after logout; no session value in URL.
- MainLayout / AuthLayout / AuthenticatedLayout / ProfilePage: fixed navigation links or publicProfilePath(handle).
- Profile API/hooks: handle in public GET URL and public cache key; authenticated user ID in private memory cache key only.
- localFakeSmsApi: former URL parameters now JSON; no params option remains.
- No URLSearchParams, useSearchParams, location.search/hash credential reader, analytics
  SDK or frontend error-reporting URL sink is present in active source.
- Existing backend logging records only safe database-check exception type/code.
  Uvicorn/proxy access logs may record requested URLs: prevention at URL construction
  is the policy, not an assumption that logs redact secrets. Arbitrary attacker/manual
  URLs can still reach an access logger; the application must never generate them.

## 4. PUBLIC HANDLE DESIGN

Field: `user_profiles.public_handle`; no authentication schema field added.
Allowed format: `^[a-z0-9][a-z0-9_-]{1,28}[a-z0-9]$`.
Length: 3–30. ASCII only. ASCII uppercase input lowercases before lookup/model storage.
Whitespace is rejected, not trimmed. Unicode, controls, bidi characters, dot segments,
percent signs, slash/backslash, query/fragment delimiters and leading/trailing separators
are rejected. Percent-encoded public lookup paths are not a fallback.

Exact reserved list:

`about, account, admin, api, assets, auth, categories, chat, cities, dev, help,
login, logout, messages, notifications, products, profile, profiles, register,
search, seller, sellers, settings, static, support, users`.

Generation: `user-` plus `secrets.token_hex(10)` (80 random bits, 25 characters total).
The neutral prefix deliberately avoids derivation from display name, email, phone,
database ID, password or HMAC data. The generator accepts no identity argument.
Unique database constraint/index is authoritative; allocation retries at most eight
handle collisions inside savepoints without discarding other work. Other integrity
errors are not retried as collisions.

Handles cannot be submitted through profile update/onboarding APIs or renamed through
model assignment. No rename feature or alias exists. Database administrators can still
change rows directly; immutability is enforced by current application interfaces, not
a database trigger. The database enforces NOT NULL, uniqueness, lowercase shape and
reserved-name exclusion.

Public handles are intentionally discoverable. They are not secrets or bearer credentials.

## 5. DATABASE / MIGRATION

Revision: `a61b2c3d4e5f`, parent `f6a1b2c3d4e5`.
Adds nullable handle, independently backfills every existing profile, then applies
NOT NULL, unique constraint/index and a format/reserved-name CHECK.
Legacy `public_id`, primary/foreign keys and every authentication column remain intact.

Run during a maintenance window with application writers stopped. MySQL DDL is not
fully transactional; take normal operational backups before production migrations.
Do not use offline SQL generation for this data-dependent backfill.

Verification:

- Isolated local MySQL 9.4 instance: old schema -> seed three synthetic profiles
  (absent, ASCII and Unicode display names) -> upgrade -> downgrade -> upgrade again.
- All original user/profile fields preserved across the cycle.
- Three non-null distinct neutral handles backfilled; Alembic check: no drift.
- Temporary server stopped and generated directory cleaned; first helper run's Windows
  shutdown cleanup issue was repaired and its leftover temporary directory removed.
- Development database upgrade: PASS. No development downgrade was run.
- Current revision/head: `a61b2c3d4e5f`, exactly one head; no drift.
- MySQL account privileges were not expanded. Isolated testing used a separate temporary
  server because the application account cannot create another database on the real server.
- Runtime credentials were generated in memory and never printed or committed.

Downgrade removes only this phase's handle column/constraints. It preserves original
profiles/authentication rows, but discards handles; a later upgrade assigns fresh handles.
Therefore downgrade is only tested in isolation and is not a stable-link rollback policy.

## 6. API CHANGES

Old: `GET /api/v1/profiles/{public_id}` — removed, no redirect or fallback.
New: `GET /api/v1/profiles/by-handle/{handle}`.

Public response is exactly:

`public_handle, display_name, bio, city, member_since, email_verified, phone_verified`.

Own-profile response also contains onboarding_completed, created_at and updated_at.
Neither profile response exposes legacy public_id, internal user/profile IDs, email,
phone, roles, account status or private verification/session state.
The authenticated /auth/me identity contract remains unchanged and is never a navigation identifier.

Development routes use the body-based contracts in section 3. Missing/malformed fields
return sanitized errors. Email consumption still derives the owner from authentication.

## 7. FRONTEND CHANGES

Canonical link: `/u/:handle`. Removed: `/users/:publicId`.
Profile page now links to its public handle; API parsing/types and public cache keys
use publicHandle. No compatibility redirect publishes a UUID.
Only current fixed navigation routes and validated public handles are accepted for
post-login destinations. Object location query/hash are discarded; string destinations
containing them are rejected. Invalid fallbacks resolve to /.

Direct public-route mount and fresh remount are tested without private state.
Unknown and hidden profiles have the same safe unavailable view. Existing escaped-text
rendering, session generation guards and private-cache cleanup remain intact.

Browser address-bar automation: ENVIRONMENT BLOCKED, not PASS. Bootstrap failed before
creating a browser tab due to missing sandboxPolicy metadata. No screenshot/address-bar
or historical manual result is represented as a fresh verification.

## 8. SECRET-IN-URL AUDIT

| Value | Result | Evidence / intended channel |
|---|---|---|
| JWT access token | PASS | Authorization header; memory-only frontend state. |
| Refresh token | PASS | HttpOnly cookie, no route interpolation. |
| CSRF token | PASS | Cookie/header, not URL. |
| OTP / phone verification code | PASS | JSON body; local inbox JSON response only. |
| Email verification code | PASS | JSON body; authenticated fake inbox response only. |
| Password-reset code | PASS | Fixed reset API path + JSON body. |
| Password | PASS | Fixed authentication paths + JSON body. |
| Internal user/profile IDs | PASS | No public navigation route or public lookup fallback. |
| Private media reference | PASS / no implementation | Future policy below; no Phase 7 media functionality added. |
| Phone/email lookup and private fake-message references | PASS | Development lookup/consume now uses JSON bodies. |

PASS means verified current source, contracts, automated tests and exercised HTTP flows;
it does not claim that an arbitrary manually pasted malicious URL cannot exist.
The app does not implement analytics/crash-reporting hooks that export navigation URLs.

Referrer-Policy is `no-referrer` in frontend HTML and API/proxy responses.
Proxy configuration was inspected, not tested in a running nginx deployment.

## 9. AUTHORIZATION / BOLA

Knowledge of a handle grants only intended public read access.
Own writes use the authenticated principal, authoritative ACTIVE account state and
the owning-user lock. Handles, user IDs or profile IDs in update/onboarding bodies
are rejected by strict field allowlists. Public write methods are not mounted.

ACTIVE + completed profiles are visible. Unknown, incomplete, SUSPENDED, BANNED and
DELETED profiles produce identical generic 404 bodies. Enumeration is expected for
intentionally public handles; it is not a privacy guarantee.

**Non-disclosure of internal IDs is not an authorization mechanism.**

## 10. VALIDATION

Passing negative/positive coverage includes valid lowercase and uppercase normalization;
length 3/30 and rejected 0/1/2/31; whitespace; slash/backslash; dots/traversal;
percent and encoded slash/double encoding; control/bidi; emoji, Unicode homoglyphs
and Kelvin-sign normalization confusion; SQL/HTML/script-shaped input; exact reserved
names and uppercase variants; leading/trailing separators; case collisions; database
null/format/uniqueness backstops; collision retry/exhaustion; concurrent first creation,
forced cross-user collision, onboarding concurrency and rollback.

Public API tests reject UUID/internal-ID fallback and encoded lookup alternatives.
Frontend tests enforce canonical links, safe redirects and strict response contracts.

## 11. OPENAPI

Current local: 23 operations. All development inboxes enabled: 27.
Without development inboxes: 21. Duplicate operation IDs: 0.
Dynamic path parameters: only handle. Query parameters: 0.
Old UUID public route: absent. Phase 7 operations: 0.
Handle path documents length, ASCII pattern and lowercase/reserved-name behavior.
Authentication credentials/codes remain request-body fields or headers/cookies.

## 12. TESTS

Latest totals include the final double-check on 2026-09-19. See
[the final self-heal audit](PHASE_6_1_FINAL_DOUBLE_CHECK.md) for reproduced defects,
remaining environment gates and the complete current change manifest.

| Check | Result |
|---|---|
| Backend full pytest | 791 passed, 0 failed, 0 skipped; existing Starlette TestClient deprecation warning |
| Frontend full Vitest 4.1.11 | 163 passed, 13 files |
| TypeScript / ESLint / production build | PASS |
| Ruff / compileall / pip check | PASS |
| pip-audit | No known vulnerabilities |
| npm audit / npm audit --omit=dev | 0 vulnerabilities after targeted patch |
| Live Uvicorn/MySQL HTTP workflow | 45 checks passed, including hidden profiles; exact synthetic cleanup |
| Repeated concurrency/rollback/snapshot regressions | 46 passed per run, three runs |
| Isolated MySQL migration cycle and preservation | PASS |
| Alembic current / heads / check | One expected head, no drift |
| Fresh browser address-bar check | ENVIRONMENT BLOCKED; no fabricated pass |
| nginx runtime | Not run; configuration-only referrer change |

A slow/paused run exposed two historical JWT tests using collection-time timestamps.
They now calculate future claims at execution; no JWT implementation or security
expectation was weakened. A complete rerun passed afterward.

Reproduce from backend:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m compileall -q app tests scripts
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts/audit_security_http.py
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py
```

Reproduce from frontend:

```powershell
npm test -- --run
npx tsc -b
npm run lint
npm run build
npm audit
npm audit --omit=dev
```

## 13. DATABASE PRESERVATION

Aggregate fingerprints hash complete ordered table rows in memory, not individual
credentials. Only non-sensitive aggregate hashes/counts were printed.
Before and after development migration/tests:

| Table | Count | SHA-256 prefix (unchanged) |
|---|---:|---|
| users | 4 | 891bef3bf220acaf |
| user_roles | 4 | be38e6e535ea4f63 |
| phone_verification_codes | 3 | c0c2eaa4a03ddbcb |
| refresh_tokens | 7 | e72016e35f65c478 |
| password_reset_codes | 0 | 4f53cda18c2baa0c |
| email_verification_codes | 0 | 4f53cda18c2baa0c |
| user_profiles | 0 | 4f53cda18c2baa0c |

Profile orphans: 0. Duplicate handles: 0. Forbidden null handles: 0.
No synthetic development records remain. The real database had no profiles to backfill;
nonempty backfill preservation was tested separately with three isolated synthetic profiles.

## 14. DOCUMENTATION / GLOBAL POLICY

URLs are for navigation only. Never place passwords, access/refresh/CSRF tokens, OTPs,
phone/email/reset/seller challenge codes, credentials, internal database/user/profile IDs,
private evidence IDs, session IDs, HMAC-derived references, storage keys or signed private
media credentials in application paths, query strings or fragments.

Intentionally public navigation handles/slugs are allowed. No identifier-hiding rule
replaces authentication, server-side ownership, function authorization or DB state.

Future routing conventions (documentation only; not implemented):

| Feature | Preferred navigation | Forbidden pattern |
|---|---|---|
| Profiles | /u/user-k7m4 | /users/42 or legacy UUID path |
| Cities | /city/qingdao | Private/internal lookup IDs |
| Categories | /category/electronics | Private/internal lookup IDs |
| Products | /p/macbook-pro-m4-k7m4 | /products/18374 |
| Favorites | /favorites | User ID query |
| Notifications | /notifications | User/session ID query |
| Seller verification | /seller/verification and /seller/verification/status | Evidence ID or challenge token query |
| Chat | Explicitly public conversation reference or authenticated server state | Internal conversation ID or private access token |
| Admin | Purpose-designed admin reference plus authoritative authorization | Credentials, evidence keys or secret URL state |

Future search/page/sort query parameters require a deliberate non-sensitive allowlist;
none is currently consumed. Never allow arbitrary return URLs merely because they are
same-origin.

Future private seller evidence MUST NOT put evidence IDs, storage object keys, signed
credentials, challenge tokens or media access tokens into application navigation URLs.
If a storage provider later requires a signed retrieval URL, produce it only after
object-level authorization, make it short-lived, and never use it as a persistent
application route, bookmark or public share link. Assess logging/referrer/caching at
that time. No upload, KYC, storage integration or seller workflow is implemented here.

## 15. PHASE BOUNDARY

Phase 7 implementation present: NO.
New future functionality present: NO.
No seller verification/evidence upload/KYC/WeChat seller proof/selfie/product/product-image/
search/chat/deal/review/notification/admin-dashboard behavior was implemented.
Pre-existing inert scaffold files remain untouched.

## 16. FILES CHANGED

The Phase 6.1 implementation manifest follows; all changes are unstaged. No file was deleted.
The final audit additionally introduces `backend/tests/integration/test_profile_snapshot_security.py`
and `documentation/security/PHASE_6_1_FINAL_DOUBLE_CHECK.md`; its manifest includes all 54 files.

| File | Status | Reason |
|---|---|---|
| `backend/alembic/versions/a61b2c3d4e5f_add_public_handles.py` | New | Focused backfill and handle constraints; reversible schema change. |
| `backend/app/api/v1/dev/fake_email_routes.py` | Modified | Consume private message reference via JSON; retain bearer ownership. |
| `backend/app/api/v1/dev/fake_password_reset_routes.py` | Modified | Move account lookup and message reference from URLs to JSON. |
| `backend/app/api/v1/dev/fake_sms_routes.py` | Modified | Move phone lookup and message reference from URLs to JSON. |
| `backend/app/api/v1/profiles/routes.py` | Modified | Strict documented handle lookup; remove UUID route and encoded fallback. |
| `backend/app/common/public_handles.py` | New | Central ASCII validation, reserved list and random generator. |
| `backend/app/main.py` | Modified | Set no-referrer response policy, including unhandled server errors. |
| `backend/app/models/profile.py` | Modified | Handle field, unique/CHECK constraints, normalization and immutable assignment, including expired attributes. |
| `backend/app/repositories/profile_repository.py` | Modified | Handle lookup and bounded unique-collision retries. |
| `backend/app/schemas/development_inbox.py` | New | Strict bounded JSON lookup/consume request models. |
| `backend/app/schemas/profile.py` | Modified | Replace public UUID with handle in both response contracts. |
| `backend/app/services/profile_service.py` | Modified | Handle results; owning-user serialization, current profile reads and bounded whole-transaction deadlock retry. |
| `backend/scripts/audit_public_handle_migration.py` | New | Isolated MySQL migration/data-preservation test and safe cleanup. |
| `backend/scripts/audit_security_http.py` | Modified | Update live workflow to handle and JSON-inbox contracts. |
| `backend/tests/integration/test_development_fake_sms_routes.py` | Modified | Regression tests for JSON lookup contract and access checks. |
| `backend/tests/integration/test_phase_5e_integrated_auth_security.py` | Modified | Evaluate future JWT timestamps at test execution to remove collection-time flakiness. |
| `backend/tests/integration/test_pre_phase7_security.py` | Modified | Preserve account-state regression with new handle route. |
| `backend/tests/integration/test_profile_concurrency.py` | Modified | Assert stable handle in existing concurrency regressions. |
| `backend/tests/integration/test_profile_routes.py` | Modified | Update public lookups/contracts without removing security assertions. |
| `backend/tests/integration/test_public_handles.py` | New | Real-MySQL validation, uniqueness, collision, BOLA and rollback tests. |
| `backend/tests/unit/test_password_reset_request.py` | Modified | Exercise body-based local reset lookup. |
| `backend/tests/unit/test_profile_openapi.py` | Modified | Assert exact new handle route and minimized response fields. |
| `backend/tests/unit/test_public_handles.py` | New | Handle edge cases, OpenAPI privacy and local-inbox access regressions. |
| `documentation/CURRENT_PROJECT_STATUS.md` | Modified | Record Phase 6.1 and new migration head; retain historical evidence. |
| `documentation/README.md` | Modified | Index the focused URL policy and evidence report. |
| `documentation/api/profile-api.md` | Modified | Document handle API, field privacy and removed UUID lookup. |
| `documentation/architecture/frontend-architecture.md` | Modified | Document routing, cache keys, redirects, referrer and UI boundaries. |
| `documentation/phases/PHASE_3B_LOCAL_FAKE_SMS.md` | Modified | Update runnable fake-inbox lookup/consume instructions. |
| `documentation/phases/PHASE_6_PROFILES_AND_ONBOARDING.md` | Modified | Mark old UUID navigation superseded by Phase 6.1. |
| `documentation/postman/UniShop_Phase_3B_Local_Fake_SMS.postman_collection.json` | Modified | Replace phone query lookups with JSON POST examples. |
| `documentation/security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md` | New | Complete policy, inventory, evidence, future conventions and change manifest. |
| `frontend/index.html` | Modified | Set document no-referrer policy. |
| `frontend/package-lock.json` | Modified | Lock patched Vitest dependency family and required transitive patch. |
| `frontend/package.json` | Modified | Pin targeted patched Vitest 4.1.11. |
| `frontend/src/app/router.tsx` | Modified | Canonical /u/:handle; remove legacy UUID route. |
| `frontend/src/features/auth/localFakeSmsApi.ts` | Modified | Send phone/message references in JSON bodies. |
| `frontend/src/features/profiles/api.ts` | Modified | Validate handle before API URL construction and parse new response. |
| `frontend/src/features/profiles/contracts.ts` | Modified | Strict public_handle contract instead of UUID. |
| `frontend/src/features/profiles/handles.ts` | New | Shared strict client validation and public link builder. |
| `frontend/src/features/profiles/hooks.ts` | Modified | Public query keys/invalidation use handles. |
| `frontend/src/features/profiles/types.ts` | Modified | PublicHandle-based client types. |
| `frontend/src/pages/public/PublicProfilePage.tsx` | Modified | Read handle route and safely reject malformed navigation. |
| `frontend/src/pages/shared/ProfilePage.tsx` | Modified | Add public-handle profile link. |
| `frontend/src/routes/routePaths.ts` | Modified | Allowlist redirects; never propagate arbitrary query/hash state. |
| `frontend/tests/unit/auth-routes.test.tsx` | Modified | Assert query/hash removal and safe fallback. |
| `frontend/tests/unit/development-route.test.tsx` | Modified | Assert handle-only dynamic route and no legacy/future routes. |
| `frontend/tests/unit/login-form.test.tsx` | Modified | Use a real implemented destination in login redirect regression. |
| `frontend/tests/unit/profile-cache-security.test.ts` | Modified | Retain cache-boundary security tests with handle contract. |
| `frontend/tests/unit/profile-contracts.test.ts` | Modified | Use new strict profile response fixture. |
| `frontend/tests/unit/profile-pages.test.tsx` | Modified | Update public rendering and assert canonical profile link. |
| `frontend/tests/unit/url-privacy.test.tsx` | New | Adversarial handles/redirects, remount, hidden state and body-only inbox tests. |
| `infrastructure/nginx/nginx.conf` | Modified | Set no-referrer; avoid duplicate upstream policy header. |

## 17. GIT STATE

Final HEAD remains `2fb4b63f1280959b2204f147d1f8f901325f4c0b`.
Working tree contains only this phase's reviewed changes. Staged files: 0.
Commit created: NO. Push performed: NO.
Final diff --check: PASS. No tracked/untracked secret-bearing filename or match to
current local secret values was found. Backend/frontend .env and .env.example were
not changed; no secret-bearing configuration diff exists.

## 18. FINAL VERDICT

URL privacy gate passed: YES.
Internal IDs absent from public navigation: YES (legacy opaque public UUID also removed).
Secrets absent from application-generated URLs: YES, within verified current scope.
Ready for human staging review: YES. The automated/source gate passes.
The complete runtime security gate remains open: fresh browser and Docker/NGINX checks
are environment-blocked. Phase 7 authorization is deferred pending those checks and a
reviewed commit. Production readiness is not asserted.

The final double-check report supersedes the earlier unconditional Phase 7 readiness statement.
