# UniShop China Current Project Status

## Authentication phases

- Phase 1 authentication database models and migration: complete.
- Phase 2 user registration API and test isolation: complete.
- Phase 3A phone OTP generation, HMAC storage, resend limits, verification, and provider abstraction: complete.
- Phase 3B secure local fake SMS workflow and manual verification: complete.
- Real Tencent SMS: pending and disabled.
- Phase 4 login, server-side sessions/tokens, logout, `/auth/me`, and protected-object authorization: not started.

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
- Ready for Phase 4: yes. Phase 4 itself remains unimplemented.

## Verified foundation

- MySQL connection succeeds against `unishop_china`.
- SQLAlchemy uses parameterized expressions and no request-derived raw SQL.
- Alembic current and head remain `a75289cfd4a9`; no schema drift exists.
- Tables remain `alembic_version`, `users`, `user_roles`, `refresh_tokens`, `phone_verification_codes`, and `password_reset_codes`.
- Strict Pydantic schemas reject unknown and privileged registration fields.
- Passwords use Argon2id; OTP values use HMAC-SHA256 and constant-time comparison.
- Registration assigns only the `BUYER` role.
- Phone resend retains its cooldown/hourly limits and verification retains its five-attempt limit.
- Normal authentication APIs return no OTP, password, hash, token, provider error, stack trace, or database detail.
- Development fake SMS remains disabled by default, loopback-only, memory-only, and absent from production routing/OpenAPI.

## Tests and database state

- Backend: 152 passed, 0 failed, 0 skipped, 1 third-party deprecation warning.
- Frontend: 14 passed, 0 failed, 0 skipped.
- Frontend type check, lint, and production build pass.
- Development database baseline and final counts: users 4, roles 4, phone codes 3, refresh tokens 0, reset codes 0.
- Orphan roles/codes: 0.

Every database test uses an outer transaction/savepoint and verifies exact counts plus pre-existing user/role identifiers after rollback. No broad deletion, truncation, schema reset, or legitimate-data modification is used.

## Authorization boundary

The current backend exposes only public registration/phone-verification and health endpoints. There is no authenticated object API yet, so object-level authorization cannot truthfully be marked implemented. Frontend route guards are navigation aids only and are not treated as security controls. Phase 4 must add server-side authentication and deny-by-default object/function authorization before protected marketplace endpoints are activated.

## Known limitations

- Login/JWT/refresh/logout/authenticated-object APIs do not exist and were not added during cleanup.
- The in-memory registration limiter is per process; production horizontal deployments require a shared limiter.
- Real Tencent Signature/Template approval and credentials remain unavailable.
- A third-party Starlette TestClient deprecation warning remains.

## Exact next step

Review and commit the completed cleanup with the suggested message `chore: complete pre-phase-4 security cleanup`, then begin the separately scoped Phase 4 implementation.
