# UniShop China Current Project Status

## Authentication phases

- Phase 1 authentication database models and migration: complete.
- Phase 2 user registration API: complete.
- Phase 2 test isolation repair: complete; legitimate development data is preserved.
- Phase 3A OTP generation, HMAC storage, resend, limits, verification, fake test sender, and Tencent adapter: complete.
- Phase 3B secure local fake SMS implementation: code and automated verification complete.
- Phase 3B live browser manual entry: pending because the in-app browser host integration was unavailable.
- Real Tencent SMS: pending.
- Ready for Phase 4: no, until the live development-page manual entry is confirmed.

## Verified foundation

- FastAPI uses the existing SQLAlchemy/MySQL/PyMySQL configuration with `pool_pre_ping=True`.
- MySQL connection check passes against `unishop_china`.
- Alembic current and head are `a75289cfd4a9`; no schema drift exists.
- The expected six tables remain: `alembic_version`, `users`, `user_roles`, `refresh_tokens`, `phone_verification_codes`, and `password_reset_codes`.
- No Phase 3B migration or database table was added.
- Vite reads `VITE_API_BASE_URL`; TypeScript, ESLint, tests, and production build pass.

## Phase 3B security status

- The fake provider and inbox are disabled by default.
- Unsafe fake configuration fails startup outside development.
- The development router is absent from production routing and OpenAPI.
- Inbox access uses the actual loopback peer and ignores forged forwarding headers.
- Raw OTP values exist only in the development process-memory inbox and live component state.
- MySQL continues to store HMAC values only.
- Normal registration, resend, and verification APIs expose no OTP.
- The fake sender performs no Tencent or other external-network call.
- Passwords and OTP values are not persisted in browser storage or logged by the development page.
- CORS is restricted to configured and expected local frontend origins.

## Test status

- Backend: 146 passed, 0 failed, 0 skipped, 1 third-party deprecation warning.
- Frontend: 12 passed, 0 failed, 0 skipped.
- Backend compile, import, dependency, Ruff, database, and Alembic checks pass.
- Frontend type check, lint, tests, and production build pass.
- Localhost API smoke flow passed registration, delayed delivery, wrong code, cooldown, resend, old-code rejection, new-code verification, HMAC-only storage, message consumption, and targeted cleanup.

## Development database state

- Users: 1 legitimate pre-existing record.
- Roles: 1 legitimate pre-existing record.
- Phone verification codes: 0.
- Refresh tokens: 0.
- Password reset codes: 0.
- Orphan roles/codes: 0.

The automated suite uses transaction/savepoint isolation and restores exact baseline counts after every database test. No broad deletion, truncation, schema reset, or modification of legitimate development data is used.

## Known limitations

- The final live browser interaction at `/dev/phone-verification` remains unconfirmed due to unavailable host browser metadata.
- Real Tencent Signature/Template approval and production credentials are not available.
- Login, JWT, refresh-token workflows, logout, password recovery, and marketplace features are not implemented.
- The local server reports MySQL 9.4 while project deployment configuration targets MySQL 8.x/8.4.
- A third-party Starlette TestClient deprecation warning remains.

## Git state

- Branch: `feature/authentication`.
- Baseline commit: `4b33850`.
- Phase 2 isolation repair and Phase 3B changes remain unstaged and uncommitted.
- No commit, push, branch switch, merge, rebase, reset, or destructive cleanup was performed.

## Exact next step

Run the documented development configuration, open `/dev/phone-verification` in a local browser, manually type the displayed fake OTP, and confirm the success state. Keep Tencent disabled. After that manual gate passes, review and commit Phase 3B before starting Phase 4.
