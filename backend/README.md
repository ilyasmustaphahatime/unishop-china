# UniShop China Backend

FastAPI modular monolith through Phase 9: authentication, profiles, seller
verification, catalogs/admin, listing core. Future placeholder routers stay unmounted.

From this directory in PowerShell, with `.env` configured and MySQL running:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check --no-cache app tests scripts alembic
```

Sole migration head: `f9a1b2c3d4e5`. Never run destructive migration cycles against
development data. Use `scripts/audit_public_handle_migration.py --products` for the
disposable local MySQL gate and `scripts/audit_security_http.py` for synthetic-only
Uvicorn/MySQL workflow with exact cleanup. See [Phase 9 gate](../documentation/phases/PHASE_9_PRODUCT_LISTINGS.md).
