# Frontend Architecture

The React application uses Router, Axios, TanStack Query, Zustand, React Hook Form, Zod, and Tailwind.

Authentication access state is memory-only in Zustand. The refresh token remains an HttpOnly cookie handled by the centralized API/session clients. `AuthBootstrap` restores a session; `ProtectedRoute` is a UX guard, never the backend authorization boundary.

Phase 6 profile server state lives in TanStack Query. Own-profile keys include the authenticated user ID in memory only and carry private metadata so session clearing removes them. Mutations update that cache, and public profiles use separate public-handle keys.

The authenticated route hierarchy is:

```text
ProtectedRoute
└── AuthenticatedLayout
    ├── /onboarding
    └── ProfileGate
        ├── /profile
        └── /profile/edit
```

`/u/:handle` is the canonical public profile route and renders only the public response contract. The former `/users/:publicId` route is removed without a compatibility redirect. Profile content is rendered as React text; raw HTML injection APIs are not used.

Post-login destinations use an allowlist of existing navigation paths or validated public handles. Query strings/fragments are not used by current navigation and are never forwarded. Local fake-inbox lookups/consumption carry private identifiers in JSON bodies, not URLs. The HTML document specifies `no-referrer`; the API and reverse proxy also set Referrer-Policy.

The reset, forgot-password, sign-up and standard phone-verification pages remain placeholders; Phase 6.1 does not implement their UI workflows. Existing backend JSON-body workflows and the local fake-SMS page retain their security controls.

See [URL privacy and future routing policy](../security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md).
