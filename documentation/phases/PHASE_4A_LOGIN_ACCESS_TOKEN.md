# Phase 4A - Secure Login and Access Token Authentication

## Scope

Phase 4A adds backend-only email/phone login, short-lived JWT access tokens, a reusable Bearer authentication dependency, `GET /api/v1/auth/me`, and bounded login rate limits. It does not add refresh tokens, cookies, logout, password reset, OAuth, frontend persistence, or marketplace authorization.

## Architecture

- `schemas/auth.py` owns strict request and safe response schemas.
- `common/validators.py` owns the shared registration/login email and mainland-China phone normalization.
- `repositories/user_repository.py` and `role_repository.py` perform parameterized read queries.
- `services/auth_service.py` owns credential and account-status policy.
- `services/token_service.py` owns JWT creation and validation.
- `api/v1/auth/dependencies.py` owns rate-limit and Bearer dependencies.
- `api/v1/auth/routes.py` maps internal failures to safe HTTP responses.

No database schema or migration is required. Login is read-only and creates no refresh-token, verification-code, or session row.

## Login flow

1. Pydantic rejects missing, oversized, or unknown fields.
2. The single `identifier` is classified and normalized.
3. IP and HMAC-hashed identifier rate limits run before account lookup or Argon2 work.
4. The existing repository loads the user by normalized email or phone.
5. The existing Argon2id verifier checks the submitted password.
6. Unknown users invoke the same verifier against one process-initialized dummy Argon2 hash.
7. Unknown users, wrong passwords, and inactive users receive the same `401 Invalid credentials.` response.
8. Current roles are loaded from MySQL.
9. A 15-minute access token is created and returned with a schema-protected user view.

## Identifier handling

- Emails are trimmed and lowercased using the same helper as registration, then validated as an email.
- Mainland Chinese mobile numbers reuse the registration E.164 normalizer.
- Supported phone examples include local `138...`, `+86...`, and `0086 ...` formats.
- Password content is never trimmed or normalized. Login enforces only non-empty and 128-character maximum limits, not registration strength policy.

## Authentication and account policy

- Password verification remains Argon2id through `verify_password()`.
- Only `ACTIVE` accounts may receive an access token.
- `SUSPENDED`, `BANNED`, and `DELETED` accounts receive the generic credential failure.
- An ACTIVE user may log in while email or phone verification is false; the safe response exposes both verification flags.
- Verification requirements for future sensitive marketplace operations are outside Phase 4A.

## Access token

- Library: PyJWT already present in the backend.
- Algorithm: HS256 only.
- Lifetime: 15 minutes.
- Issuer: `unishop-china-api`.
- Audience: `unishop-china-web`.
- Clock skew: 30 seconds.
- Claims: `sub`, `type=access`, random `jti`, `iss`, `aud`, `iat`, `nbf`, and `exp`.
- Roles are deliberately absent; the authentication dependency loads current roles from MySQL.
- Passwords, hashes, OTP data, profile documents, database credentials, and refresh-token data are absent.

The JWT secret remains only in ignored backend environment configuration. Missing, short, placeholder, or unsupported-algorithm configuration fails application startup safely without printing the secret.

## Authentication dependency and `/auth/me`

`get_current_user()` uses FastAPI HTTP Bearer support, validates every required token property, parses the UUID subject, reloads the user and roles, and rechecks ACTIVE status. Every authentication failure returns HTTP 401 with `WWW-Authenticate: Bearer` and `Could not validate credentials.`

`GET /api/v1/auth/me` returns only ID, optional email/phone, verification flags, account status, roles, and creation time. It performs no write.

## Rate limits

- Connection peer: 5 attempts per 60 seconds.
- Normalized identifier: 10 attempts per 15 minutes.
- Identifier keys are HMAC-SHA256 digests, never raw email or phone values.
- `X-Forwarded-For` is not trusted.
- Both stores are bounded and remove expired entries.
- HTTP 429 responses include `Retry-After` and no account information.

The limiter is process-local. A shared store such as Redis is required before horizontal production scaling.

## Testing and manual verification

Automated coverage includes schema rejection, normalization, real Argon2 verification, dummy-hash execution, generic errors, every account status, required JWT claims and negative JWT cases, `/auth/me`, current database roles, both rate limits, forwarded-header attacks, read-only database behavior, route inventory, and all Phase 1-3 regressions.

Manual verification uses a generated synthetic development account and the local fake-SMS path only. It checks login, token metadata, `/auth/me`, generic failures, invalid token behavior, and exact cleanup of only the generated rows. No Tencent SMS is sent.

## Known limitations and Phase 4B handoff

- No refresh token exists.
- No cookie or durable browser session exists.
- No logout or token revocation exists.
- The frontend must keep any future Phase 4A access token in memory only.
- A browser refresh will end a future temporary Phase 4A frontend session.
- The short-lived access token remains usable until expiry if stolen.
- Phase 4B will design refresh-token rotation, HttpOnly cookies, reuse detection, logout, revocation, and durable session bootstrap.
