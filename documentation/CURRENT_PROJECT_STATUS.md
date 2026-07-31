# UniShop China Current Project Status

## Authentication phases

- Phase 1 authentication database models and migration: complete.
- Phase 2 user registration API and test isolation: complete.
- Phase 3A phone OTP generation, HMAC storage, resend limits, verification, and provider abstraction: complete.
- Phase 3B secure local fake SMS workflow and manual verification: complete.
- Real Tencent SMS: pending and disabled.
- Phase 4A secure email/phone login, short-lived access token, authentication dependency, and `/auth/me`: complete.
- Phase 4B refresh-token rotation, HttpOnly cookies, reuse detection, logout, and durable frontend session: not started.
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
- The ignored local backend `.env` now contains exactly one canonical development `APP_ENV` entry and one canonical local `FRONTEND_URL` entry; no secret-bearing value was changed.
- Pre-Phase-4 security gates remain complete; Phase 4A was implemented without a schema migration.

## Verified foundation

- MySQL connection succeeds against `unishop_china`.
- SQLAlchemy uses parameterized expressions and no request-derived raw SQL.
- Alembic current and head remain `a75289cfd4a9`; no schema drift exists.
- Tables remain `alembic_version`, `users`, `user_roles`, `refresh_tokens`, `phone_verification_codes`, and `password_reset_codes`.
- Strict Pydantic schemas reject unknown and privileged registration fields.
- Passwords use Argon2id; OTP values use HMAC-SHA256 and constant-time comparison.
- Registration assigns only the `BUYER` role.
- Phone resend retains its cooldown/hourly limits and verification retains its five-attempt limit.
- Registration and phone-verification APIs return no OTP, password, hash, token, provider error, stack trace, or database detail.
- Login returns only a 15-minute access token plus a schema-protected user view; `/auth/me` reloads current roles and ACTIVE status from MySQL.
- Unknown users, wrong passwords, and inactive users share one generic 401 response, with dummy Argon2 verification for unknown users.
- Login limits are five attempts per connection peer per minute and ten attempts per HMAC-hashed identifier per 15 minutes.
- Development fake SMS remains disabled by default, loopback-only, memory-only, and absent from production routing/OpenAPI.

## Tests and database state

- Backend: 227 passed, 0 failed, 0 skipped, 1 third-party deprecation warning.
- Frontend: 14 passed, 0 failed, 0 skipped.
- Frontend type check, lint, and production build pass.
- Development database baseline and final counts: users 4, roles 4, phone codes 3, refresh tokens 0, reset codes 0.
- Orphan roles/codes: 0.

Every database test uses an outer transaction/savepoint and verifies exact counts plus pre-existing user/role identifiers after rollback. No broad deletion, truncation, schema reset, or legitimate-data modification is used.

## Authorization boundary

The backend now establishes identity through a validated access token and protects `/api/v1/auth/me`. There is still no marketplace object API in scope, so object-level authorization cannot truthfully be marked implemented. Frontend route guards remain navigation aids only. Future protected endpoints must add deny-by-default function and object authorization on top of `get_current_user()`.

## Known limitations

- Refresh tokens, cookies, rotation, reuse detection, logout, and durable frontend session bootstrap do not exist.
- Access tokens cannot be revoked before their 15-minute expiry in Phase 4A.
- Registration and login limiters are per process; production horizontal deployments require a shared limiter.
- Real Tencent Signature/Template approval and credentials remain unavailable.
- A third-party Starlette TestClient deprecation warning remains.

## Exact next step

Review and commit Phase 4A with the suggested message `feat: implement secure login and access token authentication`. Phase 4B should then design refresh-token rotation, HttpOnly cookies, reuse detection, logout, and durable session bootstrap without introducing browser token persistence.
