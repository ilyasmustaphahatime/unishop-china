# UniShop China Backend

FastAPI modular monolith through Phase 10: authentication, profiles, seller
verification, catalogs/admin, listings and product images. Future placeholder routers stay unmounted.

From this directory in PowerShell, with `.env` configured and MySQL running:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-proxy-headers
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check --no-cache app tests scripts alembic
```

Sole migration head: `a10b2c3d4e5f`. Never run destructive migration cycles against
development data. Use `scripts/audit_public_handle_migration.py --product-images --products --catalog --seller-verification`
for disposable MySQL migration checks. `scripts/audit_security_http.py` runs the
synthetic-only HTTP/MySQL/storage gate; `--browser` instead runs an independent
real-Chrome lifecycle with fresh profile and temporary Vite/Uvicorn servers, preserving
normal rate limits. Neither command contacts real delivery providers or modifies real users.
`scripts/audit_product_media.py` reports missing/orphaned objects without deleting
anything (0 clean, 1 issues/unavailable). Run it while writes are quiescent.

Product media uses a dedicated ignored local root from `PRODUCT_IMAGE_STORAGE_DIR`
and `PRODUCT_IMAGE_STORAGE_PROVIDER=local` in development. It is never static-served;
production local storage fails closed. Configure and verify a production adapter in
a separate deployment task. See [Phase 10 gate](../documentation/phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md).
