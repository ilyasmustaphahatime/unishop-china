# Phase 4D: Final Authentication Security Audit

Audit window: 2026-08-20 to 2026-08-21

Repository: `unishop-china`

Branch: `feature/authentication`

Required and audited HEAD: `a9f5bbec39a192dbab7408ae2be01dc350acc3e1`

Alembic revision: `c91e4a7b2d6f`

## Outcome

**Overall status: PASSED WITH NON-BLOCKING WARNINGS.**

- Phase 4D complete: **YES**.
- Phase 1-4D authentication foundation complete: **YES**.
- Security regression passed: **YES**.
- Critical/high unresolved authentication defects: **NONE**.
- Ready for a separately approved Phase 5: **YES**.
- Phase 5 or marketplace functionality introduced: **NO**.

This was a source, configuration, automated-test, live-development-database, dependency, and documentation audit. It was not a penetration test, an external assessment, or an OWASP ASVS certification.

## Scope and boundaries

The audit covered registration, password handling, roles, phone verification, local Fake SMS, login, access JWTs, `/auth/me`, refresh sessions, cookies, CSRF, session-family rotation/reuse, concurrency, session limits, logout, logout-all, frontend session state, route guards, cache isolation, CORS/origin handling, rate limiting, configuration safety, secrets, database integrity, Alembic, dependencies, and the existing browser evidence.

Password recovery/change, email verification, OAuth, MFA, passkeys, session-device management, Redis, real Tencent SMS, seller verification, marketplace APIs, and deployment infrastructure remained outside scope and were not implemented.

## Architecture reviewed

The active backend path remains coherent:

`auth routes -> Pydantic schemas/dependencies -> authentication, phone-verification, refresh-session and token services -> SQLAlchemy repositories -> five authentication models`

Cross-cutting security remains centralized in configuration validation, Argon2id/HMAC helpers, access-token validation, refresh/CSRF generation and hashing, cookie helpers, rate limiting, database session ownership, and UTC helpers. There is one active authentication service, refresh-session service, cookie helper, rate limiter implementation, and auth router. SQLAlchemy expressions bind request data; no request-derived formatted SQL was found. Runtime code contains no `create_all`, `drop_all`, table drop, or truncate operation.

The active frontend path remains:

`components and route guards -> auth workflows/contracts -> normal and session Axios clients -> one in-memory Zustand store`

There is one active store, one refresh single-flight coordinator, one bootstrap coordinator, and one CSRF-cookie reader. Placeholder scaffold modules contain no competing implementation. The normal client adds the current bearer token dynamically; only the session client uses credentials. Backend authorization remains authoritative and `RoleRoute` is explicitly a UI/navigation aid.

## Git, environment, and secrets

- Preflight repository, branch, HEAD, clean-tree, log, and `git fsck --full` gates passed.
- `backend/.env` and `frontend/.env` are ignored and neither is tracked.
- Both real environment files and both examples have no duplicate keys.
- Local development flags are guarded: Fake SMS is explicit, development-only, and loopback-only; production startup rejects it.
- Production startup rejects missing, weak, or placeholder JWT secrets, non-HS256 algorithms, insecure refresh cookies, invalid SameSite/cookie names/paths, invalid lifetime ordering, wildcard credentialed CORS, and Fake SMS/Fake inbox enablement.
- The tracked-file scan examined 493 files. Its 27 strong-pattern matches were all clearly synthetic test fixtures; runtime/source and documentation contained no real credential finding.
- No tracked environment backup, private key, credential dump, token dump, database dump, or production credential was found.
- No credential rotation is required from this audit.
- AST/source scans found no runtime logging call that includes a password, OTP, access/refresh token, CSRF value, cookie, authorization value, JWT secret, database URL, database password, or personal document.

## Executable quality evidence

### Backend

| Gate | Result |
|---|---|
| Compile `app` | Pass |
| Import `app.main:app` | Pass |
| Ruff over app/tests/Alembic/scripts | Pass |
| `pip check` | Pass |
| `pip-audit` | Pass; no known vulnerabilities |
| Collection | 283 tests |
| Full suite | 283 passed, 0 failed, 0 skipped |
| Warning | One third-party Starlette `TestClient` deprecation warning |

Phase 4D added explicit negative JWT regression coverage for every required claim, an empty JTI, unsigned `alg=none`, and a token signed with an unsupported algorithm. It did not change production authentication code.

### Frontend

| Gate | Result |
|---|---|
| Direct TypeScript project check | Pass |
| Existing ESLint script | Pass |
| Existing Vitest script | 49 passed in 8 files; 0 failed |
| Existing production build (`tsc -b && vite build`) | Pass |
| `npm audit` | 0 vulnerabilities |
| `npm audit --omit=dev` | 0 runtime vulnerabilities |
| Production-bundle sensitive-key/Fake-SMS scan | Pass |

`package.json` has no standalone `typecheck` script. Direct `tsc -b` and the existing TypeScript-backed build both passed, so this is a non-blocking developer-tooling gap rather than a type-safety failure. The production bundle contained neither the local Fake SMS development module/route nor backend-only secret key names.

Docker CLI was unavailable, so image construction and Compose rendering were not re-executed. Existing Dockerfile command-format regression tests passed; the unavailable CLI is an accepted audit limitation.

## Database and Alembic

MySQL connection and `scripts/check_database.py` passed against `unishop_china`. The same validated `mysql+pymysql` URL is used by SQLAlchemy and Alembic; the engine uses `pool_pre_ping=True`.

Baseline and post-audit counts were identical:

| Table | Before | After |
|---|---:|---:|
| `users` | 4 | 4 |
| `user_roles` | 4 | 4 |
| `phone_verification_codes` | 3 | 3 |
| `refresh_tokens` | 6 | 6 |
| `password_reset_codes` | 0 | 0 |

All of these checks returned zero: orphan roles, orphan OTP rows, orphan refresh rows, orphan reset rows, duplicate refresh hashes, invalid/self/cross-family/cross-user replacement links, refresh expiry beyond family expiry, null family IDs, and null CSRF hashes. Synthetic live-flow rows were deleted only by their captured user IDs; cascading foreign keys removed their dependent rows. Legitimate rows and counts were preserved.

Model/schema checks passed for primary keys, required columns, unique email and phone, composite user-role uniqueness, non-negative OTP attempts, unique refresh hashes, user cascades, replacement `SET NULL`, refresh-family indexes, expiry indexes, account status, and refresh revocation-reason constraints. Password, OTP, reset, refresh, and CSRF fields store hashes rather than raw secrets.

Alembic passed `current`, `heads`, `history`, and `check`:

`<base> -> a75289cfd4a9 -> c91e4a7b2d6f (head)`

There is one head, the database is current, no drift exists, and Phase 4D created no migration.

## Phase-by-phase security result

### Phase 1: authentication database

Pass. All five authentication models match the two migrations and live schema. Foreign keys and cascades are scoped, refresh replacement links are constrained, hash uniqueness is enforced, and no runtime schema mutation exists.

### Phase 2: registration and passwords

Pass. Tests and live flows cover email-only, phone-only, and combined registration; normalized lowercase email; Chinese E.164 phone normalization; strict unknown-field rejection; bounded inputs; Argon2id hashing; automatic `BUYER` only; duplicate defenses; safe transaction rollback; safe error responses; and connection-peer registration limiting with `Retry-After`. Password whitespace is preserved and login intentionally does not apply newer registration-strength rules to existing accounts. Unknown-user login executes a dummy Argon2 verification path.

### Phase 3A: phone verification

Pass. OTPs are six ASCII digits generated with `secrets`, persisted only as HMAC-SHA256, expire after ten minutes, allow at most five wrong attempts, enforce resend cooldown and hourly limits, use newest-code-only behavior, and update the code/user atomically. Unknown-phone behavior is generic. Provider failures expose safe errors and leave no usable unsent code. No raw OTP appears in normal APIs, database rows, or logs.

### Phase 3B: local Fake SMS

Pass. The provider and inbox require explicit development configuration, use process memory only, enforce a bounded expiring store, delay availability, supersede old messages, consume successful messages, and validate the actual peer as loopback. Forged forwarding headers do not bypass the peer check. Production simulation removes the routes/OpenAPI entry and forces debug off. No Tencent call or real SMS occurred.

### Phase 4A: login, JWT, and `/auth/me`

Pass. Email/phone login normalization, Argon2id, dummy hashing, generic unknown/wrong/inactive responses, safe cookies-after-commit behavior, peer and HMAC-identifier rate limits, and forwarded-header rejection are covered.

Access JWTs use HS256, a 15-minute lifetime, issuer `unishop-china-api`, audience `unishop-china-web`, and 30-second configured skew. `sub`, `type`, `jti`, `iss`, `aud`, `iat`, `nbf`, and `exp` are mandatory. Expired, malformed, modified, wrong-signature, wrong-issuer/audience/type, missing-claim, invalid-subject, empty-JTI, unsigned, and unsupported-algorithm cases are rejected. Tokens contain no roles, password, OTP, refresh token, or sensitive profile document.

`/auth/me` requires Bearer authentication, reloads the user and roles from the database, rechecks active status, does not accept a client-selected user ID, and returns only its strict safe schema. Failures include `WWW-Authenticate: Bearer`.

### Phase 4B: refresh sessions, cookies, CSRF, and logout

Pass. Refresh tokens use 512 bits of pre-encoding randomness and are stored only as SHA-256 hashes. Each row has a UUID family, bound CSRF hash, seven-day individual expiry, unchanged 30-day absolute family expiry, and a maximum of ten active families per user. The oldest family is revoked at the limit.

The refresh cookie is `HttpOnly`, path `/api/v1/auth`, SameSite Lax, domain unset, and required Secure outside development. The readable CSRF cookie uses path `/`, SameSite Lax, domain unset, and the same Secure policy. Set/delete paths match and maximum age is bounded by token/family expiry.

Refresh and current-session logout validate exact Origin when present, use double-submit cookie/header comparison in constant time, and bind the submitted CSRF value to the database hash. Rotation issues new refresh and CSRF values only after a successful commit. Row locking, nested collision handling, bounded retry, replacement linking, rollback behavior, reuse-family revocation, deterministic concurrent refresh, and user/family isolation all passed.

Current logout is CSRF protected, idempotent, family-scoped, clears cookies, and returns an empty 204. Logout-all derives its target only from the access token, revokes all current-user families, preserves other users, clears cookies, and returns an empty 204. An already-issued access JWT may remain valid for at most 15 minutes.

### Phase 4C: frontend authentication

Pass. Access token and safe user remain only in the non-persistent Zustand store. Source scans found no localStorage, sessionStorage, IndexedDB, persistence middleware, XSS-sensitive sink, or console logging in frontend source. JavaScript does not read the HttpOnly refresh token; it reads only the CSRF cookie when needed.

Tests cover login, bootstrap, `/auth/me`, dynamic bearer injection, one bounded retry, refresh failure, five-request single-flight success and failure, rotated CSRF reads, protected/guest/role guards, internal redirect validation, logout, logout-all, and private query-cache removal. Role routing remains UI-only. External, scheme-relative, script/data, and backslash redirect forms are rejected.

Existing browser evidence remains **USER-VERIFIED 7/7 PASS**: LocalStorage, SessionStorage, refresh-cookie flags/path, CSRF-cookie flags/path, F5 restoration, logout plus F5, and logout-all plus F5. The audit did not downgrade this evidence or claim it was browser-automation evidence.

## Live end-to-end and isolation evidence

Unique synthetic development accounts completed:

- email register -> login -> `/auth/me` -> refresh -> logout;
- phone register -> local Fake SMS retrieval -> manual verify -> login -> `/auth/me`;
- A -> B -> C rotation -> replay A -> whole compromised family revoked;
- new family -> logout;
- two families -> logout-all -> both rejected;
- User A family 1 and family 2 plus User B family 1;
- replay of A family 1 without impact to A family 2 or User B;
- logout of A family 2 without impact to User B;
- logout-all for User A without impact to User B.

No password, OTP, JWT, refresh token, CSRF value, cookie, hash, or row content was printed. Exact cleanup restored all five table counts to baseline.

## Findings and non-blocking warnings

No production-code security defect was confirmed.

1. **Resolved test-evidence gap, informational:** crafted JWT cases for all missing claims, empty JTI, `alg=none`, and unsupported signing algorithm are now explicit negative regressions. Production code already rejected them.
2. **Third-party warning:** Starlette's current `TestClient` path emits one deprecation warning. It does not affect runtime authentication.
3. **Tooling warning:** Docker CLI was unavailable, so Docker/Compose runtime construction was not revalidated.
4. **Tooling warning:** no standalone frontend `typecheck` npm script exists; direct TypeScript and production build gates pass.

## Accepted residual risks

1. Issued access JWTs remain valid for up to 15 minutes after logout or logout-all.
2. All rate limiting is process-local and must become distributed before horizontal production scaling.
3. Frontend refresh single-flight is per tab; cross-tab refresh races remain possible and backend reuse detection is the safety boundary.
4. Real Tencent SMS is pending and remained disabled; no production SMS delivery was validated.
5. Production TLS, CSP, monitoring, secret rotation, alerting, and distributed rate limiting are deployment prerequisites, not present audit controls.
6. Docker image construction remains unverified because the Docker CLI was unavailable.

The first three are accepted MVP architecture limitations, the fourth is deferred integration scope, and the final two are deployment/tooling prerequisites. None is a critical/high Phase 4D authentication blocker in the current development scope.

## Production prerequisites

Before production, provide secrets through a managed secret store, enable Secure cookies behind TLS, retain an explicit same-site origin topology or deliberately redesign cookie/CORS/CSRF policy, deploy CSP and broader XSS hardening, replace process-local limits with a distributed store, establish authentication security logs/metrics/alerts without sensitive values, approve and test the real SMS provider, define secret rotation and incident response, and validate hardened production images/infrastructure.

## Phase 5 handoff

The Phase 1-4D foundation is suitable for a separately approved Phase 5 covering forgot/reset/change password, email verification/resend, and refresh-session revocation after password change. Phase 5 must continue using server-derived identity, strict schemas, generic recovery responses, hashed single-use recovery material, rate limits, transaction ownership, current session-family revocation, and negative object/function authorization tests.

**READY FOR PHASE 5: YES.**

## Phase 4D files

Created:

- `documentation/phases/PHASE_4D_FINAL_AUTHENTICATION_AUDIT.md`
- `documentation/security/PHASE_4D_AUTHENTICATION_SECURITY_REVIEW.md`

Modified:

- `backend/tests/unit/test_access_tokens.py`
- `backend/tests/unit/test_project_foundation.py`
- `documentation/CURRENT_PROJECT_STATUS.md`
- `documentation/phases/PHASE_3_PHONE_VERIFICATION.md`
- `documentation/phases/PHASE_4C_FRONTEND_AUTHENTICATION.md`

All Phase 4D changes are intentionally unstaged and uncommitted.
