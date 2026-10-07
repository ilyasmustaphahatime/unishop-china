# Frontend Architecture

The React application uses Router, Axios, TanStack Query, Zustand, React Hook Form, Zod, and Tailwind.

Authentication access state is memory-only in Zustand. The refresh token remains an HttpOnly cookie handled by the centralized API/session clients. `AuthBootstrap` restores a session; `ProtectedRoute` is a UX guard, never the backend authorization boundary.

Profile/seller server state lives in TanStack Query. Own-profile keys include the authenticated user ID in memory only and carry private metadata so session clearing removes them. Seller queries use gcTime 0; private file/grant state resets on session changes. Mutations update/invalidate relevant feature caches, and public profiles use separate public-handle keys. Phase 8 public cities/categories share independent public keys (60-second stale time, one retry); stale UI state never authorizes a backend write.

The authenticated route hierarchy is:

```text
ProtectedRoute
└── AuthenticatedLayout
    ├── /onboarding
    └── ProfileGate
        ├── /profile
        ├── /profile/edit
        └── /seller/verification
```

`/u/:handle` is the canonical public profile route and renders only the public response contract. The former `/users/:publicId` route is removed without a compatibility redirect. Profile content is rendered as React text; raw HTML injection APIs are not used.

Post-login destinations use an allowlist of existing navigation paths or validated public handles. Query strings/fragments are not used by current navigation and are never forwarded. Local fake-inbox lookups/consumption carry private identifiers in JSON bodies, not URLs. The HTML document specifies `no-referrer`; the API and reverse proxy also set Referrer-Policy.

The reset, forgot-password, sign-up and standard phone-verification pages remain placeholders through Phase 8. Existing backend JSON-body workflows and the local fake-SMS page retain their security controls. The public /categories route is a read-only directory, not product browsing. There is no admin dashboard or Phase 9 UI.

Actual request direction: src/app/router.tsx -> pages/components -> feature hooks -> feature API/Zod contracts -> centralized Axios clients in src/services -> FastAPI. Zustand owns memory-only auth identity/token/session version, not duplicate profile/catalog server state. The API clients retain version fencing, single-flight refresh, one retry and logout coordination; no browser-storage credentials or raw HTML injection.

Verified 2026-10-07: 211 tests in 15 files, TypeScript, ESLint and production build passed. This review changes no frontend code or dependencies. Browser runtime remains unverified/environment-blocked, not replaced by jsdom tests. Tailwind stays 3.4.19 and its build advisories remain release blockers. See [the complete review](PHASE_1_TO_8_ARCHITECTURE_REVIEW.md).

See [URL privacy and future routing policy](../security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md).
