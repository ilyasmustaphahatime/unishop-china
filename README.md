# UniShop China

UniShop China is a full-stack marketplace project for international students and foreigners living in China. Authentication, secure frontend sessions, profiles/onboarding, public handles, private seller verification, catalogs/admin, and product listing core are implemented through Phase 9. Sign-up, forgot/reset password and standard phone-verification frontend pages remain placeholders. Product images, browsing/search, chat, favorites, deals and reviews remain future work. UniShop China does **not** process payments; payment and delivery will be arranged privately outside the platform.

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
head `f9a1b2c3d4e5` before starting the code. Profile/listing city writes use public city slugs.

Phase 9 routes: `/sell/new`, `/seller/listings`, `/seller/listings/:slug/edit`, `/p/:slug`.
Create/publish requires current approved seller status, verified email/phone and
completed onboarding. No product images or public feed. See [listing API](documentation/api/product-api.md)
and [Phase 9 gate](documentation/phases/PHASE_9_PRODUCT_LISTINGS.md).

Local regression passed. Production readiness is **NO**: Tailwind 3 build advisories,
unconfigured private production storage/operations, and browser/container runtime
verification remain open. Tailwind remains 3; Phase 10/11 functionality was not added.
