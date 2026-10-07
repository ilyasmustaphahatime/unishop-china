# UniShop China Current Project Status

## Phase 1-8 architecture review (2026-10-07)

**LOCAL ARCHITECTURE/REGRESSION REVIEW PASSED: YES. PRODUCTION READY: NO.**
Phase 9 may begin as a separately requested development task; it was not implemented.

- Backend: **1,006 passed**, including 23 new architecture/security regression cases;
  one upstream Starlette/httpx TestClient deprecation warning. Frontend: **211 passed**
  in 15 files; TypeScript, ESLint and production build passed.
- Three repeated 33-case race gates passed (auth/refresh, profiles, seller and catalog).
  Real MySQL/Uvicorn: **79 checks passed**, synthetic cleanup complete, process stopped.
  Ordered counts/SHA-256 fingerprints across **all 14 tables are unchanged**.
- Python compile, Ruff, pip check and pip-audit passed. Alembic current/sole head
  remains `e8f0a1b2c3d4`, no drift; isolated upgrade/downgrade/upgrade passed.
- OpenAPI is identical before/after in local (45), all-fake development (49) and
  production-configured (43) operations; no duplicate operation IDs/Phase 9 endpoints.
- Narrow fixes: refresh cached state in locked auth reads; recover Sessions after
  owned-auth commit failure; batch seller queue evidence; move shared rate/text/size
  rules and seller error mapping to neutral boundaries; keep ticket issuance inside
  the authorized seller service. No schema, dependency or frontend-code changes.
- Full npm audit: existing **5 High / 2 Moderate dependency nodes** from braces and
  postcss-selector-parser; production-only audit: zero. Installed 326 package versions
  match the lockfile. Normal HTTPS and trusted system CAs were used. Tailwind stays 3.
- Browser runtime remains unverified/environment-blocked; Docker/NGINX commands are
  unavailable. Private production storage, multi-worker controls and operations remain
  release blockers. This is not OWASP certification or a production approval.
- Original 62 Phase 8 files preserved. Audit changes are separately attributed in the
  [31-section report and full manifests](architecture/PHASE_1_TO_8_ARCHITECTURE_REVIEW.md).
  No staging, commit or push; HEAD remains `0a79e9b`.

The Phase 8 completion section below records its earlier 983-test handoff, not the
latest 1,006-test architecture gate. Older dated sections remain historical evidence.

## Current Phase 8 completion (2026-10-07)

Cities, two-level categories, profile city references, and the minimal backend admin
foundation are implemented. **LOCAL PHASE 8 PASSED: YES. PRODUCTION READY: NO.**
Phase 9 development may begin separately; no Phase 9 functionality was added here.

- MySQL/Alembic current and sole head: `e8f0a1b2c3d4`, through additive revisions
  `d8e9f0a1b2c3` and `e8f0a1b2c3d4`; no drift. Isolated migration round-trip passed.
- Backend: 983 tests passed; Phase 8: 100 tests; complete eight-case concurrency suite
  passed three repetitions. Frontend: 211 tests, TypeScript, ESLint and build passed.
- Real MySQL/Uvicorn: 79 checks passed; exact synthetic cleanup and existing data
  fingerprints preserved. All ten original tables are unchanged; six cities and one
  catalog write-lock row are the intentional new data.
- Profile writes now send a canonical city slug (`city: "qingdao"`), not a display
  label. Responses retain the city display name; own profiles add `city_slug` and
  `city_active`. Historical retired cities remain visible and do not undo completed
  onboarding. The frontend and API changed together.
- Admin writes recheck ACTIVE status and the current database ADMIN role under locks.
  Every successful catalog mutation and its minimal audit record commit together.
- Python compile, Ruff, pip check and pip-audit passed. Frontend lockfile/install
  consistency passed for 326 installed packages. Only `source-map-js` was narrowly
  patched (1.2.1 to 1.2.2), using system-trusted CAs and normal HTTPS verification.
- Fresh full npm audit still reports **5 High and 2 Moderate dependency nodes** from
  two existing build-graph root advisories: braces and postcss-selector-parser.
  Production-only npm audit has zero findings. Tailwind remains **3.4.19**; no Tailwind 4
  migration or cross-major selector-parser override was attempted. Both unresolved
  advisories remain production/security blockers, not accepted risk.
- Browser and Docker/NGINX runtime verification remain **ENVIRONMENT BLOCKED**.
  Private production object storage and broader production operations remain unready.
- No staging, commit or push. Starting/final HEAD: `0a79e9b`.

See the [24-section completion report and complete changed-file manifest](phases/PHASE_8_CITIES_CATEGORIES_ADMIN_FOUNDATION.md),
[catalog API](api/catalog-api.md), and [updated profile API](api/profile-api.md).
Everything below is historical evidence; older heads, dependency counts and
"Phase 8 has not started" statements describe their dated audit only.

## Authentication phases

### Current Phase 7 follow-up (final regression 2026-10-05)

The existing Phase 7 implementation is retained and extended with expiring handwritten
challenges, draft-only renewal, a boolean public seller badge, header-only private download
credentials, audit-before-image release, and pre-parse seller/admin peer limits.
Current database head: `c7d8e9f0a1b2` (additive to `b7c1d2e3f4a5`).
Backend tests: 883 passed; frontend tests: 187 passed; live HTTP/MySQL checks: 64 passed.
Migration round-trips use an isolated instance only. Development rows and private files are preserved.
**LOCAL PHASE 7 PASSED: YES. PRODUCTION READY: NO.** The local automated functional/security,
migration and data-preservation regressions pass. Trusted-system-CA npm installation succeeded;
actual Axios 1.20.0, brace-expansion 5.0.12 and Undici 7.29.1 match the lockfile and passed the
full frontend gate. Verified PyJWT/urllib3 updates are retained; full backend suite and pip-audit pass.
Full npm audit remains non-clean: one unpatched braces advisory affects five High dependency
nodes in the Tailwind 3 build graph. npm audit --omit=dev has zero known vulnerabilities.
Per the user, retain Tailwind 3 and resolve braces in a separate dependency-migration task.
This remains a production/security blocker, not accepted risk. Private production object storage
is unconfigured; browser and Docker/NGINX runtime checks are environment-blocked.
See the [full completion report and file manifest](phases/PHASE_7_COMPLETION_GATE_2026_10_04.md).
Do not treat historical audit-clean statements below as current.
Phase 8 has not started. No commit or push was made by this follow-up.

### Earlier phase evidence (historical)

Phase 7 seller verification: implemented and locally verified (843 backend tests, 179 frontend
tests, 58 live HTTP checks, isolated migration cycle and repeated seller concurrency tests passed).
User-confirmed workflow: private draft, three required images, submission, admin review,
and independent retry after rejection. New Alembic head: `b7c1d2e3f4a5`.
See [Phase 7 implementation](phases/PHASE_7_SELLER_VERIFICATION.md) and
[threat model](security/PHASE_7_SELLER_VERIFICATION_THREAT_MODEL.md).
Production storage integration and browser/container runtime checks remain open.
Phase 8 has not started. Earlier phase status/counts below are historical records.

Phase 6.1 URL Privacy & Public Identifier Hardening: implemented. Canonical public profiles now use
`/u/:handle`; private identifiers and local-inbox references travel in JSON bodies, never navigation URLs.
Alembic head is `a61b2c3d4e5f`. See [Phase 6.1 evidence and policy](security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md).
Final double-check: 791 backend tests, 163 frontend tests, 45 live HTTP checks and three
46-case concurrency runs passed. Three reproduced issues were repaired. Changes remain
unstaged; browser and Docker runtime checks remain environment-blocked, so the full
runtime gate and Phase 7 approval are pending. See [final audit](security/PHASE_6_1_FINAL_DOUBLE_CHECK.md).
Earlier phase counts below remain historical evidence, not the latest test totals.

- Phase 1 authentication database models and migration: complete.
- Phase 2 user registration API and test isolation: complete.
- Phase 3A phone OTP generation, HMAC storage, resend limits, verification, and provider abstraction: complete.
- Phase 3B secure local fake SMS workflow and manual verification: complete.
- Real Tencent SMS: pending and disabled.
- Phase 4A secure email/phone login, short-lived access token, authentication dependency, and `/auth/me`: complete.
- Phase 4B backend refresh-token rotation, HttpOnly cookies, CSRF, reuse detection, logout, and logout-all: complete.
- Phase 4C secure frontend authentication: complete, including 7/7 user-verified real-browser checks.
- Phase 4D final authentication security audit: complete with no critical/high authentication blocker.
- Phase 5A secure forgot-password request and reset-challenge generation: complete.
- Phase 5B secure reset verification, durable attempts, atomic password replacement, reset consumption, and refresh-session revocation: complete.
- Pre-Phase 5C validation-response and Docker build-context security blockers: resolved.
- Phase 5C secure authenticated password change, current-password proof, atomic reset/session invalidation, concurrency control, and dual rate limits: complete.
- Phase 5D secure authenticated email ownership verification, provider-safe challenge activation, durable abuse controls, replay protection, and MySQL concurrency safety: complete.
- Phase 5E final integrated authentication security audit, cross-purpose/cross-user matrices, real-MySQL cross-feature races, lifecycle verification, and closure gate: complete.
- Phase 1-5 authentication subsystem: closed.
- Phase 6 secure profiles, onboarding, public-profile privacy, frontend design system, and authenticated shell: complete.
- Phase 1-6 foundation: ready for separately approved Phase 7 development.
- Protected profile object/function authorization: implemented and verified.

## Pre-Phase-4 cleanup status

- Baseline commit: `320bd5c`.
- Repository duplicate, architecture, configuration, secrets, generated-artifact, dependency, and security audits: performed.
- Registration now has a thread-safe, connection-peer rate limit with a safe HTTP 429 response.
- Production and staging force FastAPI debug mode off.
- The duplicated UTC-normalization helper was consolidated.
- Future authentication state no longer persists tokens or user data in browser storage.
- Postman phone, password, and code inputs now use empty collection variables.
- One transitive dependency advisory was fixed by pinning `brace-expansion` to a patched version.
- React Router was migrated from the v7 compatibility package to patched `react-router` 8.3.0; existing declarative/data routing behavior and tests remain intact.
- `npm audit` reports zero vulnerabilities, and `pip-audit` reports no known Python dependency vulnerabilities.
- Authentication validation errors now return only sanitized error type, field location, and fixed safe messages; request `input`, Pydantic context, exception representations, and request bodies are never returned or logged.
- The backend Docker build context now excludes real `.env` variants, virtual environments, caches, tests, logs, and private/runtime uploads through `backend/.dockerignore`; `.env.example` remains an intentional placeholder-only exception.
- The local audit virtual environment uses pip 26.2.1, resolving CVE-2026-13346 without changing application requirements.
- The ignored local backend `.env` now contains exactly one canonical development `APP_ENV` entry and one canonical local `FRONTEND_URL` entry; no secret-bearing value was changed.
- Pre-Phase-4 security gates remain complete; Phase 4A was implemented without a schema migration.
- The pre-Phase-4B full-system audit disabled unused CORS/browser credential mode and removed the development Fake SMS page from production bundles.

## Verified foundation

- MySQL connection succeeds against `unishop_china`.
- SQLAlchemy uses parameterized expressions and no request-derived raw SQL.
- Alembic current and head are `f6a1b2c3d4e5`; no schema drift exists.
- Authentication tables are `users`, `user_roles`, `refresh_tokens`, `phone_verification_codes`, `password_reset_codes`, and `email_verification_codes`.
- Marketplace profile data is isolated in `user_profiles` with unique user/public identifiers, bounded fields, and server-owned onboarding state.
- Strict Pydantic schemas reject unknown and privileged registration fields.
- Global validation-error sanitization prevents passwords, reset/verification codes, tokens, secrets, and nested submitted values from being reflected in HTTP 422 responses while retaining safe field metadata.
- Passwords use Argon2id; OTP values use HMAC-SHA256 and constant-time comparison.
- Registration assigns only the `BUYER` role.
- Phone resend retains its cooldown/hourly limits, verification retains its five-attempt limit, and `SUSPENDED`, `BANNED`, or `DELETED` accounts cannot receive or consume a phone challenge.
- Registration and phone-verification APIs return no OTP, password, hash, token, provider error, stack trace, or database detail.
- Login returns only a 15-minute access token plus a schema-protected user view; `/auth/me` reloads current roles and ACTIVE status from MySQL.
- Unknown users, wrong passwords, and inactive users share one generic 401 response, with dummy Argon2 verification for unknown users.
- Login limits are five attempts per connection peer per minute and ten attempts per HMAC-hashed identifier per 15 minutes.
- Development fake SMS remains disabled by default, loopback-only, memory-only, and absent from production routing/OpenAPI.
- Forgot-password accepts normalized email or Mainland China phone, returns one generic 202 contract, and uses a comparable dummy HMAC/database path for unknown or ineligible accounts.
- Reset challenges are six secure digits stored only as domain-separated HMAC-SHA256, expire after ten minutes, and become usable only after confirmed delivery and a newest-row recheck.
- Forgot-password abuse controls include actual-peer and HMAC-identifier process-local limits, a 60-second database cooldown, and a five-challenge rolling hourly cap.
- Password-reset delivery is disabled by default; the optional fake provider/inbox is bounded, memory-only, identifier-scoped, loopback-only, development-only, and blocked in production.
- Password-reset completion accepts only normalized identifier, six ASCII digits, and the registration-strength new password; all extra/internal fields are forbidden.
- Reset challenges have a durable five-attempt budget, atomic MySQL increments, newest-only/expiry/consumption enforcement, and real concurrent-request coverage.
- Successful reset stores only Argon2id, consumes the challenge, invalidates the user's other challenges, revokes every active refresh family, returns no token/cookie, and requires normal login.
- Unknown, inactive, wrong, expired, superseded, consumed, and exhausted resets share one generic no-store failure.
- Authenticated password change accepts only current and new password, derives identity from the validated Bearer subject, and rejects IDOR/mass-assignment fields.
- The current password and same-as-current new password are verified through the existing Argon2id helper; the new value reuses the exact registration/reset policy.
- Successful password change locks the user row and atomically updates the Argon2id hash, invalidates valid same-user reset challenges, and revokes all same-user refresh sessions while preserving every other user's state.
- Password-change limits are five attempts per HMAC-keyed authenticated user and ten per actual connection peer per 15 minutes; forwarded headers are ignored.
- Password-change authority is the explicit Bearer header plus current-password proof, not an ambient cookie. Exact Origin validation is retained, while refresh/logout double-submit CSRF controls remain unchanged.
- Concurrent stale-password changes serialize on the MySQL user row and allow exactly one transition.
- Email-verification resend and verify derive identity only from the validated Bearer subject; request bodies cannot select an email or user.
- Email challenges are six ASCII digits stored only as `email-verification:v1` domain-separated HMAC-SHA256, become active only after confirmed delivery, expire after ten minutes, and have five durable attempts.
- Resend has a 60-second database cooldown and five-per-hour rolling cap plus peer/user HTTP limits; verification has peer/user HTTP limits and every 429 includes `Retry-After`.
- The development Fake Email inbox is authenticated-user scoped, HMAC-referenced, bounded, expiring, memory-only, actual-loopback-only, disabled by default, and absent from production.
- Successful verification atomically consumes the challenge and changes only `users.email_verified`; passwords, roles, phone state, account status, reset challenges, and refresh sessions are preserved.
- Concurrent correct verification yields exactly one success, concurrent wrong attempts have no lost increments, concurrent resend leaves at most one usable challenge, and delayed provider delivery cannot resurrect stale state.

## Phase 5E closure evidence

- The explicit phone/email/password-reset purpose-separation matrix permits only matching-purpose challenges.
- IDOR/BOLA, mass-assignment, account-state, JWT, CSRF/Origin, cookie, CORS, validation, logging, secret, fake-provider, transaction, and OWASP-targeted reviews are complete.
- Real HTTP/MySQL lifecycle passed registration, both verification channels, login, `/me`, refresh rotation, logout, reset, password change, logout-all, revocation, and exact synthetic cleanup.
- The twelve-case real-MySQL concurrency matrix passes, including reset/change/logout-all versus refresh; a deadlock victim rolls back safely and requires retry.
- One MEDIUM phone account-state defect and one LOW development dependency issue were fixed. No Critical, High, or unresolved Medium finding remains.
- Registration identifier enumeration remains an accepted LOW contract risk; stateless access-token lifetime and process-local limiting remain documented architecture residuals.
- Fresh browser automation was environment-blocked; no evidence was fabricated. The passing source/test audit and prior user-verified 7/7 Phase 4C browser gate remain the browser evidence.

## Phase 6 closure evidence

- One additive `user_profiles` migration passed upgrade, downgrade, upgrade-again, one-head, and drift checks against real MySQL.
- Own-profile reads/writes derive identity only from the ACTIVE bearer principal; 16 malicious mass-assignment fields are rejected.
- Incomplete and inactive profiles are hidden publicly; public responses exclude contact, internal ID, role, status, auth, and session data.
- Onboarding is server-authoritative and idempotent. Clearing a required field clears completion.
- First creation, update, onboarding, update-versus-completion, and rollback paths passed real-MySQL concurrency/integrity tests and five stress repetitions.
- The responsive frontend includes a small accessible design system, authenticated shell, onboarding, own profile, edit profile, and safe public profile.
- Private profile cache is user-scoped and removed at session clear; access/refresh token storage architecture is unchanged.
- A fresh real HTTP/MySQL Phase 6 lifecycle passed with exact synthetic cleanup. In-app browser automation remained environment-blocked and no result was fabricated.

## Tests and database state

- Backend: 597 passed, 0 failed, 0 skipped, 1 third-party deprecation warning.
- Phase 5E integrated suite: 11 passed and also passed five consecutive stress repetitions; phone account-state regression adds three status cases.
- Phase 5D focused security suite: 57 passed, covering cryptography, strict schemas, provider guards/failure, IDOR, mass assignment, cooldown/hour limits, HTTP limits, Fake Email isolation, rollback, session preservation, and real MySQL concurrency.
- Phase 5C focused security suite: 64 passed, including IDOR, strict validation, Argon2id, wrong/same password, session and reset isolation, rate limits, CSRF decision, rollback, sensitive data, and real MySQL concurrency.
- Pre-Phase 5C blocker suite: 16 passed, covering validation reflection, nested/extra sensitive input, safe metadata, no request-body logging, Docker ignore policy, Dockerfile secret patterns, and Compose runtime substitution.
- Frontend: 68 passed, 0 failed, 0 skipped.
- Frontend type check, lint, and production build pass.
- `pip check`, `pip-audit`, `npm audit`, and `npm audit --omit=dev` pass; Browserslist is pinned to patched `4.28.8` for the development/build graph.
- Development database baseline and final counts: users 4, user roles 4, phone codes 3, refresh tokens 7, reset codes 0, email verification codes 0.
- Phase 6 profile rows after synthetic cleanup: 0; orphan profiles and duplicate user/public profile identifiers: 0.
- Orphan roles, OTP rows, refresh rows, reset rows, and email-verification rows: 0. Refresh replacement-link and family-integrity checks also pass.

Every database test uses an outer transaction/savepoint and verifies exact counts plus pre-existing user/role identifiers after rollback. No broad deletion, truncation, schema reset, or legitimate-data modification is used.

## Authorization boundary

The backend establishes identity through a validated access token and current ACTIVE database state. Profile writes use only `/profile/me`; no client-supplied internal or public identifier grants write authority. Public identifiers are read-only lookup keys, not authorization credentials. Frontend guards remain navigation aids only; backend dependencies and service rechecks are the enforcement boundary.

## Known limitations

- Phase 4C real-browser verification passed using explicit user-provided evidence, not browser-tool evidence: no authentication token in LocalStorage or SessionStorage; refresh cookie `HttpOnly=true` and `Path=/api/v1/auth`; CSRF cookie `HttpOnly=false` and `Path=/`; F5 restored the authenticated session; logout and logout-everywhere both remained logged out after F5.
- Access tokens cannot be revoked before their 15-minute expiry in Phase 4A.
- Registration and login limiters are per process; production horizontal deployments require a shared limiter.
- Refresh, logout, and logout-all limiters are also per process.
- Password-change peer/user limiters are per process; production horizontal deployments require a shared limiter.
- Email-verification peer/user limiters and Fake Email delivery are process-local; production horizontal deployments require shared rate limiting and an approved real provider.
- Forgot-password peer/identifier limiters and fake delivery are process-local.
- Recovery timing uses a comparable dummy workload but cannot guarantee identical database/provider/network timing.
- A provider failure after old-code invalidation can temporarily deny recovery; no undelivered challenge becomes usable.
- A malicious party can exhaust a reset challenge's five attempts and temporarily deny recovery; a fresh Phase 5A challenge restores a new budget subject to cooldown/hour limits.
- Frontend refresh single-flight coordination is per tab, not cross-tab.
- Real Tencent Signature/Template approval and credentials remain unavailable.
- Production TLS, CSP, monitoring, secret rotation, and distributed rate limiting are deployment prerequisites.
- Docker image construction was not rechecked in Phase 4D because Docker CLI was unavailable.
- Dedicated local secret-scanner CLIs and fresh in-app browser automation were unavailable during Phase 5E; structural/pattern scanning and the prior manual browser gate were used without fabricating evidence.
- Registration duplicate conflicts disclose identifier existence and remain an accepted LOW API-contract risk.
- Same-account hostile MySQL races may select one request as a deadlock victim; rollback is atomic and the failed request must retry.
- Profile/onboarding rate limits are process-local; production horizontal deployments require shared storage.
- The six-city Phase 6 allow-list is intentionally small and will migrate to the managed Phase 8 city catalog.
- A third-party Starlette TestClient deprecation warning remains.

## Exact next step

Resolve the remaining dependency/runtime gate findings in the latest Phase 7 report before
claiming closure. Phase 8 requires a separate request; no products, search, chat, deals,
payments, external KYC or full administration dashboard is implemented here.
