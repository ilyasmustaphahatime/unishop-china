# Phase 5C: Secure Authenticated Password Change

Completion date: 2026-08-22

Branch: `feature/authentication`

Baseline: `3b914c6`

Alembic revision before and after: `aca2dda0ef53`

## Scope and outcome

Phase 5C adds only the authenticated password-change operation at `POST /api/v1/auth/password/change`. It does not add email verification, Phase 5D, MFA, OAuth, passkeys, password history, profile/account management, marketplace authorization, or frontend redesign.

No migration was required. The existing `users.password_hash`, `password_reset_codes`, and `refresh_tokens` schema supports the complete operation. The existing allowed `logout_all` refresh-revocation reason is reused.

The success contract is minimal:

```json
{
  "message": "Password changed successfully. Please sign in again."
}
```

The response clears the refresh and CSRF cookies, creates no replacement session, returns no token or user object, and is marked `Cache-Control: no-store` and `Pragma: no-cache`.

## Authentication and authorization

The existing `get_current_user()` dependency is authoritative. It accepts only a valid Bearer access token, validates signature, issuer, audience, type, timestamps, and canonical UUID subject, then reloads the user and current roles from MySQL. The account must still be ACTIVE.

The request body cannot select an identity. `ChangePasswordRequest` accepts exactly:

```json
{
  "current_password": "CurrentStrongPassword123",
  "new_password": "NewStrongPassword456"
}
```

Extra fields are forbidden. Client-controlled user IDs, email, phone, role, admin state, password hash, token/session identifiers, account status, and verification state are rejected with a sanitized 422. Tests confirm User A cannot target or mutate User B.

## Password verification and policy

The service locks the authenticated user row with `SELECT ... FOR UPDATE`, re-checks ACTIVE status, and verifies the supplied current password against the current stored hash using the existing `verify_password()` helper. Wrong current passwords and same-as-current new passwords share one generic HTTP 400 response:

```json
{
  "detail": "Password change could not be completed."
}
```

The same-password check uses Argon2 verification against the current hash; hashes are not compared directly. The new password reuses the single registration/reset policy: 8-128 characters with at least one uppercase letter, lowercase letter, and digit. Values are strict strings and are never truncated. Successful replacement uses the existing `PasswordHash.recommended()` Argon2id helper. Plaintext is never persisted.

## Atomic security transaction

`PasswordChangeService` owns the transaction. Repositories issue parameterized SQLAlchemy operations and do not commit. When access-token resolution has already opened the request session transaction, the service uses a nested rollback boundary and commits the caller session only after every required mutation succeeds.

Within one transaction the service:

1. locks the server-resolved user row;
2. re-checks ACTIVE status;
3. verifies the current password;
4. verifies that the new password differs;
5. derives a new Argon2id hash;
6. updates `users.password_hash`;
7. invalidates that user's valid outstanding reset challenges;
8. revokes all that user's active refresh rows with the existing `logout_all` reason;
9. commits.

Injected password-update, reset-invalidation, and refresh-revocation failures each roll back all credential, recovery, and session state. No repository commits independently. A commit-time exception is propagated to the safe route error and the request session is closed/rolled back by the database dependency.

## Session and recovery behavior

Every refresh family belonging to the changed account is revoked, including the current browser and other devices. Refresh sessions and reset challenges belonging to other users are preserved. The backend clears current auth cookies and does not issue replacement credentials. Old raw refresh tokens receive HTTP 401, the old password no longer logs in, and the new password requires a normal login.

Any valid outstanding password-reset challenge for the same user is marked used inside the credential transaction. A post-change attempt to use the old challenge fails. Other users' challenges remain usable and unchanged.

Access JWTs remain stateless and may continue until their configured short lifetime, currently approximately 15 minutes. Phase 5C deliberately does not add an access-token blacklist. Frontends should clear their in-memory access token after success and return to login.

## Concurrency and stale credentials

The MySQL user-row lock is acquired before current-password verification. Two concurrent requests using the same old password therefore serialize. The winner changes the hash and commits; the loser then verifies against the new hash and receives the generic failure. A real two-session MySQL test produced exactly one successful transition, one rejection, a final hash matching only the winner, revoked refresh state, invalidated recovery state, and complete synthetic-data cleanup.

This lock is database-backed and works across application workers; no Python process lock is used for credential state.

## Rate limiting

Password-change attempts are limited by both:

- actual connection peer: 10 attempts per 15 minutes;
- authenticated user: 5 attempts per 15 minutes using an HMAC-protected key derived from the immutable user ID.

The stores are bounded, thread-safe `InMemoryRateLimiter` instances. Excess requests receive HTTP 429, `Retry-After`, and no-store headers before any service mutation. `X-Forwarded-For` is ignored; only `request.client.host` is consumed. The limits are process-local and require a reviewed distributed limiter for horizontally scaled production.

## CSRF decision

Password-change authority is the explicitly attached `Authorization: Bearer` access token plus current-password knowledge. The refresh cookie is neither read nor accepted as authentication authority, so classic ambient-cookie CSRF cannot authorize this endpoint. Requiring the refresh-session double-submit CSRF token would incorrectly make an unrelated refresh cookie part of password-change authority.

The endpoint therefore does not require the CSRF cookie/header pair. It retains exact allowed-Origin validation as defense in depth for browser requests: configured development origins are accepted, a foreign Origin receives HTTP 403 before mutation, and non-browser clients without Origin remain supported. Existing refresh and logout double-submit CSRF controls are unchanged.

## Validation, errors, logging, and cache control

The global sanitized `RequestValidationError` handler remains authoritative. Phase 5C tests recursively inspect malformed, nested, oversized, weak, and extra-field responses and confirm submitted current/new passwords and nested secret markers never appear. Only safe error type, location, and fixed message fields are returned.

The implementation adds no request-body, password, token, cookie, CSRF, hash, or database-detail logging. Synthetic secrets, Bearer tokens, and injected internal errors are absent from captured responses and logs. Public errors are limited to safe 401, 400, 403, 422, 429, or generic 500 contracts. Every password-change response path receives no-store/no-cache headers through the endpoint and sensitive-route middleware.

## Verification evidence

- Phase 5C focused unit/integration/security suite: 64 passed.
- Phase 5A targeted regression: 45 passed.
- Phase 5B targeted regression: 57 passed.
- Pre-Phase-5C validation/Docker security suite: 16 passed.
- Real MySQL concurrency: exactly one transition; baseline restored.
- Database counts before and after: users 4, roles 4, phone codes 3, refresh tokens 6, reset codes 0.
- Alembic current/head: `aca2dda0ef53`; drift none; no migration created.
- OpenAPI: forgot, reset, and change routes each occur exactly once; Phase 5D and email-verification routes remain absent.

The full backend, frontend, and dependency-gate results are recorded in `documentation/CURRENT_PROJECT_STATUS.md` after the final regression run.

## Residual risks

1. An already-issued access JWT can remain usable until its short expiry.
2. Password-change endpoint limits are process-local and are not shared across replicas.
3. Current-password verification and Argon2 hashing consume application resources under attack; bounded limits reduce but do not eliminate denial-of-service risk.
4. Existing password policy has no breached-password screening or password history because neither capability was approved for Phase 5C.
5. Production TLS, managed secrets, monitoring with strict redaction, and distributed rate limiting remain deployment prerequisites.

## Phase boundary

Phase 5C is complete. Phase 5D is **NOT STARTED**. No Phase 5D route, model, service, migration, or frontend feature was added.
