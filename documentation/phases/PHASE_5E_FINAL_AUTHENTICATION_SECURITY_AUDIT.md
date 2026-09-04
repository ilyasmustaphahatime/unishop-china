# Phase 5E Final Authentication Security Audit

## Decision

- Phase 5E complete: YES
- Authentication subsystem closed: YES
- Ready for separately approved Phase 6 development: YES
- Production-code remediation required: YES, one minimal phone account-status check
- Migration required: NO
- Unresolved Critical/High/Medium findings: 0/0/0
- Phase 6 implementation added: NO

This is an engineering security review, not OWASP certification.

## Baseline

- Branch: `feature/authentication`
- Committed baseline: `634a545a78817bbddfe9a13be7d134395eea910a` (`feat: implement secure email verification`)
- Initial working tree: clean
- Initial branch relation: three commits ahead of `origin/feature/authentication`
- Git integrity: `git diff --check` and `git fsck --full` passed
- Backend baseline: 522 passed, one third-party Starlette deprecation warning
- Frontend baseline: 49 passed; TypeScript, ESLint, and production build passed
- MySQL: connected to `unishop_china`
- Alembic: current/head `d5f0c1e2a3b4`, one head, no drift

Baseline MySQL state:

| Table | Count | Safe ID fingerprint |
|---|---:|---|
| users | 4 | `1420b51076d7ca1f` |
| user_roles | 4 | `85157da8f3c427cd` |
| phone_verification_codes | 3 | `dd975b64c01ff4ad` |
| refresh_tokens | 7 | `769ae08d45b64710` |
| password_reset_codes | 0 | `e3b0c44298fc1c14` |
| email_verification_codes | 0 | `e3b0c44298fc1c14` |

All orphan, broken replacement, cross-user/cross-family replacement, duplicate refresh-hash, negative-attempt, and impossible email/reset/refresh state checks returned zero. Two old phone rows expire one second before `created_at`; both are intentional failed-delivery cancellation sentinels produced by `_expire_unsent_code`, not usable challenges or integrity corruption.

## Architecture reviewed

| Capability | Authority and principal security property | Result |
|---|---|---|
| Registration | strict identifiers/password; DB uniqueness; BUYER only; transactional user/role/challenge | PASS |
| Phone verification | phone-owned newest HMAC challenge; durable attempts/cooldown; ACTIVE required after Phase 5E fix | PASS |
| Email verification | bearer owner; pending delivery; active/newest HMAC challenge; atomic flag mutation | PASS |
| Login | normalized email/phone plus Argon2id; dummy unknown-user verification; ACTIVE only | PASS |
| Access JWT | HS256 allow-list; complete claims; canonical UUID subject; 15-minute life | PASS |
| `/me` | bearer subject with current MySQL status/roles | PASS |
| Refresh | opaque token hash, CSRF binding, rotation/reuse/family/absolute expiry | PASS |
| Logout | cookie+CSRF family revocation and cookie clearing | PASS |
| Logout-all | bearer principal; same-user session revocation; cookie clearing | PASS |
| Forgot password | generic response; pending provider delivery; HMAC challenge | PASS |
| Password reset | durable attempts; one-time/newest; atomic password/challenge/session changes | PASS |
| Password change | bearer+current password; row lock; atomic reset/session invalidation | PASS |

## Full real-runtime lifecycle

An actual Uvicorn server on loopback, real MySQL, real HTTP cookies, and development-only in-memory providers were used. Only one generated synthetic account was affected and it was removed by exact ID/email afterward.

| Step | Result |
|---|---|
| Register and initial state | PASS |
| Retrieve and verify phone challenge | PASS |
| Login | PASS |
| Retrieve and verify email challenge | PASS |
| `/auth/me` verification state | PASS |
| Refresh and persisted parent→child rotation | PASS |
| Logout and replay rejection | PASS |
| Login again | PASS |
| Forgot password and retrieve reset challenge | PASS |
| Reset; old password/old refresh rejected | PASS |
| Login with reset password | PASS |
| Authenticated password change | PASS |
| Previous password/pre-change refresh rejected | PASS |
| Login with final password | PASS |
| Logout-all and refresh rejection | PASS |
| Synthetic cleanup | PASS |

No raw credential, token, cookie, or challenge value was emitted in the audit result.

## JWT adversarial matrix

| Case | Result |
|---|---|
| Invalid/modified signature | rejected |
| Expired token | rejected |
| Wrong issuer/audience/type | rejected |
| Missing required claim | rejected |
| Empty or non-string JTI | rejected |
| Missing/malformed/non-canonical subject | rejected |
| Future `nbf` outside skew | rejected |
| Future `iat` outside skew | rejected |
| Unsupported algorithm | rejected |
| Unsigned `alg=none` | rejected |
| Refresh-like token as access | rejected |
| Arbitrary/malformed/empty bearer | rejected |

Token validation remains centralized in `AccessTokenService`; current status and roles are loaded from MySQL.

## Session, cross-user, property, and account-state matrices

Refresh/session results:

- initial rotation: one parent and one child with a valid replacement link;
- concurrent rotation: exactly one request returns a rotation; reuse revokes the family;
- expired/revoked/malformed refresh: rejected generically;
- missing/mismatched CSRF and malicious Origin: rejected before rotation;
- unrelated families and unrelated users: preserved;
- logout: family-scoped and idempotent;
- logout-all: bearer user-scoped; other users preserved;
- active-family cap and absolute family lifetime: enforced.

IDOR/BOLA attempts:

| Attempt | Result |
|---|---|
| User A verifies User B email challenge | rejected; bearer owner controls lookup |
| User A changes User B password | `user_id` rejected; bearer subject authoritative |
| User A revokes User B sessions | body identity rejected/not accepted; bearer subject authoritative |
| User A consumes User B email inbox message | owner-scoped lookup/delete fails |
| Phone/reset cross-user challenge guessing | only server-owned identifier/challenge relationship is consulted |

Mass-assignment attempts for `user_id`, roles, admin flags, account status, email/phone, verification flags, password hash, and nested unexpected values are rejected by strict schemas. No silent property mutation occurred.

Actual `AccountStatus` values are `ACTIVE`, `SUSPENDED`, `BANNED`, and `DELETED`. Login, `/me`, refresh, phone/email verification, forgot/reset password, and password change were reviewed. `ACTIVE` follows each endpoint's normal authority rules; every non-active state is denied or receives the intentionally generic forgot-password response without state mutation. The phone gap found during this matrix is fixed as AUTH-5E-001.

## Purpose-separation matrix

| Source | Phone Verify | Email Verify | Password Reset |
|---|---|---|---|
| Phone | PASS | rejected | rejected |
| Email | rejected | PASS | rejected |
| Reset | rejected | rejected | PASS |

The test uses distinct valid codes and one synthetic owner. Phone, email, and reset repositories/models are separate; reset and email additionally use explicit purpose-prefixed HMAC domains.

## Password and verification security

- Reset replay, expiry, supersession, attempt exhaustion, concurrency, and rollback: PASS.
- Reset versus refresh: a successful reset revokes every old/descendant refresh; a deadlock victim rolls back and reports failure.
- Change concurrency: one stale-current-password transition succeeds; the other fails.
- Reset versus change: exactly one credential authority wins; all reset/refresh state matches the winner.
- Change versus refresh: successful change revokes all descendants; a failed/deadlock-victim change commits nothing.
- Reset challenge invalidation after change: PASS.
- Phone wrong attempts, expiry, replay, newest-only, provider failure, and production fake-provider guard: PASS.
- Email wrong attempts, expiry, replay, supersession, pending/failed delivery, cross-user isolation, concurrent valid/invalid/resend/verify-versus-resend, and production guard: PASS.
- Email verification preserves password, roles, phone flag, status, reset records, and refresh sessions: PASS.

## CSRF, Origin, cookies, and CORS

| Endpoint group | Authority | Origin | Double-submit CSRF |
|---|---|---|---|
| register | submitted identifiers/password | not required; no ambient authority | no |
| phone resend/verify | phone/newest challenge | not required; no ambient authority | no |
| login | identifier/password | exact if present; missing allowed for API clients | no |
| `/me` | bearer | GET | no |
| email resend/verify | bearer | exact if present | no |
| forgot/reset | identifier/reset challenge | exact if present | no |
| password change | bearer + current password | exact if present | no |
| refresh | refresh cookie | exact if present | yes: cookie/header/stored hash |
| logout | refresh cookie | exact if present | yes: cookie/header/stored hash |
| logout-all | bearer | exact if present | no |

Malicious, lookalike, wrong scheme, wrong port, userinfo-style, malformed, and `null` Origin values are rejected where Origin policy applies. Missing Origin is intentionally permitted for non-browser clients. Rate limiters and local-only provider guards use `request.client.host`; forwarded headers cannot change the peer identity.

Cookie review:

| Property | Refresh | CSRF |
|---|---|---|
| HttpOnly | true | false, intentionally readable |
| SameSite | Lax | Lax |
| Development Secure | false for local HTTP | false for local HTTP |
| Production Secure | required true | required true |
| Path | `/api/v1/auth` | `/` |
| Domain | unset | unset |
| Deletion | matching name/path/security options | matching name/path/security options |

CORS uses explicit configured origins, credential mode, a narrow method/header list, and never `*`. Production adds no local development origin.

## Rate-limit inventory

| Endpoint | Peer limit | User/identifier limit | Durable control | `Retry-After` |
|---|---|---|---|---|
| register | 20/min | none | uniqueness | peer 429 |
| phone resend | none | 60s cooldown; 5/phone/hour | MySQL | cooldown 429; hourly may omit |
| phone verify | none | 5 attempts/challenge | MySQL | not guaranteed |
| email resend | 10/15m | 5/user/hour | 60s cooldown; 5/hour | every 429 |
| email verify | 20/15m | 10/user/15m | 5 attempts | every 429 |
| login | 5/min | 10/identifier/15m | none | every 429 |
| refresh | 20/min | 10/session/min | token/family state | every 429 |
| logout | 10/min | none | family state | every 429 |
| logout-all | none | 5/user/min | session state | every 429 |
| forgot password | 10/15m | 5/identifier/hour | 60s cooldown; 5/hour | every HTTP 429 |
| password reset | 10/15m | 5/identifier/15m | 5 attempts | every HTTP 429 |
| password change | 10/15m | 5/user/15m | current-password proof | every 429 |

All HTTP limiters are thread-safe, bounded, and process-local. Distributed production requires shared storage. Phone's durable per-number controls protect the currently disabled/real-provider-pending workflow; adding an actual production SMS provider should include a shared peer/cost limiter.

## Validation, logging, secrets, and providers

- Every auth schema forbids extra input.
- Strict ASCII codes prevent Unicode digit confusion.
- Identifier/password length/type constraints reject oversized or structured input.
- Sanitized validation responses never contain submitted sentinel values, raw `input`, unsafe `ctx`, exception repr, or Pydantic documentation URLs.
- Static/log-capture review found no password, challenge, Authorization header, access/refresh token, cookie, CSRF value, HMAC, request body, or environment-secret logging.
- Errors return safe generic detail without provider/database exception text.
- Real `.env` files are ignored/untracked; `.env.example` contains placeholders only.
- Backend `.dockerignore` excludes environment files, VCS, tests, caches, logs, virtual environments, and private/runtime uploads.
- No tracked private-key/token pattern was found. `gitleaks`, `trufflehog`, and `detect-secrets` were unavailable, so local structural/pattern scanning plus dependency/security tests were used.
- Fake SMS/email/reset stores are bounded, expiring, process-memory only, actual-loopback guarded, development only, and absent from production OpenAPI. Forwarded headers cannot bypass the peer check.

## Transaction ownership and failure injection

| Operation | Transaction owner and atomicity |
|---|---|
| Registration | registration service owns user/BUYER/phone-row transaction; provider call follows commit; failed delivery expires only its code |
| Phone verification | service owns locked user/challenge transaction |
| Email verification | service owns pending creation, post-delivery activation/cancellation, and locked verification transactions |
| Login | authentication service owns login session creation with locked user |
| Refresh | refresh service owns row-locked rotation/reuse/revocation transaction |
| Logout/logout-all | refresh service owns family/user revocation transaction |
| Forgot password | request service owns pending/activation transactions around delivery |
| Password reset | completion service owns password, challenge, and session revocation transaction |
| Password change | change service owns locked password/reset/session transaction |

Repositories flush/execute parameterized SQLAlchemy statements and do not commit. Service-level commits are deliberate where an authentication dependency has already opened a read transaction.

Injected failures passed for registration role/code persistence, phone user/code update, email provider/activation/verification, refresh replacement creation, password-reset password/consume/invalidate/session steps, and password-change password/reset/session steps. Every required state mutation rolled back together.

## Real MySQL concurrency results

| # | Race | Result |
|---:|---|---|
| 1 | concurrent refresh | PASS; one rotation, family revoked on reuse |
| 2 | refresh reuse | PASS; compromised family revoked |
| 3 | concurrent password reset | PASS; exactly one success |
| 4 | concurrent password change | PASS; exactly one stale-password transition |
| 5 | reset vs refresh | PASS; successful reset leaves no refresh authority; deadlock victim rolls back |
| 6 | change vs refresh | PASS; successful change leaves no refresh authority; deadlock victim rolls back |
| 7 | reset vs change | PASS; exactly one credential authority wins |
| 8 | concurrent email verify | PASS; exactly one success |
| 9 | concurrent invalid email attempts | PASS; no lost increments |
| 10 | concurrent email resend | PASS; at most one usable challenge |
| 11 | email verify vs resend | PASS; delayed delivery cannot resurrect stale state |
| 12 | logout-all vs refresh | PASS; successful logout-all leaves no descendant; safe retry after deadlock victim |

The new Phase 5E cross-feature suite passed five consecutive runs.

## OpenAPI and frontend

- Current OpenAPI: 13 authentication operations, each exactly once.
- Production OpenAPI: 13 authentication operations, zero development-provider routes.
- No Phase 6 route was added by Phase 5E.
- No duplicate method/path pair exists.
- Frontend access token/user state is memory-only.
- No source use of LocalStorage, SessionStorage, or IndexedDB stores auth state.
- JavaScript reads only the CSRF cookie; the refresh cookie is HttpOnly.
- Credentialed session calls, centralized bearer injection, one-retry bound, per-tab single-flight refresh, failed-refresh cleanup, query-cache cleanup, and safe internal redirects remain intact.
- Frontend route guards are explicitly UX-only.

Fresh in-app browser automation was `ENVIRONMENT BLOCKED` because the browser connection was unavailable. No evidence was fabricated. The audit therefore relies on source/tests and the previously recorded user-verified 7/7 Phase 4C browser gate: empty LocalStorage/SessionStorage, correct refresh/CSRF attributes, F5 restoration, and logout/logout-all persistence after F5.

## Dependency and OWASP targeted review

- `pip check`: PASS
- `pip-audit`: no known vulnerabilities
- `npm audit`: initially found transitive dev-only Browserslist advisories; fixed at 4.28.8; final zero
- `npm audit --omit=dev`: zero before and after

OWASP API Security Top 10 2023 review:

- API1 BOLA: bearer/challenge ownership matrices pass.
- API2 Broken Authentication: password, JWT, refresh, recovery, replay, and account-state controls pass after AUTH-5E-001.
- API3 Broken Object Property Level Authorization: strict schemas/mass-assignment tests pass.
- API4 Unrestricted Resource Consumption: bounded local/durable limits exist; shared production limiting remains required.
- API5 Broken Function Level Authorization: roles are server-loaded; auth endpoints do not grant elevated roles.
- API7 SSRF: no user-controlled provider URL or fetch target exists in this scope.
- API8 Security Misconfiguration: production secret/cookie/provider/CORS guards pass.
- API9 Improper Inventory Management: exact OpenAPI inventory passes.
- API10 Unsafe Consumption of APIs: provider errors are categorized/sanitized and failed delivery cannot activate challenges.

Relevant OWASP ASVS 5.0 architecture, authentication, session, access control, validation, cryptography, error/logging, data protection, communication/configuration, and API-security controls were reviewed. No certification claim is made.

## Findings, warnings, and residual risks

The full finding register is in `documentation/security/PHASE_5E_SECURITY_FINDINGS.md`.

- AUTH-5E-001 MEDIUM: fixed and tested.
- AUTH-5E-002 LOW: fixed and dependency audits clean.
- AUTH-5E-003 LOW: accepted registration enumeration residual.
- AUTH-5E-004 INFO: accepted atomic MySQL retry behavior.

Non-blocking warnings/residuals:

1. stateless access JWT residual lifetime;
2. process-local HTTP limits and per-tab refresh coordination;
3. production SMS/email providers not integrated;
4. production TLS/proxy/monitoring/secret operations remain deployment work;
5. delayed external messages may arrive after cancellation but remain unusable;
6. Starlette TestClient deprecation warning;
7. Docker CLI and dedicated secret scanners were unavailable;
8. fresh browser automation environment blocked; prior manual evidence retained.

## Closure gate

All required automated/backend/frontend/database/Alembic gates pass, legitimate database data is preserved, no migration exists, no Critical/High or unresolved Medium finding remains, and no Phase 6 feature was implemented.

Authentication is sufficiently verified to close Phases 1–5. UniShop China may begin separately approved Phase 6 work without changing the authentication architecture first.
