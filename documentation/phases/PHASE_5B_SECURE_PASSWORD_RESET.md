# Phase 5B: Secure Password Reset

Completion date: 2026-08-21

Branch: `feature/authentication`

Baseline: `6ace68f`

Previous Alembic revision: `c91e4a7b2d6f`

Phase 5B Alembic revision: `aca2dda0ef53`

## Scope and outcome

Phase 5B implements the unauthenticated possession-factor completion step for the Phase 5A forgot-password flow. It adds durable per-challenge incorrect-attempt tracking and `POST /api/v1/auth/password/reset`. It does not add a logged-in change-password flow, email verification, a frontend recovery implementation, production message delivery, an access-token blacklist, Phase 5C, or marketplace features.

Successful reset returns only:

```json
{
  "message": "Password has been reset successfully. Please sign in again."
}
```

It does not issue an access token, refresh token, cookie, user object, or automatic login. Invalid, unknown, inactive, expired, superseded, consumed, wrong, and exhausted requests share HTTP 400 with:

```json
{
  "detail": "Invalid or expired password reset request."
}
```

Sensitive reset responses use `Cache-Control: no-store` and `Pragma: no-cache`.

## Approved migration

The approved migration is deliberately limited to `password_reset_codes`:

- `attempts INTEGER NOT NULL DEFAULT 0`
- `CHECK (attempts >= 0)` named `ck_password_reset_codes_attempts_non_negative`

No other table, column, key, index, constraint, or data was changed. The ORM model uses the same integer, defaults, nullability, and named constraint. The migration upgraded successfully, passed a safe `aca2dda0ef53 -> c91e4a7b2d6f -> aca2dda0ef53` round trip while the reset table was empty, and preserved all unrelated table counts. Alembic reports one head and no drift.

## Request validation and normalization

`ResetPasswordRequest` strictly accepts:

```json
{
  "identifier": "email or Mainland China phone",
  "code": "123456",
  "new_password": "NewStrongPassword456"
}
```

Extra fields are forbidden. The schema does not accept user IDs, roles, admin state, password hashes, attempt state, consumption timestamps, session IDs, or authorization state.

The identifier uses the shared Phase 5A/login email and Mainland China phone normalization. The code uses the existing `AsciiCode` contract and accepts exactly six ASCII digits; whitespace, letters, incorrect lengths, Arabic-Indic digits, and fullwidth digit lookalikes are rejected. The new password uses the exact registration password policy: 8-128 characters with uppercase, lowercase, and digit requirements. Values are never silently truncated.

The project has no existing policy forbidding reuse of the current password, so Phase 5B does not invent a reset-only inconsistency. A valid challenge may set the same policy-compliant password again.

## Reset verification

The service resolves and locks the normalized ACTIVE user, selects only that user's newest challenge using `SELECT ... FOR UPDATE`, and checks server-side UTC expiry, `used_at`, and the durable attempt budget. Suspended, banned, deleted, and unknown accounts use a dummy user/challenge workload and are never reactivated.

The submitted code is processed by the Phase 5A domain-separated HMAC-SHA256 helper. Comparison uses `hmac.compare_digest`. MySQL never stores or compares a raw code. Expired, consumed, superseded, pending, or exhausted challenges cannot be revived.

Argon2id work is performed for every schema-valid request, including unknown and ineligible identifiers, so those paths do not skip the dominant password work. Timing cannot be guaranteed identical across database/cache/lock states, but the architecture avoids the most direct account-existence shortcut.

## Durable attempt policy

- Initial attempts: 0.
- Maximum: configurable, default and tested value 5, bounded to 1-10.
- Incorrect code: atomic conditional database increment.
- Correct code: does not increment attempts.
- Fifth incorrect request changes attempts from 4 to 5.
- At attempts 5, even the correct code fails.
- A newer Phase 5A challenge starts with attempts 0 and a fresh budget.

The user and newest challenge rows are locked. The increment also requires the exact challenge/user, unconsumed state, unexpired state, and `attempts < maximum` in its SQL `WHERE` clause. This gives durable, multi-process, race-safe accounting and prevents lost increments or exceeding the security budget. Seven concurrent wrong requests produced exactly five stored attempts and zero success.

## Atomic reset transaction

`PasswordResetCompletionService` owns the transaction. Repositories contain parameterized SQLAlchemy operations and never commit independently.

Within one transaction the service:

1. locks and validates the eligible user and newest challenge;
2. performs HMAC verification and checks expiry/consumption/attempt state;
3. derives the new Argon2id password hash;
4. updates the user's password hash;
5. conditionally consumes the exact challenge;
6. marks all other active reset challenges for that user used;
7. invokes the existing Phase 4B `RefreshTokenRepository.revoke_all_for_user()` path;
8. commits.

Password-update, challenge-consumption, other-challenge-invalidation, and refresh-revocation failures were injected separately. Every failure rolled back the password, reset rows, and refresh rows together. No partial credential/session state remained.

## Replay and concurrency

A consumed code fails on replay, even with the same identifier, code, and new password. Reset selects only the newest challenge, so an older challenge cannot succeed. On success, all other unconsumed challenges for that user are invalidated without affecting another user.

User and challenge row locks provide the cross-process race boundary. Two real concurrent MySQL sessions using the same valid challenge produced exactly one success and one generic failure. The challenge was consumed once and the resulting password was deterministic.

## Refresh-session revocation

Successful reset revokes every currently usable refresh row belonging to the reset user through the existing Phase 4B repository. The allowed existing `logout_all` revocation reason is reused; no duplicate session architecture or unrelated schema change was introduced. Already-rotated/revoked ancestors remain unusable. Other users' refresh sessions remain unchanged.

Tests verify two independent refresh families are revoked, an unrelated user's family remains active, and an old raw refresh token receives HTTP 401 after reset. The user must perform a normal login with the new password. The old password fails and the new password succeeds.

Existing access JWTs are stateless and can remain usable until their approximately 15-minute expiry. Phase 5B intentionally adds no access-token blacklist.

## Rate limiting

- Connection peer: 10 reset attempts per 15 minutes.
- Normalized identifier: 5 reset attempts per 15 minutes using an HMAC-protected key.
- Storage: bounded expiring `InMemoryRateLimiter` maps.
- Excess response: HTTP 429 with `Retry-After`, no-store, and no account state.
- Peer source: actual connection peer; `X-Forwarded-For` is ignored.

These endpoint limits complement, but do not replace, the durable five-attempt challenge counter. They remain process-local and require a reviewed distributed store before horizontal production scaling.

## Enumeration and error safety

Unknown account, inactive account, wrong code, expired code, superseded code, consumed code, and exhausted code return the same public 400 response. Rate-limit responses are account-independent. Unexpected failures return one safe 500 message without provider, database, hash, account, or stack detail.

The implementation performs no new logging or printing. Tests and source review found no plaintext password, password hash, reset code/hash, token, cookie, CSRF value, Authorization header, full identifier, database secret, or provider secret in logs or public responses.

## CSRF decision

Password reset is an unauthenticated recovery endpoint authorized by the reset possession factor, not by a refresh cookie. Requiring the authenticated-session double-submit CSRF token would incorrectly make an existing session part of reset authority and would block users who need recovery precisely because they cannot authenticate.

The endpoint therefore does not consume or trust a refresh cookie and does not require the Phase 4B CSRF token. It applies exact allowed-Origin validation when an Origin header is present, strict schema validation, HMAC verification, durable attempts, and peer/identifier rate limits. A cross-origin request with a foreign Origin is rejected without incrementing challenge state.

## Database and verification evidence

Counts before migration/tests and after all tests are identical:

| Table | Before | After |
|---|---:|---:|
| `users` | 4 | 4 |
| `user_roles` | 4 | 4 |
| `phone_verification_codes` | 3 | 3 |
| `refresh_tokens` | 6 | 6 |
| `password_reset_codes` | 0 | 0 |

Orphan roles, phone codes, refresh rows, and reset rows are zero. Transactional tests use the project savepoint fixture. Real concurrency tests create UUID-scoped users, delete only their captured exact user IDs, rely on foreign-key cascades for owned rows, and verify exact baseline restoration.

Final evidence:

- Phase 5A+5B focused: 102 passed.
- Full backend: 385 passed, zero failed; one third-party Starlette TestClient deprecation warning.
- Frontend: 49 passed; direct TypeScript, lint, and production build passed.
- Ruff, compile, import, `pip check`, and `pip-audit`: passed; no known Python dependency vulnerabilities.
- `npm audit` and `npm audit --omit=dev`: zero vulnerabilities.
- MySQL health: passed.
- Alembic current/head: `aca2dda0ef53`; drift none.

## OWASP engineering review

This is not certification or a formal compliance claim.

- OWASP API2 Broken Authentication: possession-factor verification, newest-only state, expiry, durable attempts, single use, Argon2id, and refresh revocation.
- API4 Unrestricted Resource Consumption: bounded peer/identifier limits and durable per-challenge attempts.
- API6 Unrestricted Access to Sensitive Business Flows: reset spam/brute-force controls and generic failures.
- API8 Security Misconfiguration: validated secret/provider baseline and narrowly reviewed migration.
- API10 Unsafe Consumption of APIs: no production message provider was added; Phase 5A provider failures remain contained.
- ASVS 5.0 focus areas reviewed: recovery, password storage, session invalidation, cryptography, validation, errors, logging, concurrency, and transaction integrity.

## Residual risks

1. Existing access JWTs remain valid for up to their short expiry after reset.
2. Endpoint rate-limit maps are process-local; durable attempts remain database-backed.
3. A malicious party with a valid identifier can exhaust a challenge in five guesses, creating temporary recovery denial of service; a fresh Phase 5A challenge restores the budget subject to its cooldown/hour limit.
4. Six-digit codes depend on expiry, rate limits, durable attempts, HMAC-secret custody, and delivery-channel security.
5. Timing is structurally balanced with dummy lookup/HMAC/Argon2id work but cannot be guaranteed identical under all database and network conditions.
6. Production TLS, managed secrets, monitoring/alerting with redaction, distributed rate limiting, and real provider review remain deployment prerequisites.

## Phase 5C handoff

Phase 5B is complete. Phase 5C is **NOT STARTED**. Any separately approved Phase 5C must preserve Phase 5A enumeration controls, Phase 5B attempt/replay/session invariants, current Argon2id and HMAC helpers, no-store responses, backend-authoritative authentication, and strict test isolation.

