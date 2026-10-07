# UniShop China

UniShop China is a full-stack marketplace project for international students and foreigners living in China. Authentication backend workflows, secure frontend sessions, profiles/onboarding, public handles, private seller verification, public cities/two-level categories and minimal backend admin operations are implemented through Phase 8. Sign-up, forgot/reset password and standard phone-verification frontend pages remain placeholders. Products, browsing/search, chat, favorites, deals and reviews remain future work, not available features. UniShop China does **not** process payments; payment and delivery will be arranged privately outside the platform.

## Stack and structure

- `frontend/`: React, TypeScript, Vite, Router, Axios, TanStack Query, Zustand, Tailwind.
- `backend/`: FastAPI, SQLAlchemy, Alembic, Pydantic, secure JWT/session authentication, PyMySQL, profiles, private seller verification and catalogs/admin.
- `database/`: MySQL 8 bootstrap, seed placeholders, diagrams, ignored backups.
- `documentation/`, `postman/`, `infrastructure/`, `scripts/`: engineering documentation and local tooling.

## Local setup

Never commit real secrets. Copy `.env.example` files to `.env` and replace development values.

```bash
cd backend
python -m venv .venv
# Activate the environment, then:
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm ci
npm run dev
```

Install MySQL 8 locally, create `unishop_china` with `utf8mb4`, and configure `backend/.env`. Local verification currently used MySQL 9.4; MySQL 8 deployment compatibility remains a release gate. Docker Compose configuration exists, but Docker/NGINX runtime verification is environment-blocked. Create new migrations with `alembic revision --autogenerate -m "description"` and apply them with `alembic upgrade head`; never regenerate applied revisions.

See [current project status](documentation/CURRENT_PROJECT_STATUS.md), the
[Phase 1-8 architecture/security review](documentation/architecture/PHASE_1_TO_8_ARCHITECTURE_REVIEW.md),
[seller workflow](documentation/phases/PHASE_7_SELLER_VERIFICATION.md), and
[catalog API](documentation/api/catalog-api.md). Apply migrations through the sole
head `e8f0a1b2c3d4` before starting the code. Profile city writes use public city slugs.

Local regression passed. Production readiness is **NO**: Tailwind 3 build advisories,
unconfigured private production storage/operations, and browser/container runtime
verification remain open. No Tailwind 4 migration or Phase 9 implementation was added.
