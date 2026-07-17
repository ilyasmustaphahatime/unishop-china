# UniShop China

UniShop China is a full-stack marketplace starter for international students and foreigners living in China. Users browse by Chinese city, verified sellers can list products originating from different countries, and users can chat, save products, track informal deals, review, and report. UniShop China does **not** process payments; payment and delivery are arranged privately outside the platform. All users and listings operate within China.

## Stack and structure

- `frontend/`: React, TypeScript, Vite, Router, Axios, TanStack Query, Zustand, Tailwind.
- `backend/`: FastAPI, SQLAlchemy, Alembic, Pydantic, JWT-ready security placeholders, PyMySQL, WebSockets.
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

Most domain models, schemas, repositories, services, routes, tests, and documentation pages are intentional placeholders. Authentication and marketplace business logic are not implemented yet.
