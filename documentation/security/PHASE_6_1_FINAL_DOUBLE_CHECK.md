# Phase 6.1 Final Double-Check and Self-Heal Audit

Date: 2026-09-19. Repository: UniShop China. No staging, commit or push authorized or performed.

## 1. EXECUTIVE RESULT

Repository double-check complete: NO for the full requested runtime gate; all available source,
database and automated checks completed. Browser and Docker runtime checks remain blocked.
Phase 6.1 still valid: YES within verified scope.
Ready for staging review: YES.
Ready for Phase 7 after commit: NO until the open runtime checks are completed and reviewed.

Confirmed code findings: Critical 0; High 0; Medium 1 (fixed); Low 2 (fixed).
Informational environment limitations: 2 (browser and Docker/NGINX).
No known unresolved reproduced code defect remains. This is engineering evidence, not
OWASP certification or a production-readiness claim.

## 2. PRE-FLIGHT

Branch: `feature/authentication`.
HEAD and remote `origin/feature/authentication`:
`2fb4b63f1280959b2204f147d1f8f901325f4c0b`.

Initial tree: 43 modified tracked files, 9 untracked files, 0 staged files.
All belonged to the supplied Phase 6.1 work. No unrelated work was discarded.
Status, short status, branch status, HEAD, eight-commit log, untracked inventory,
diff whitespace check, full Git integrity check and read-only remote query passed.
No unexpected staged state was present. No applicable AGENTS.md was found.

## 3. FILE/FOLDER INVENTORY

Final tracked/nonignored-untracked inventory: 575 files, excluding installed dependencies,
virtual environments, ignored local environment files and generated build/cache output.

| Area | Files |
|---|---:|
| backend/app | 181 |
| backend/tests | 48 |
| backend/alembic | 10 |
| backend/scripts | 6 |
| frontend/src | 187 |
| frontend/tests | 16 |
| documentation | 65 |
| infrastructure | 6 |
| Other root/config/database/Postman/scaffold files | 56 |

Inventory and targeted source/config/contract/security review covered the repository;
every changed/new file was reviewed. Imports, static checks, real database tests and
frontend tests supplement the review; this is not a claim of formal proof for every line.
No accidental nonignored dump, key, environment file, build output, temporary test artifact
or generated dependency directory was found. Existing empty/inert future-phase scaffolds
were retained, not mistaken for implemented features or deleted. No duplicate required
replacement or architectural consolidation.

## 4. CONFIRMED ISSUES FOUND

### AUDIT-001 — Medium — stale profile reads under MySQL REPEATABLE READ

Files: `backend/app/repositories/profile_repository.py`,
`backend/app/services/profile_service.py`.

Root cause: authentication can establish an older consistent-read snapshot before the
owning-user row lock is acquired. Removing the profile locking read did not refresh that
snapshot. Three new cases failed before repair: a duplicate lazy profile insert, stale
profile fields, and onboarding completion after a required city was cleared elsewhere.
Impact: intermittent 500 responses, stale own-profile data and incorrect onboarding state.

Fix: restore SELECT FOR UPDATE with populate_existing after the owning-user lock.
Retry only whole transactions selected as InnoDB deadlock victims (1213), at most three
attempts, including when a savepoint-cleanup error wraps that original error.
Unrelated duplicate-key and lock-timeout errors are not retried; exhaustion retains safe
error handling. The separate eight-attempt unique-handle collision allocator is unchanged.
All three reproductions pass. Three 46-case race/rollback runs pass.

The approach follows MySQL's distinction between consistent and locking reads and its
requirement to retry deadlock victims:
[locking reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html),
[deadlock handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks-handling.html).

### AUDIT-002 — Low — expired ORM attribute bypassed handle immutability

File: `backend/app/models/profile.py`.

Root cause: the assignment validator inspected the instance dictionary; expiration removes
the old handle from that dictionary. Impact: trusted ORM callers could rename an expired
handle although the API already prohibited it. A new regression failed before repair.
Fix: active_history loads the previous value before validation. The expired-attribute test
now rejects renaming. No client-controlled handle editing was added.

### AUDIT-003 — Low — unhandled 500 response omitted referrer policy

File: `backend/app/main.py`.

Root cause: the outer unhandled-exception response bypassed the normal response middleware.
Impact: Referrer-Policy was inconsistent on unexpected failures.
Fix: set no-referrer in the global error handler, retaining private no-store/no-cache headers
and the existing generic JSON error. New regression failed before and passes after repair.

## 5. PHASE 6.1 REVIEW

Canonical UI route: `/u/:handle`.
Canonical public API: `GET /api/v1/profiles/by-handle/{handle}`.
Old UUID routes are removed without redirect or compatibility fallback.
The legacy public_id remains intentionally internal, absent from both profile response schemas.

Handles: ASCII only, lowercase normalization, 3–30 characters, alphanumeric ends,
alphanumeric/underscore/hyphen interior, reserved names rejected. Generated values contain
a neutral prefix and 80 random bits, with no identity-derived input. Unique/NOT NULL/CHECK
constraints, unique index, bounded collision retry and immutable model/API behavior verified.
Traversal, encoded separators, double encoding, whitespace, bidi controls, Unicode lookalikes,
malformed values and reserved names are covered by negative tests.

URL search matches were classified:
SAFE — canonical public handles, fixed navigation, placeholder-only documentation.
INTERNAL ONLY — database IDs, in-memory cache keys and object ownership joins.
NOT URL RELATED — keyword arguments such as user_id/code/token in Python or JSON bodies.
No remaining confirmed risky application-generated URL was found.
Adversarial test URLs and clearly historical removed-route references are intentional.
Private fake-inbox lookup/consume values now travel in JSON, never path/query parameters.
No public UUID navigation remains in active frontend code.

Profile field contracts align on public_handle, display_name, bio, city, member_since and
verification indicators; own-only onboarding/timestamps remain separate. Public responses
exclude private contact, account-state, role and database-ID fields. Unknown/incomplete/
suspended/banned/deleted profiles produce the same generic missing response.

## 6. BACKEND SECURITY

Current database account authority and owner-derived profile mutations remain authoritative.
Bearer guards, active-account checks, role authority, strict body allowlists, parameterized
SQLAlchemy queries, validation sanitization, rate-limit responses and safe errors passed
regression checks. No new SQL interpolation or client-owned role/status assignment was found.

Cookie-bound CSRF, exact Origin checking, scoped HttpOnly refresh cookies, refresh rotation,
reuse-family revocation, logout/logout-all, password-reset/change invalidation, and separate
phone/email challenge purposes remain intact. Development inboxes remain loopback/development
only; email inbox ownership remains authenticated. Invalid submissions do not reflect secret
inputs. Private auth/profile/dev responses retain no-store and no-cache, including generic 500s.

Review covered OWASP API risk areas including object/property authorization, authentication,
resource limits, misconfiguration and API inventory. It is not an ASVS/API Top 10 certification.
[OWASP API Security Top 10](https://api-security.owasp.org/editions/2023/en/0x11-t10/)

Known deployment boundary unchanged: rate limiting is process-local, not distributed.
This single-process development verification does not establish multi-worker production safety.

## 7. FRONTEND SECURITY

Access tokens remain memory-only; refresh credentials stay in HttpOnly cookies.
No access/refresh token persistence to localStorage or sessionStorage was found.
Router guards are UX controls, not a replacement for backend authorization.
Existing session epochs/abort boundaries prevent late authenticated responses from
repopulating state after logout/account switch. Private query keys remain user-scoped;
public query keys use validated handles.

Redirects use existing-route/valid-handle allowlists and discard query/hash state.
Malformed public routes never dispatch unsafe identifiers. Hidden profiles render the same
missing state. React renders untrusted profile content as text.
DOM-router remount/history-related regression tests pass; actual browser address-bar,
back/forward and deep-link refresh verification remains unverified due to the browser blocker.
Reset/forgot/signup/standard phone pages remain existing placeholders, not newly finished UI.

## 8. DATABASE / MIGRATIONS

Actual local server: MySQL 9.4.0, PyMySQL, shared validated DATABASE_URL, pool_pre_ping.
Alembic current and sole head: `a61b2c3d4e5f`.
History:
`a75289cfd4a9 -> c91e4a7b2d6f -> aca2dda0ef53 -> d5f0c1e2a3b4 -> f6a1b2c3d4e5 -> a61b2c3d4e5f`.
Alembic check: no new upgrade operations/schema drift.

The handle migration adds a nullable column, backfills random unique values, then enforces
NOT NULL/unique/CHECK constraints. Random values are intentionally not deterministic;
the shape, policy, collision bound and preservation behavior are fixed. Frozen migration
validation does not import changing application policy. Apply during a maintenance window.

Fresh isolated MySQL upgrade/downgrade/upgrade: PASS on three synthetic profiles, including
Unicode content. All pre-existing fields survive; only the new handle is removed on downgrade
and regenerated on re-upgrade. No DROP TABLE, create_all/drop_all or dev downgrade/reset ran.
MySQL 8.x compatibility was source-reviewed; a separate 8.x runtime/container run was unavailable.

Full ordered-row fingerprints before/after all database testing match:

| Table | Rows | Unchanged SHA-256 prefix |
|---|---:|---|
| users | 4 | 891bef3bf220acaf |
| user_roles | 4 | be38e6e535ea4f63 |
| phone_verification_codes | 3 | c0c2eaa4a03ddbcb |
| refresh_tokens | 7 | e72016e35f65c478 |
| password_reset_codes | 0 | 4f53cda18c2baa0c |
| email_verification_codes | 0 | 4f53cda18c2baa0c |
| user_profiles | 0 | 4f53cda18c2baa0c |

Existing users, role assignments, sessions and challenges remain unchanged.
No invalid/duplicate/null handles, orphan relationships or unexpected synthetic rows remain.
Profile/backfill behavior is exercised using isolated synthetic records despite the dev
profile table being empty. Cleanup targets only records created by the audit.

## 9. OPENAPI

| Variant | Operations | Development operations |
|---|---:|---:|
| Current local | 23 | 2 |
| All development inboxes | 27 | 6 |
| Production-safe configuration | 21 | 0 |

Duplicate operation IDs: 0. Sensitive query/path parameters: 0.
Only public handle is a dynamic path parameter. Legacy UUID routes: 0. Phase 7 routes: 0.
An initial attempt to reuse development fake-provider settings in production correctly
failed closed; the production-safe, providers-disabled variant above passed.

## 10. TESTS

| Check | Final result |
|---|---|
| Full backend pytest | 791 passed; 0 failed; 0 skipped |
| Targeted security selection | 637 passed; 154 deliberately deselected |
| Repeated concurrency/rollback/snapshot selection | 46 passed per run, three runs; 407 deliberately deselected each |
| New audit regressions | 8 passed, included in full suite |
| Full frontend Vitest | 163 passed in 13 files |
| TypeScript | PASS: npx tsc -b |
| ESLint / production build | PASS |
| Ruff / compileall / pip check | PASS |
| pip-audit | No known vulnerabilities |
| npm audit / npm audit --omit=dev | 0 vulnerabilities |
| OpenAPI / Alembic / drift | PASS |
| Isolated migration cycle | PASS |
| Live loopback Uvicorn + real MySQL | 45 checks passed; preservation and exact cleanup true |
| Browser | ENVIRONMENT BLOCKED |
| Docker images / NGINX runtime | ENVIRONMENT BLOCKED |

The live workflow covers health, registration, login, /me, refresh, logout/logout-all,
phone/email verification, password reset/change, private profile update/onboarding,
minimal public handle response, hidden profiles and cross-user mutation rejection.
The child server stopped after testing. No external SMS/email was sent.

The browser skill bootstrap failed before opening a tab:
`codex/sandbox-state-meta: missing field sandboxPolicy`.
No browser PASS is claimed. Docker/NGINX executables are unavailable; build-context and
configuration tests passed, but image builds/proxy execution did not run.

One existing Starlette TestClient deprecation warning remains; it is not a failed test.
An attempted npm run typecheck found no such script; the correct existing npx tsc -b and
build commands passed. Full npm audit encountered transient ECONNRESET twice; a bounded
retry returned 0 vulnerabilities. No failure was silently relabeled as a pass.

Reproduce from backend:
```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/integration tests/unit -q -k "profile or handle or auth or refresh or reset or phone or email or rate or redirect or openapi or pre_phase7 or concurrency or migration"
1..3 | ForEach-Object {
  .\.venv\Scripts\python.exe -m pytest tests/integration -q -k "concurrent or racing or delayed_reset or rotated_cookie or rolls_back or rollback or snapshot"
  if ($LASTEXITCODE -ne 0) { throw "Concurrency regression failed" }
}
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m compileall -q app tests scripts alembic
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts/audit_security_http.py
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py
```

From frontend:
```powershell
npm test -- --run
npx tsc -b
npm run lint
npm run build
npm audit --fetch-retries=0 --fetch-timeout=20000
npm audit --omit=dev
npm ls --depth=0
```

## 11. DEPENDENCIES

No dependency change was made by this final audit. Python dependency checks passed.
The existing Phase 6.1 patch remains narrowly pinned: Vitest and seven @vitest packages
4.1.10 -> 4.1.11, plus required tinyrainbow 3.1.0 -> 3.1.1.
Nine lockfile package entries changed, no unrelated major upgrade.
The earlier vulnerability motivated that patch; fresh audits now report zero known findings.
Installed direct dependencies and root package-lock/manifest consistency passed.
Existing broader manifest ranges remain locked by package-lock; no dependency redesign occurred.

## 12. SECRET / LOGGING AUDIT

Read-only scan covered tracked plus nonignored-untracked source/config/docs and the last
eight commit patches. Known local secret values were compared only in memory; none matched.
Generic private-key/cloud-key/JWT/credential-URL patterns found only the Compose runtime
substitution/placeholder, not a real embedded credential. No matched value was printed.
This bounded scan is not proof about all historical objects or unknown secret formats;
gitleaks/trufflehog were unavailable.

Application logging review found only safe database error category/code logging.
Validation, private error payload and body/header logging regressions passed.
No new password/code/token logging was introduced. The live audit suppresses child server
output and prints only check labels and preservation flags.
Arbitrary hostile incoming URLs may still be logged by deployment infrastructure; this gate
covers application-generated URLs, not a new production access-log redaction system.

Git and both Docker ignore files exclude local .env, private key files, dependency/build
output and existing uploads/private_uploads locations. Environment examples contain
placeholders only. No local environment file was changed or tracked.
Future private evidence still requires runtime-only storage policy; no evidence feature exists.

## 13. DOCUMENTATION

Accurate within stated scope: YES.
Updated CURRENT_PROJECT_STATUS.md, documentation/README.md and the URL policy report
with final counts, corrected profile-lock/retry behavior, audit link and explicit open gates.
This report adds the complete current manifest. Historical phase test counts remain marked
as historical rather than rewritten. Phase 6.1 docs align with actual handle routes,
payloads and migration. No production-readiness claim remains in the current phase verdict.

## 14. PHASE BOUNDARY

Seller verification present: NO.
Products present: NO.
Chat present: NO.
Admin dashboard present: NO.

These refer to implemented/exposed functionality; pre-existing inert scaffold names remain.
No payments, KYC/passport, evidence uploads or Phase 7 workflow was added.

## 15. FINAL CHANGES

54 files total: 43 modified tracked files and 11 new/untracked files. No deletions.
All are unstaged. The audit itself changed only four backend implementation files, the existing
live audit script, one new regression file, three existing phase documentation files, and
this report. Remaining entries are the reviewed pre-existing Phase 6.1 work.

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
| `backend/app/repositories/profile_repository.py` | Modified | Handle lookup, current locking reads and bounded unique-collision retries. |
| `backend/app/schemas/development_inbox.py` | New | Strict bounded JSON lookup/consume request models. |
| `backend/app/schemas/profile.py` | Modified | Replace public UUID with handle in both response contracts. |
| `backend/app/services/profile_service.py` | Modified | Handle results; owning-user serialization, current profile reads and bounded whole-transaction deadlock retry. |
| `backend/scripts/audit_public_handle_migration.py` | New | Isolated MySQL migration/data-preservation test and safe cleanup. |
| `backend/scripts/audit_security_http.py` | Modified | Handle/JSON contracts and 45 live checks, including hidden account states. |
| `backend/tests/integration/test_development_fake_sms_routes.py` | Modified | Regression tests for JSON lookup contract and access checks. |
| `backend/tests/integration/test_phase_5e_integrated_auth_security.py` | Modified | Evaluate future JWT timestamps at test execution to remove collection-time flakiness. |
| `backend/tests/integration/test_pre_phase7_security.py` | Modified | Preserve account-state regression with new handle route. |
| `backend/tests/integration/test_profile_concurrency.py` | Modified | Assert stable handle in existing concurrency regressions. |
| `backend/tests/integration/test_profile_routes.py` | Modified | Update public lookups/contracts without removing security assertions. |
| `backend/tests/integration/test_profile_snapshot_security.py` | New | Eight regressions for stale snapshots, expired-handle immutability, bounded retry and error headers. |
| `backend/tests/integration/test_public_handles.py` | New | Real-MySQL validation, uniqueness, collision, BOLA and rollback tests. |
| `backend/tests/unit/test_password_reset_request.py` | Modified | Exercise body-based local reset lookup. |
| `backend/tests/unit/test_profile_openapi.py` | Modified | Assert exact new handle route and minimized response fields. |
| `backend/tests/unit/test_public_handles.py` | New | Handle edge cases, OpenAPI privacy and local-inbox access regressions. |
| `documentation/CURRENT_PROJECT_STATUS.md` | Modified | Record Phase 6.1, final test evidence and open environment gates; retain history. |
| `documentation/README.md` | Modified | Index URL policy and final double-check evidence. |
| `documentation/api/profile-api.md` | Modified | Document handle API, field privacy and removed UUID lookup. |
| `documentation/architecture/frontend-architecture.md` | Modified | Document routing, cache keys, redirects, referrer and UI boundaries. |
| `documentation/phases/PHASE_3B_LOCAL_FAKE_SMS.md` | Modified | Update runnable fake-inbox lookup/consume instructions. |
| `documentation/phases/PHASE_6_PROFILES_AND_ONBOARDING.md` | Modified | Mark old UUID navigation superseded by Phase 6.1. |
| `documentation/postman/UniShop_Phase_3B_Local_Fake_SMS.postman_collection.json` | Modified | Replace phone query lookups with JSON POST examples. |
| `documentation/security/PHASE_6_1_FINAL_DOUBLE_CHECK.md` | New | This 17-section audit, evidence, limitations and complete 54-file staging-review manifest. |
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

## 16. FINAL GIT STATE

HEAD: `2fb4b63f1280959b2204f147d1f8f901325f4c0b`.
Staged files: 0. Unstaged modified tracked files: 43. Untracked files: 11.
Git diff --check: PASS. Git fsck --full: PASS.
Remote branch unchanged at expected baseline.
Commit created: NO. Push performed: NO. No git add was executed.

## 17. FINAL VERDICT

Repository clean enough for human staging review: YES.
Phase 6.1 automated/source security gate: PASSED.
Complete requested runtime security gate: NO — browser and Docker/NGINX checks are blocked.
Phase 7 may begin after reviewed commit/push alone: NO; resolve/review the open runtime gates
and obtain separate implementation authorization first.

All three reproduced code defects were repaired; automated, real-MySQL and preservation
checks pass. The work remains intentionally unstaged. No Phase 7 functionality was introduced.

