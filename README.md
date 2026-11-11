# UniShop China

UniShop China is a full-stack marketplace project for international students and foreigners living in China. The backend is implemented through Phase 14: authentication, profiles/onboarding, seller verification, catalogs/admin, product listings/images, browse/search, favorites/recent history, private chat, consent-based WeChat sharing and offers/deals. The frontend implements secure sessions, profiles, seller verification and product management in four languages. Sign-up/reset/standard phone-verification pages and browse/chat/favorites/offers interfaces remain deferred or placeholders. UniShop China does **not** process payments; payment and delivery are arranged privately outside the platform.

## Stack and structure

Phase 11A adds English, Simplified Chinese, Arabic (RTL) and French to existing
reachable UI, with a global selector and browser preference. Phase 11A Git closure
is complete; its historical browser evidence is distinct from current local tests.
See the [Phase 11A report and full manifest](documentation/phases/PHASE_11A_INTERNATIONALIZATION.md).
Seller content, authentication, API payloads and database schemas are unchanged.

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
head `e14f5a6b7c8d` before starting the code. Profile/listing city writes use public city slugs.

Phase 9 routes: `/sell/new`, `/seller/listings`, `/seller/listings/:slug/edit`, `/p/:slug`.
Create/publish requires current approved seller status, verified email/phone and
completed onboarding. Each listing supports 0-8 sanitized static JPEG/PNG/WebP images,
private authenticated owner previews, ordering/cover and deletion. Public image
bytes follow current listing visibility. The backend now supports public browse/search;
the corresponding browse UI remains deferred. See
[listing API](documentation/api/product-api.md), [image API](documentation/api/product-images-api.md)
and the [Phase 10 gate and full manifest](documentation/phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md).

The [full codebase audit](documentation/audits/FULL_CODEBASE_ARCHITECTURE_API_SECURITY_AUDIT.md)
(11 November 2026) records 2,003 passing full-backend tests, 405 frontend tests,
targeted follow-up regressions, three concurrency rounds and live MySQL HTTP/WebSocket
checks. Current Python/full npm/production npm audits report zero known vulnerabilities;
Tailwind remains 3.4.19. This does not constitute production certification.

Production readiness is **NO**: production private storage/delivery/operations,
deployed TLS/WSS, container/proxy runtime, target-runtime and fresh browser acceptance
remain release gates. Phase 15 has not started. Configured private product media is
kept separate from private seller evidence and is not committed to Git.
