# UniShop China

UniShop China is a full-stack marketplace project for international students and foreigners living in China. Authentication, profiles/onboarding, public handles and private seller verification are implemented. Products, browsing/search, chat, favorites, deals and reviews remain future work, not available features. UniShop China does **not** process payments; payment and delivery will be arranged privately outside the platform.

## Stack and structure

- `frontend/`: React, TypeScript, Vite, Router, Axios, TanStack Query, Zustand, Tailwind.
- `backend/`: FastAPI, SQLAlchemy, Alembic, Pydantic, secure JWT/session authentication, PyMySQL, profiles and private seller verification.
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
npm install
npm run dev
```

Install MySQL 8 locally, create `unishop_china` with `utf8mb4`, and configure `backend/.env`; or start everything with `docker compose up --build`. Create migrations with `alembic revision --autogenerate -m "description"` and apply them with `alembic upgrade head`.

See [current project status](documentation/CURRENT_PROJECT_STATUS.md) and the
[Phase 7 workflow and private-media contract](documentation/phases/PHASE_7_SELLER_VERIFICATION.md).
Apply the additive challenge-expiry migration with `alembic upgrade head` before starting the new code.
Production object storage and operational privacy controls are not configured; this is not a production release.
