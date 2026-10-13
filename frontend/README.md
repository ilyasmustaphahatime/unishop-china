# UniShop China Frontend

React/Vite frontend through Phase 10. Listing/image pages use strict Zod contracts,
server catalog slugs, memory-only private queries and access tokens.

```powershell
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
npm.cmd test -- --run
npm.cmd run lint
npm.cmd run build
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
