# Phase 4C: Secure Frontend Authentication

## Verification status

**Phase 4C — Secure Frontend Authentication: COMPLETE.**

Implementation and automated security gates are complete. The final real-browser gate also passed using explicit user-verified evidence; it was not performed or observed by browser automation.

Browser verification source: **USER-VERIFIED PASS**

- LocalStorage authentication token: PASS — no authentication token present.
- SessionStorage authentication token: PASS — no authentication token present.
- Refresh cookie security: PASS — `HttpOnly=true`, `Path=/api/v1/auth`.
- CSRF cookie security: PASS — `HttpOnly=false`, `Path=/`.
- F5 session restoration: PASS — the authenticated Buyer Dashboard remained authenticated.
- Logout + F5: PASS — the user remained logged out after reload.
- Logout everywhere + F5: PASS — the user remained logged out after reload.

Browser result: **7 / 7 USER-VERIFIED CHECKS PASSED**.

Phase 4D — Final Authentication Security Audit is **NOT STARTED**. Phase 4C is ready to hand off to Phase 4D, but Phase 4D is outside this task and has not been started.

## Scope and backend assumptions

Phase 4C connects the existing React application to the Phase 4A access-token and Phase 4B refresh-session APIs. It does not add password reset, OAuth, MFA, seller verification, marketplace features, a session-device API, token persistence, or a database migration. Backend identity, account-state checks, role checks, function authorization, and future object authorization remain authoritative.

The integration assumes a same-site production topology compatible with `SameSite=Lax`. A frontend and API on unrelated sites require a deliberate cookie, CORS, and CSRF policy review; this implementation does not silently weaken SameSite.

## Authentication state

The one active Zustand store contains only:

- `status`: `bootstrapping`, `authenticated`, or `unauthenticated`;
- the short-lived access token in JavaScript memory;
- the backend-provided safe user, including roles and email/phone verification flags.

No persist middleware is used. Authentication data is not written to localStorage, sessionStorage, IndexedDB, Cache Storage, URLs, DOM attributes, or JavaScript-readable authentication cookies. Passwords remain local to the login form and are cleared after success.

## Login and safe navigation

The existing login form calls `POST /api/v1/auth/login` through the credentialed session client. The client accepts the refresh and CSRF cookies, validates the JSON contract, stores only the access token and safe user in memory, and selects a role-aware default view for UX. Login validation requires non-empty bounded values and intentionally does not reuse registration password-strength rules.

401 and 403 responses share generic wording. Validation, rate-limit, server, and network failures use safe messages without rendering response internals or logging Axios objects. A return destination must be a same-origin path beginning with one `/`; external URLs, scheme-relative URLs, script/data URLs, and backslash-based paths fall back to a known dashboard.

## HTTP and CSRF boundaries

The existing normal `apiClient` has no global credential mode. Immediately before an eligible protected request, it reads the current in-memory token and adds `Authorization: Bearer`. Public authentication routes do not receive this header; `/auth/me` is the only current `/auth/*` endpoint using the normal bearer client.

The dedicated `sessionClient` has `withCredentials=true` only for login, refresh, logout, and logout-all. It has no automatic bearer interceptor; logout-all supplies its current access token explicitly.

The refresh cookie remains HttpOnly with path `/api/v1/auth`. Real-browser pre-implementation testing proved that a CSRF cookie with that same path was not readable from the frontend route. The minimal backend repair gives the non-credential CSRF cookie path `/`, keeps it non-HttpOnly, and deletes each cookie using its matching path. The frontend reads only `unishop_csrf_token`, immediately before refresh or current-session logout, and never caches or logs it.

## Bootstrap and reload behavior

`AuthBootstrap` starts while the store is `bootstrapping`. With no readable CSRF cookie, it makes no refresh call and settles as unauthenticated. With a possible browser session, it performs one credentialed refresh, stores the new token in memory, calls `/auth/me`, validates the safe-user response, and marks the session authenticated.

Any refresh, `/auth/me`, contract, server, or network failure clears token, user, and private cache and settles as unauthenticated. This deterministic MVP policy does not preserve stale identity or create automatic request storms. Guards render an accessible status until bootstrap settles, preventing login-page flicker before session restoration.

## Automatic refresh and retry

The normal client considers automatic refresh only when all of these are true:

- the response is 401 with a Bearer `WWW-Authenticate` challenge;
- the original request carried an access token;
- the endpoint accepts bearer authentication;
- the request has not already been refresh-retried.

A module-level shared Promise permits exactly one refresh for a concurrent 401 burst in one page context. All waiters receive the same new token and retry their original method, body, query, and headers once with the stale Authorization value replaced. Refresh failure rejects all waiters and clears local authentication. A second 401 after retry clears the session and never refreshes again.

This single-flight boundary is per JavaScript page/tab. Multiple tabs share rotating cookies but not the Promise or in-memory token, so simultaneous cross-tab refresh remains a documented residual risk. BroadcastChannel coordination is deferred rather than weakening backend reuse detection.

## Routes, roles, and verification

`ProtectedRoute` waits during bootstrap, redirects guests to login with internal location state, and renders authenticated children. `GuestRoute` waits during bootstrap, renders guests, and redirects authenticated users to an existing role-aware dashboard. `RoleRoute` is explicitly a navigation convenience only. Backend dependencies remain the security boundary.

The safe user keeps backend roles, `email_verified`, and `phone_verified`. Phase 4C does not invent seller/admin permission changes or enforce verification only in the browser.

## Logout and cache isolation

Current-session logout re-reads CSRF, sends it to `POST /auth/logout`, and always clears local identity and private query cache in a `finally` block. Logout-all sends no body or user ID; the bearer token is the sole target identity. Both use the credentialed client so clear-cookie responses are honored and both navigate to login. Buttons are disabled while a request is pending.

If network logout cannot be confirmed, the login page shows a safe warning. Local identity is still removed, but the server refresh family may remain valid if the request never arrived. Access tokens on other clients can remain valid until their maximum 15-minute expiry after logout-all.

Only queries keyed under `auth` or explicitly marked `meta.private=true` are removed, preserving public marketplace cache while preventing cross-user private-data display.

## Security decisions and testing

Tests cover store lifecycle and storage non-use, cookie decoding, runtime contracts, login mapping and generic errors, open-redirect rejection, bootstrap success/no-session/failures, dynamic bearer injection, public-auth exclusions, one-retry loop protection, rotated CSRF reads, logout/logout-all, private-cache isolation, and both success and failure for five simultaneous 401 requests. The concurrency tests use controlled Promises and prove exactly one refresh call without sleep-based timing.

The backend cookie repair is covered by unit and integration assertions for separate Set-Cookie and delete-cookie paths. Full backend regression, frontend typecheck/lint/tests/build, dependency audits, database preservation, and Alembic checks are completion gates.

## Known limitations and Phase 4D handoff

- XSS in an active page can act with the in-memory access token; production CSP and broader XSS hardening remain important.
- Single-flight does not coordinate multiple tabs.
- Network-failed logout cannot prove server revocation.
- Backend rate limits remain process-local until a shared production limiter is introduced.
- The current same-site cookie topology must be reviewed before any unrelated-site deployment.
- Phase 4D remains not started and should address only its separately approved scope.
- Ready for Phase 4D: **YES**.
