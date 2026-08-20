# Phase 4C Frontend Authentication Threat Model

This is a focused engineering review against relevant OWASP ASVS 5.0 authentication, session, access-control, validation, and browser-client themes and OWASP API Security Top 10 2023 risks. It is not a certification.

| Threat | Attack path | Current control and test evidence | Residual risk / future work |
| --- | --- | --- | --- |
| Access-token theft through persistence | Read token after reload or from browser storage | Token exists only in Zustand memory; storage spies and browser-storage assertions cover non-persistence | Active-page XSS can still use memory token |
| Access-token theft through XSS | Inject script into the application | Auth code introduces no raw HTML, eval, document.write, or token logging; refresh token remains HttpOnly | Add a production CSP and continue component-level XSS review |
| Refresh-token JavaScript exposure | Read or copy the long-lived credential | Refresh cookie is HttpOnly and only browser-managed; frontend has no refresh-token field or reader | Browser or host compromise remains out of scope |
| CSRF misuse | Forge refresh/logout using ambient cookie | Double-submit CSRF plus exact Origin checks; frontend re-reads current CSRF and sends `X-CSRF-Token`; tests cover rotation and logout | XSS can read the non-credential CSRF value and make same-origin actions |
| CSRF cookie-path incompatibility | Scope readable cookie to API path so app route cannot read it | Real-browser gate demonstrated the defect; CSRF path changed to `/`, refresh path remains narrow; backend path tests added | Deployment path changes require a browser regression |
| Credentialed CORS abuse | Send cookies to arbitrary origins | Credential mode exists only on session client; backend uses exact allowed origins, never wildcard credentials | Production origin changes require configuration review |
| Open redirect | Supply an external return location | Same-origin internal-path validator rejects absolute, scheme-relative, script/data, and backslash paths; negative tests added | Future redirect features must reuse the validator |
| Login CSRF / session fixation | Force a victim into an attacker-selected session | Backend exact Origin policy and new family on login; frontend uses the established credentialed login contract | Shared-device user confusion remains a general UX concern |
| Concurrent refresh race | Several expired requests rotate one single-use token | One shared Promise per page; deterministic five-request success/failure tests prove one refresh | Multiple tabs do not share the coordinator |
| Backend reuse detection triggered by frontend | Duplicate rotation makes a legitimate family look reused | Same single-flight control and one-retry marker | Cross-tab simultaneous refresh can still trigger strict reuse defense |
| Infinite refresh loop | 401 → refresh → retry repeatedly | Requires Bearer challenge and header, excludes public auth endpoints, marks retry, and clears after retry 401; test proves two request attempts and one refresh | Misconfigured APIs without correct challenge do not auto-refresh |
| Request replay or mutation loss | Retry changes body, method, query, or uses stale token | Axios retries the original config once and replaces Authorization; concurrent tests preserve query and verify new header | Non-idempotent future endpoints should assess server idempotency separately |
| Stale token | Module captures token before rotation | Request interceptor reads Zustand immediately before each request | An already in-flight request may still return 401 and join refresh |
| Cross-user query-cache leakage | User B sees private data cached for user A | Logout, logout-all, and refresh failure remove `auth` and `meta.private` queries; public cache remains; isolation tests added | Future private hooks must mark keys consistently |
| Sensitive console logging | Axios error or cookie/token is printed | Auth catches render safe messages and contain no console logging; source scans cover auth terms and logging APIs | Future diagnostics must log only safe status/path metadata |
| Password logging or retention | Log request object or retain form secret | Login request is never logged or cached; successful login resets password field | Browser extensions and compromised devices remain out of scope |
| Client role tampering | Modify Zustand roles to display privileged UI | Role routes are documented as UX only; backend remains authoritative | Every future backend object/function action needs deny-by-default authorization |
| ProtectedRoute bypass | Navigate directly or change local state | Guard protects navigation only and makes no security claim | Backend APIs must never trust route state |
| Session bootstrap confusion | Render guest/private UI before identity is known | Explicit bootstrapping state and accessible loading UI; success/no-session/failure tests | Temporary backend failure uses safe guest state rather than offline recovery |
| Network logout failure | Local clear occurs but revoke request never arrives | `finally` clears memory/cache; UI warns revocation was not confirmed | Cookie session may restore after reload until server revocation/expiry |
| 401 retry storm | Every failure launches refresh | Bearer challenge, eligible path, shared Promise, and one-retry marker bound requests | A broad backend outage still surfaces failures but does not loop |
| 429 retry storm | Client automatically retries a limited auth endpoint | Session client has no response retry; UI shows safe rate-limit messaging | Process-local backend limits need a shared store before scaling |
| Multi-tab refresh race | Two tabs rotate the same cookie concurrently | Backend reuse detection remains strict; limitation documented and not hidden | Consider BroadcastChannel or another deliberate coordinator in a later phase |

## API and ASVS review summary

- Broken object/function authorization is not claimed solved by React roles or routes; future APIs must authorize server-side.
- Authentication flows use generic errors, bounded backend rate limits, short-lived access JWTs, rotating HttpOnly refresh sessions, CSRF, and safe contract validation.
- Resource consumption is bounded by client one-retry behavior and backend rate limits; the frontend does not retry 429 responses.
- Security misconfiguration checks cover exact credentialed origins, cookie flags/paths, environment secrets, dependency audits, and production-bundle isolation.
- Unsafe API consumption is reduced by strict runtime validation of login, refresh, and `/auth/me` JSON before state changes.
