# UniShop China Current Project Status

## Verified working

- The repository is on `feature/authentication`; `main` exists and both branches currently point to commit `aba5943`.
- FastAPI responds with HTTP 200 at `/`, `/health`, `/api/v1/health`, `/api/v1/health/database`, and `/docs`.
- The database health endpoint returns `{"database":"mysql","status":"healthy","connected":true}`.
- Settings load `backend/.env` relative to the backend directory without exposing its values.
- SQLAlchemy uses `mysql+pymysql`, `pool_pre_ping=True`, a reusable `SessionLocal`, `Base`, and a rollback/close-safe `get_db()` dependency.
- SQLAlchemy and the database-check script both complete `SELECT 1` successfully against `unishop_china` as the dedicated application user.
- Alembic loads the same database URL builder and `Base.metadata` as FastAPI and connects without a configuration or access-denied error.
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

- Backend domain models, model exports, repositories, services, most schemas, and most `/api/v1` domain route modules are placeholders.
- Backend test modules contain placeholders and no collected tests.
- Authentication backend endpoints, authentication database models, JWT behavior, registration, and login are not implemented.
- Most frontend domain feature API/hook/type files, pages, and UI components are placeholders or simple headings.
- The frontend login screen and client request/store helpers are partially implemented from earlier work, but cannot authenticate because the backend authentication API does not exist.
- Most engineering documentation pages, database seeds, diagrams, and Postman collections remain placeholders.

## Existing database state

- Database name: `unishop_china`
- Connection status: connected; `SELECT 1` succeeds
- Server observed: MySQL 9.4.0
- Alembic status: connects successfully with no current revision
- Existing table names: none
- Current migration revision: none
- Existing migrations: none in `backend/alembic/versions/`

## Git status

- Current branch: `feature/authentication`
- Latest commit: `aba5943 chore: initialize UniShop China project`
- Working tree: not clean because this audit has uncommitted fixes and this status document
- Ignore status: `backend/.env`, `frontend/.env`, `backend/.venv/`, and `frontend/node_modules/` are ignored
- Tracked environment files: placeholder-only `backend/.env.example` and `frontend/.env.example`
- Git identity: name is configured; the configured email appears malformed (missing `@`) and was not changed

## Tests and builds

- Backend database check: passed; MySQL returned `1`
- FastAPI health checks: all five audited routes returned HTTP 200
- Alembic `current`, `heads`, and `history`: all exited successfully; each is empty because there are no migrations
- Backend Ruff check: passed
- Backend tests: pytest runs, but collects no tests; this is not a passing test suite
- Frontend build: passed (`tsc -b && vite build`)
- Frontend lint: passed
- Frontend tests: Vitest runs, but finds no test files and exits non-zero; this is not a passing test suite
- Browser validation: a local headless browser rendered the login page and form; its console contained only normal Vite/React development messages and no critical application errors

## Known issues

- No backend or frontend tests are implemented.
- The local server is MySQL 9.4.0, while the project documentation and Docker service target MySQL 8.x/8.4; compatibility is currently adequate for the connection checks but the development baseline is inconsistent.
- `frontend/src/stores/authStore.ts` is implemented while `frontend/src/features/auth/store.ts` is a placeholder with overlapping responsibility.
- The frontend login flow is client-only and cannot succeed until the backend models, migration, and authentication API are implemented in later tasks.
- Most generated project modules are placeholders and must not be mistaken for completed features.
- The Git email `ilyasihtm52gmail.com` appears malformed and should be corrected by the user if unintended.

## Security notes

- Real environment files, virtual environments, dependencies, caches, build outputs, and uploads are ignored appropriately.
- No real `.env` file is tracked, and tracked SQL/environment templates contain placeholder passwords only.
- A secret was previously visible in an IDE screenshot. Rotate that JWT secret locally before using authentication, and do not commit or share the replacement.
- The previously exposed MySQL application password should also be rotated locally if it was shown or shared; keep the replacement only in ignored local configuration.

## Exact next step

Implement the five authentication database models and create the first Alembic migration. Do not implement authentication APIs or JWT behavior in that same task.
