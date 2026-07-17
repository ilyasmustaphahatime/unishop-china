# UniShop China Current Project Status

## Verified working

- The repository is on `feature/authentication`; `main` exists and the latest committed foundation audit is `68310c8`.
- FastAPI responds with HTTP 200 at `/`, `/health`, `/api/v1/health`, `/api/v1/health/database`, and `/docs`.
- The database health endpoint returns `{"database":"mysql","status":"healthy","connected":true}`.
- Settings load `backend/.env` relative to the backend directory without exposing its values.
- SQLAlchemy uses `mysql+pymysql`, `pool_pre_ping=True`, a reusable `SessionLocal`, `Base`, and a rollback/close-safe `get_db()` dependency.
- SQLAlchemy and the database-check script both complete `SELECT 1` successfully against `unishop_china` as the dedicated application user.
- Alembic loads the same database URL builder and `Base.metadata` as FastAPI and connects without a configuration or access-denied error.
- Phase 1 authentication models, constraints, relationships, and migration `a75289cfd4a9` are applied and validated.
- Vite serves the frontend on port 5173, returns HTTP 200, renders the React login page and form, and injects `VITE_API_BASE_URL` into the transformed API client.
- The TypeScript/Vite production build and ESLint check complete successfully.

## Foundation fixes completed

- Standardized the stale underscored database name to the required `unishop_china` name in backend defaults, examples, SQL bootstrap scripts, Docker configuration, infrastructure configuration, and the README.
- Added ignore rules for TypeScript build-info and compiled configuration artifacts.
- Removed tracked generated `*.tsbuildinfo`, compiled configuration `.js`, and compiled configuration `.d.ts` files while retaining their TypeScript sources.
- Removed a UTF-8 BOM from `backend/pytest.ini` so pytest can load its configuration.
- Replaced the minimal ESLint setup with TypeScript/React-aware rules and ignored generated build output.
- Removed two unused imports from the shared backend model mixin; Ruff now passes.

## Existing placeholders

- Marketplace domain models, repositories, services, most schemas, and most `/api/v1` domain route modules are placeholders.
- Authentication backend endpoints, JWT behavior, registration, and login are not implemented; the five authentication database models are implemented.
- Authentication database tests are implemented; other backend test modules remain placeholders.
- Most frontend domain feature API/hook/type files, pages, and UI components are placeholders or simple headings.
- The frontend login screen and client request/store helpers are partially implemented from earlier work, but cannot authenticate because the backend authentication API does not exist.
- Most engineering documentation pages, database seeds, diagrams, and Postman collections remain placeholders.

## Existing database state

- Database name: `unishop_china`
- Connection status: connected; `SELECT 1` succeeds
- Server observed: MySQL 9.4.0
- Alembic status: connected and at head
- Existing table names: `alembic_version`, `users`, `user_roles`, `refresh_tokens`, `phone_verification_codes`, `password_reset_codes`
- Current migration revision: `a75289cfd4a9`
- Existing migrations: one authentication-only migration

## Git status

- Current branch: `feature/authentication`
- Latest commit: `68310c8 chore: repair and document project foundation`
- Working tree: not clean because Phase 1 implementation is not committed yet
- Ignore status: `backend/.env`, `frontend/.env`, `backend/.venv/`, and `frontend/node_modules/` are ignored
- Tracked environment files: placeholder-only `backend/.env.example` and `frontend/.env.example`
- Git identity: name is configured; the configured email appears malformed (missing `@`) and was not changed

## Tests and builds

- Backend database check: passed; MySQL returned `1`
- FastAPI health checks: all five audited routes returned HTTP 200
- Alembic `current`, `heads`, `history`, and schema-drift check: passed at revision `a75289cfd4a9`
- Backend Ruff check: passed
- Backend tests: 22 authentication database tests passed; other feature test files remain placeholders
- Frontend build: passed (`tsc -b && vite build`)
- Frontend lint: passed
- Frontend tests: Vitest runs, but finds no test files and exits non-zero; this is not a passing test suite
- Browser validation: a local headless browser rendered the login page and form; its console contained only normal Vite/React development messages and no critical application errors

## Known issues

- Frontend tests and non-authentication backend tests are not implemented.
- The local server is MySQL 9.4.0, while the project documentation and Docker service target MySQL 8.x/8.4; compatibility is currently adequate for the connection checks but the development baseline is inconsistent.
- `frontend/src/stores/authStore.ts` is implemented while `frontend/src/features/auth/store.ts` is a placeholder with overlapping responsibility.
- The frontend login flow is client-only and cannot succeed until authentication APIs are implemented in later tasks.
- Most generated project modules are placeholders and must not be mistaken for completed features.
- The Git email `ilyasihtm52gmail.com` appears malformed and should be corrected by the user if unintended.

## Security notes

- Real environment files, virtual environments, dependencies, caches, build outputs, and uploads are ignored appropriately.
- No real `.env` file is tracked, and tracked SQL/environment templates contain placeholder passwords only.
- A secret was previously visible in an IDE screenshot. Rotate that JWT secret locally before using authentication, and do not commit or share the replacement.
- The previously exposed MySQL application password should also be rotated locally if it was shown or shared; keep the replacement only in ignored local configuration.

## Exact next step

Implement `POST /api/v1/auth/register` only. Keep login, JWT issuance, OTP sending, password reset, and other endpoints out of that task.
