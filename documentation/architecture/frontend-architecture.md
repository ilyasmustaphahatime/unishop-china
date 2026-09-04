# Frontend Architecture

The React application uses Router, Axios, TanStack Query, Zustand, React Hook Form, Zod, and Tailwind.

Authentication access state is memory-only in Zustand. The refresh token remains an HttpOnly cookie handled by the centralized API/session clients. `AuthBootstrap` restores a session; `ProtectedRoute` is a UX guard, never the backend authorization boundary.

Phase 6 profile server state lives in TanStack Query. Own-profile keys include the authenticated user ID and carry private metadata so session clearing removes them. Mutations update that cache, and public profiles use separate public-ID keys.

The authenticated route hierarchy is:

```text
ProtectedRoute
└── AuthenticatedLayout
    ├── /onboarding
    └── ProfileGate
        ├── /profile
        └── /profile/edit
```

`/users/:publicId` is intentionally public and renders only the public response contract. Profile content is rendered as React text; raw HTML injection APIs are not used.
