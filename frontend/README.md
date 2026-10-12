# UniShop China Frontend

React/Vite frontend through Phase 9. Listing pages use strict Zod contracts,
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
BUYER/SELLER roles are not product authority. No hardcoded catalog fallback, images,
feed, search, or product admin dashboard.

Tailwind remains 3. Build advisories stay release blockers even when npm audit
--omit=dev is clean. Use HTTPS/trusted system CAs; never disable certificate checks.
