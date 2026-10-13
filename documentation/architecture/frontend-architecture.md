# Frontend Architecture

The React application uses Router, Axios, TanStack Query, Zustand, React Hook Form, Zod, and Tailwind.

Authentication access state is memory-only in Zustand. The refresh token remains an HttpOnly cookie handled by the centralized API/session clients. `AuthBootstrap` restores a session; `ProtectedRoute` is a UX guard, never the backend authorization boundary.

Profile/seller server state lives in TanStack Query. Own-profile keys include the authenticated user ID in memory only and carry private metadata so session clearing removes them. Seller queries use gcTime 0; private file/grant state resets on session changes. Mutations update/invalidate relevant feature caches, and public profiles use separate public-handle keys. Phase 8 public cities/categories share independent public keys (60-second stale time, one retry); stale UI state never authorizes a backend write.

The authenticated route hierarchy is:

```text
ProtectedRoute
└── AuthenticatedLayout
    ├── /onboarding
    ├── /seller/listings
    ├── /seller/listings/:slug/edit
    └── ProfileGate
        ├── /profile
        ├── /profile/edit
        ├── /seller/verification
        └── /sell/new
```

`/u/:handle` is the canonical public profile route and renders only the public response contract. The former `/users/:publicId` route is removed without a compatibility redirect. Profile content is rendered as React text; raw HTML injection APIs are not used.

Post-login destinations use an allowlist of existing navigation paths or validated public handles. Query strings/fragments are not used by current navigation and are never forwarded. Local fake-inbox lookups/consumption carry private identifiers in JSON bodies, not URLs. The HTML document specifies `no-referrer`; the API and reverse proxy also set Referrer-Policy.

The reset, forgot-password, sign-up and standard phone-verification pages remain placeholders through Phase 9. Existing backend workflows and the fake-SMS page retain their security controls. Public /categories is a catalog directory, not product browsing. There is no admin dashboard.

Actual request direction: src/app/router.tsx -> pages/components -> feature hooks -> feature API/Zod contracts -> centralized Axios clients in src/services -> FastAPI. Zustand owns memory-only auth identity/token/session version, not duplicate profile/catalog server state. The API clients retain version fencing, single-flight refresh, one retry and logout coordination; no browser-storage credentials or raw HTML injection.

Verified 2026-10-07: 211 tests in 15 files, TypeScript, ESLint and production build passed. This review changes no frontend code or dependencies. Browser runtime remains unverified/environment-blocked, not replaced by jsdom tests. Tailwind stays 3.4.19 and its build advisories remain release blockers. See [the complete review](PHASE_1_TO_8_ARCHITECTURE_REVIEW.md).

See [URL privacy and future routing policy](../security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md).

## Phase 9 frontend boundary (2026-10-09)

Four existing placeholders now implement listing core. Own list/manage routes are
outside ProfileGate so ACTIVE owners can read/pause/archive after losing onboarding
or verification. Creation stays inside ProfileGate; backend checks every eligible
mutation. Public `/p/:slug` is under MainLayout, not a feed/search route.

APIs reuse centralized bearer/refresh clients and strict Zod DTOs. Private keys
include user identity AND session version, private metadata, zero stale/cache
retention, and no retries. APIs reject late responses before parsing; mutations
fence cache writes/navigation by current session version. Logout removes private
queries; account switching cannot display previous drafts. Public detail is separately
keyed, no-store over HTTP, immediately stale with zero retention, and hides old data
after failed refetch. This is request-time visibility, not a real-time subscription.

Forms keep decimal prices as strings, PATCH only changed fields, and load catalog
selectors from Phase 8. Historical retired references remain unless explicitly
replaced. No raw HTML, Zustand product state, browser-storage drafts, credentials
in links. Gallery/upload was intentionally absent in Phase 9. Lifecycle errors refetch current state.

## Phase 10 image boundary (2026-10-12)

`features/productImages` owns strict image contracts, API transport and hooks;
three components own manager/private preview/public gallery UI. Central bearer,
refresh and session-version fencing are reused. Private query keys include identity
and version, with private metadata/zero retention/no retries. Logout eviction also
covers cold mutation-seeded product keys that lack query metadata. Blob URLs are
created in effects, attached to image elements and removed/revoked on replacement,
unmount, logout or account switch. Stale API/mutation results cannot restore them.

Manager uses one-file FormData with a generic filename, synchronous busy guard,
complete-ref reorder and server-authoritative returned images. Archived listings
retain preview/delete, not upload/reorder. Mutations invalidate image metadata and
owner lists, not the owner detail form, preserving unsaved listing edits. Public
gallery derives canonical trusted API paths from validated slug/ref, never trusts
arbitrary returned storage URLs, and has a zero-image/missing-file fallback.

304 tests/19 files, TypeScript, ESLint and production build pass. Real Chrome uses
fresh synthetic profile/accounts, temporary Vite + Uvicorn/MySQL/storage and 21 UI
assertions including refresh-cookie bootstrap, mobile width, visibility/cover/
archive/delete and account isolation. It does not certify every browser or a
production deployment. No dependency changes, Tailwind migration or Phase 11 code.
