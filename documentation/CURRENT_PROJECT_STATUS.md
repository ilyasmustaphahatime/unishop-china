# UniShop China Current Project Status

## Authentication phases

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
- Phase 5E: not started.
- Phase 1-5D authentication foundation: complete.
- Ready for separately approved Phase 5E planning: yes.
- Protected marketplace object/function authorization: not started.

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
- Alembic current and head are `d5f0c1e2a3b4`; no schema drift exists.
- Authentication tables are `users`, `user_roles`, `refresh_tokens`, `phone_verification_codes`, `password_reset_codes`, and `email_verification_codes`.
- Strict Pydantic schemas reject unknown and privileged registration fields.
- Global validation-error sanitization prevents passwords, reset/verification codes, tokens, secrets, and nested submitted values from being reflected in HTTP 422 responses while retaining safe field metadata.
- Passwords use Argon2id; OTP values use HMAC-SHA256 and constant-time comparison.
- Registration assigns only the `BUYER` role.
- Phone resend retains its cooldown/hourly limits and verification retains its five-attempt limit.
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

## Tests and database state

- Backend: 522 passed, 0 failed, 0 skipped, 1 third-party deprecation warning.
- Phase 5D focused security suite: 57 passed, covering cryptography, strict schemas, provider guards/failure, IDOR, mass assignment, cooldown/hour limits, HTTP limits, Fake Email isolation, rollback, session preservation, and real MySQL concurrency.
- Phase 5C focused security suite: 64 passed, including IDOR, strict validation, Argon2id, wrong/same password, session and reset isolation, rate limits, CSRF decision, rollback, sensitive data, and real MySQL concurrency.
- Pre-Phase 5C blocker suite: 16 passed, covering validation reflection, nested/extra sensitive input, safe metadata, no request-body logging, Docker ignore policy, Dockerfile secret patterns, and Compose runtime substitution.
- Frontend: 49 passed, 0 failed, 0 skipped.
- Frontend type check, lint, and production build pass.
- Development database baseline and final counts: users 4, user roles 4, phone codes 3, refresh tokens 7, reset codes 0, email verification codes 0.
- Orphan roles, OTP rows, refresh rows, reset rows, and email-verification rows: 0. Refresh replacement-link and family-integrity checks also pass.

Every database test uses an outer transaction/savepoint and verifies exact counts plus pre-existing user/role identifiers after rollback. No broad deletion, truncation, schema reset, or legitimate-data modification is used.

## Authorization boundary

The backend now establishes identity through a validated access token and protects `/api/v1/auth/me`. There is still no marketplace object API in scope, so object-level authorization cannot truthfully be marked implemented. Frontend route guards remain navigation aids only. Future protected endpoints must add deny-by-default function and object authorization on top of `get_current_user()`.

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
- A third-party Starlette TestClient deprecation warning remains.

## Exact next step

Phase 5D is complete and all security/regression gates pass. Phase 5E remains not started and requires separate approval and scope definition. Email changing, a production email provider, recovery UI expansion, MFA, OAuth, passkeys, password history, and marketplace features remain outside the completed scope.
