# Phase 4B: Secure Refresh Sessions

## Scope and status

Phase 4B adds backend-only browser session renewal to the Phase 4A login system. It implements opaque refresh tokens, hash-only persistence, rotation, reuse detection, CSRF-bound cookies, explicit credentialed CORS, logout, logout-all, resource limits, and rate limiting. At Phase 4B completion, the Phase 4C frontend bootstrap, `withCredentials`, single-flight refresh, retry queues, and route integration were not yet implemented. They now exist as uncommitted Phase 4C work with automated gates passing, and the final real-browser gate subsequently passed using explicit user-verified evidence.

## Architecture

- `RefreshSessionService` owns transaction boundaries and session-family lifecycle.
- `RefreshTokenRepository` contains parameterized SQLAlchemy reads, row locks, inserts, and revocations; it never commits.
- `session_security.py` centralizes cryptographic generation, SHA-256 hashing, CSRF validation, and exact Origin validation.
- `auth_cookies.py` is the only Set-Cookie/delete-cookie implementation.
- The existing UTC helpers, user repository, account-status enum, access-token service, authentication dependency, and bounded in-process limiter are reused.

## Token and session-family design

Refresh tokens are opaque `secrets.token_urlsafe(64)` values with 512 bits of input entropy. The raw value exists only in an HttpOnly browser cookie. MySQL stores `SHA-256(raw_token)`; neither raw refresh nor CSRF values are returned in JSON or logged. CSRF tokens use `secrets.token_urlsafe(32)` and only their SHA-256 hashes are stored.

Every password login creates a new UUID family. Rotation creates a single-use child with the same `family_id` and unchanged `family_expires_at`. Individual tokens last at most 7 days, while a family lasts at most 30 days. A child's expiry is the earlier of those limits. Up to 10 active families are allowed by default; a transactional user row lock serializes logins and the oldest excess family is revoked with `session_limit`.

## Database and migration

Migration `c91e4a7b2d6f` follows `a75289cfd4a9`. It adds `family_id`, `csrf_token_hash`, `family_expires_at`, `last_used_at`, `revocation_reason`, and self-referencing `replaced_by_token_id`; it also adds focused indexes, a replacement foreign key, and a bounded reason constraint. Existing `token_hash`, user cascade policy, IDs, and timestamps are preserved. The development table contained zero refresh rows before upgrade, so adding required non-null fields did not require insecure defaults or destructive conversion. Downgrade was reviewed but was not run against the real development database.

## Cookies, CORS, and CSRF

The refresh cookie is HttpOnly and narrowly scoped to `/api/v1/auth`; the CSRF cookie is JavaScript-readable and scoped to `/` so frontend code running on application routes can read it. Both default to `SameSite=Lax`, no Domain, and aligned Max-Age/Expires. Cookie deletion uses each cookie's matching path. Secure is false only for local HTTP development and mandatory outside development. Startup rejects unsafe lifetime, name, SameSite, Secure, path, and wildcard-origin settings.

Credentialed CORS accepts only the configured frontend origin plus localhost and 127.0.0.1 development origins. Methods and headers are narrow and include `X-CSRF-Token`. Login, refresh, logout, and logout-all reject a present foreign Origin; clients without Origin remain supported.

Refresh and logout use double-submit CSRF: the cookie and `X-CSRF-Token` header must exist and match via `hmac.compare_digest`, and the presented value's hash must match the selected refresh row. Rotation creates a fresh CSRF value. Login ignores pre-existing session cookies and always creates a new family, preventing session fixation.

## Login and refresh flow

Successful login preserves the Phase 4A JSON access-token and safe-user response, commits the new family, and only then sets both cookies. Failed authentication creates no session and sets no cookies.

`POST /api/v1/auth/refresh` validates Origin and CSRF, hashes the cookie, and locks the matching row with `SELECT ... FOR UPDATE`. In one transaction it checks token/family expiry, reloads and locks the ACTIVE user, inserts one child, marks the parent `rotated`, and links `replaced_by_token_id`. Only after commit does it mint an access token and set rotated cookies. Success returns only access token, type, and expiry with `Cache-Control: no-store` and `Pragma: no-cache`.

Reusing a revoked ancestor revokes every row in that family as `reuse_detected`; independent families remain valid. With concurrent use of one parent, one request may rotate and the next observes reuse and revokes the family. Phase 4C must implement single-flight refresh to prevent legitimate browser races from triggering this strict policy. Token-hash collisions are retried at most three times. Transaction failure rolls back parent and child state, and routes do not set cookies.

Expired sessions are revoked as `expired_cleanup`. A non-ACTIVE user causes family revocation as `inactive_account` and a generic 401. Public errors do not distinguish unknown, expired, rotated, reused, revoked, or inactive sessions.

## Logout behavior

`POST /api/v1/auth/logout` requires CSRF only when a refresh cookie exists, revokes the current family as `logout`, clears both cookies, and returns 204. Missing, unknown, expired, and already-revoked cookies remain idempotent 204 outcomes without session disclosure.

`POST /api/v1/auth/logout-all` requires the existing Phase 4A bearer authentication, derives the user from the validated access token, revokes only that user's active families as `logout_all`, clears current cookies, and returns 204. It accepts no user ID or body. Access tokens remain stateless and valid until their 15-minute expiry; no blacklist is added.

## Rate limits

- Refresh peer: 20 per 60 seconds.
- Refresh session: 10 per 60 seconds using an HMAC-derived token key.
- Logout peer: 10 per 60 seconds.
- Logout-all authenticated user: 5 per 60 seconds.

The actual connection peer is used; `X-Forwarded-For` is ignored. Responses include `Retry-After`, limiter memory is bounded, and limited requests do not reach rotation/revocation. Limits remain process-local; a shared store such as Redis is required before horizontal scaling.

## Manual testing

Use the Phase 4B Postman collection or a local test client with the development Fake SMS provider. Confirm cookies through headers/cookie-jar metadata without printing values, compare database hashes without displaying them, rotate once, test old-token reuse, verify independent-family isolation, then test logout and logout-all. Remove only synthetic users by exact ID so existing rows are preserved.

## Security decisions and limitations

- Access tokens remain 15-minute stateless JWTs with the Phase 4A validation rules.
- Logout cannot immediately invalidate an issued access token.
- A stolen raw refresh cookie plus matching CSRF value remains usable until rotation, expiry, revocation, or detection.
- In-process rate limiting is not sufficient for multiple application replicas.
- No device metadata or session-management API is stored or exposed.
- Phase 4C now sends credentialed requests and coordinates refresh per tab; its final real-browser workflow passed using explicit user-verified evidence.
