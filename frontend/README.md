# UniShop China Frontend

React/Vite frontend through Phase 11A. Listing/image pages use strict Zod contracts,
server catalog slugs, memory-only private queries and access tokens.

Choose English, 简体中文, العربية (RTL), or Français in any global shell.
English is the default/fallback. Only `unishop.locale` is saved; it survives logout
without saving private data. Seller content is not translated. Catalog names use
approved Chinese or English fallback; slugs and decimal payloads are unchanged.

Fresh Phase 11A: **367 frontend tests**, TS/negative-key fixtures, lint/build, 1,388
backend tests and 74 real-Chrome locale checks. Production is not certified.
See [the full report/coverage/manifest](../documentation/phases/PHASE_11A_INTERNATIONALIZATION.md).

```powershell
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
npm.cmd test -- --run
npm.cmd run lint
npm.cmd run build
npx.cmd tsc -p tsconfig.i18n-tests.json --noEmit
node.exe scripts/inventory-i18n.mjs
```

Configure `.env` `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1` (or the allowed
same-origin proxy URL). Backend CORS must permit the actual frontend origin.
Routes: `/sell/new`, `/seller/listings`, `/seller/listings/:slug/edit`, `/p/:slug`.
Creation requires current server-authoritative approved seller/onboarding state.
BUYER/SELLER roles are not product authority. Owners can upload up to eight images,
preview authenticated sanitized bytes, reorder the cover and delete. Archived
listings retain private read/delete, never upload/reorder. Public detail has a safe
gallery and zero-image fallback. Blob URLs are revoked on removal/logout/account
switch; tokens never enter URLs or persistent storage. Image changes do not reset
unsaved listing edits. No hardcoded catalog fallback, feed, search, or product admin dashboard.

Full Phase 10 gate: 304 tests, TypeScript, ESLint and production build passed.
The isolated real-Chrome script is run from backend with `scripts/audit_security_http.py --browser`.
See [image API](../documentation/api/product-images-api.md) and
[gate/manifest](../documentation/phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md).

Tailwind remains 3. Build advisories stay release blockers even when npm audit
--omit=dev is clean. Use HTTPS/trusted system CAs; never disable certificate checks.

For this machine's trusted system store and normal HTTPS verification:

```powershell
$cli = Join-Path (Split-Path (Get-Command node.exe).Source) 'node_modules\npm\bin\npm-cli.js'
node.exe --use-system-ca $cli ci
node.exe --use-system-ca $cli audit
node.exe --use-system-ca $cli audit --omit=dev
```

Run the Phase 11A isolated Chrome/MySQL gate from `backend/`:

```powershell
.\.venv\Scripts\python.exe ..\frontend\scripts\verify-i18n-browser.py
```

It reuses random synthetic accounts, temporary Vite/Uvicorn/storage, exact cleanup
and fingerprints; it prints no credentials. Empty-login screenshots are kept in
a named system-temp folder outside the repo for visual QA. No production data,
provider or deployment certification is implied. Do not run against production.
