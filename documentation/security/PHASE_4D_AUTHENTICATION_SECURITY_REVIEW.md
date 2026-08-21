# Phase 4D Authentication Security Review

Review window: 2026-08-20 to 2026-08-21

Baseline: `feature/authentication` at `a9f5bbec39a192dbab7408ae2be01dc350acc3e1`

Result: **PASSED WITH NON-BLOCKING WARNINGS**

## Review statement

This document is a targeted engineering security review of the UniShop China Phase 1-4C authentication implementation. It combines source inspection, negative automated tests, production-configuration simulation, dependency scanning, live MySQL integrity checks, isolated end-to-end flows, and existing user-verified browser evidence.

It is not a penetration test, an external assurance report, legal advice, an OWASP endorsement, or an OWASP ASVS certification. “Implemented” means the reviewed control exists and its cited project evidence passed in this development environment.

## Security architecture summary

### Trust boundaries

- The browser holds the short-lived access JWT only in JavaScript memory.
- The opaque refresh token is a server-set HttpOnly cookie scoped to `/api/v1/auth`.
- The browser-readable CSRF cookie is a separate random value; it is never the refresh token.
- The API validates access JWT signature, algorithm, issuer, audience, time claims, type, JTI, and UUID subject.
- The API reloads user status and roles from MySQL for `/auth/me`; frontend roles are navigation hints only.
- MySQL stores Argon2id password hashes, HMAC-SHA256 OTP hashes, SHA-256 refresh/CSRF hashes, and no raw authentication secret.
- Session mutation uses transactions, refresh-row locking, family IDs, replacement links, reuse detection, and exact user/family scoping.
- Browser session endpoints require an allowed Origin when one is supplied; refresh/logout additionally require CSRF cookie/header/DB binding.
- CORS uses explicit origins with credentials and never a wildcard.

### Security invariants

1. A client cannot choose the `/auth/me` or logout-all user target.
2. A refresh token grants no access unless its hash exists, the row and family are live, the user is active, and CSRF binding succeeds.
3. Successful rotation revokes the parent and creates exactly one linked child in the same family.
4. Reusing a revoked token revokes only its family, not another family or another user.
5. Raw refresh and CSRF values are emitted only as cookies after a successful commit and never persisted.
6. Frontend authentication state is cleared together with private auth/query cache on logout or irrecoverable refresh failure.

## Verified controls

| Area | Implemented control | Evidence |
|---|---|---|
| Passwords | Argon2id recommended hasher; strict registration policy; whitespace preserved; dummy-hash path | Unit/integration password and login tests |
| Registration | Strict schemas, normalization, `BUYER` only, safe uniqueness/rollback, peer limiting | Registration unit/integration suite and live email/phone flows |
| OTP | Six ASCII digits, cryptographic generation, HMAC-SHA256, expiry/attempt/resend limits | OTP unit/integration and live phone verification |
| Fake SMS | Explicit dev flag, fake provider, actual-loopback validation, bounded expiring memory | Dev-route tests and production simulation |
| Login | Generic failures, inactive-state check, no cookies on failure, peer and HMAC-identifier limits | Login and refresh-session integration tests |
| JWT | HS256 allow-list, required safe claims, issuer/audience/time/type/subject/JTI validation | 33 access-token tests after Phase 4D additions |
| Refresh | Opaque high-entropy token, hash-only DB, seven-day token, 30-day family | Refresh unit/integration and live rotation flows |
| Rotation | Row lock, one child, replacement FK, bounded collision retry, commit before cookies | Transaction/concurrency tests and database inspection |
| Reuse | Whole compromised-family revocation, generic public 401 | Automated reuse and live A-B-C replay tests |
| CSRF | Double submit, constant-time comparison, DB hash binding, Origin restriction | CSRF unit/integration tests |
| Cookies | HttpOnly refresh; separate readable CSRF; scoped paths; Lax; Secure guard | Cookie tests and user-verified browser evidence |
| Logout | Family-scoped, CSRF protected, idempotent, matching cookie deletion | Integration and live isolation tests |
| Logout-all | Bearer-derived target, all current-user families, other users preserved | Integration and live isolation tests |
| Frontend | Memory-only Zustand state, single-flight refresh, bounded retry, safe redirects | 49 frontend tests, source scans, production build |
| Configuration | Fail-closed production secret/cookie/CORS/Fake-SMS checks | Unit tests and isolated production simulation |
| Dependencies | Python and npm dependency audits | `pip-audit`, `pip check`, both npm audits |

## OWASP API Security Top 10 (2023) targeted review

| Item | Applicable | Current control and evidence | Residual risk | Future control |
|---|---|---|---|---|
| API1 Broken Object Level Authorization | Yes | Authentication endpoints derive user/family targets from validated token/cookie state; cross-user and cross-family revocation tests pass. No marketplace object endpoint is active. | Future marketplace resources will create new object targets not covered by auth-only tests. | Require owner/role checks in every object query, deny by default, and add cross-user negative tests per endpoint. |
| API2 Broken Authentication | Yes | Argon2id, generic login errors, dummy hashing, bounded login/OTP/session requests, strict JWT validation, hash-only refresh sessions, rotation/reuse, CSRF, logout. | Access JWT revocation delay, process-local limiting, cross-tab refresh race. | Distributed throttling, monitoring, password-recovery hardening, optional stronger authenticators in later phases. |
| API3 Broken Object Property Level Authorization | Yes | Pydantic requests/responses forbid extra fields; registration cannot set roles/status/verification/hash fields; safe user response excludes hashes and session secrets. | Future profile/product schemas may expose or accept sensitive fields. | Maintain explicit allow-list DTOs, role-aware field policy, and negative mass-assignment tests. |
| API4 Unrestricted Resource Consumption | Yes | Input lengths, OTP limits, session-family cap, bounded in-memory limiter stores, bounded fake inbox, request timeout, refresh collision cap, `Retry-After`. | Limits are per process and can be bypassed across replicas; no edge/WAF limits yet. | Shared distributed limits, gateway body/time/concurrency limits, quotas, abuse alerting. |
| API5 Broken Function Level Authorization | Yes | `/auth/me` and logout-all require validated Bearer identity; session mutation does not accept role/user selectors; frontend role guard states it is UI-only. | Marketplace/admin functions are scaffold placeholders and have no implemented backend authorization. | Backend role/permission dependency plus deny-by-default endpoint policy and negative role tests. |
| API6 Unrestricted Access to Sensitive Business Flows | Yes | Registration, login, OTP resend/verify, refresh, logout, and logout-all have relevant limits or attempt controls; responses are generic. | Distributed bot defense and behavioral monitoring are not deployed. | Shared throttling, anomaly detection, challenge/escalation policy, security analytics. |
| API7 Server Side Request Forgery | No for current auth input | Auth clients cannot supply a destination URL. Tencent endpoint is server configuration and its adapter has a bounded timeout/no retry. | A compromised configuration source could redirect a provider endpoint; real provider is not enabled. | Allow-list provider endpoints and apply egress controls before production provider activation. |
| API8 Security Misconfiguration | Yes | Production rejects weak/missing JWT secret, unsupported algorithm, insecure cookie policy, unsafe SameSite/path/name, wildcard CORS, Fake SMS; debug forced off. | TLS, CSP, secret manager, monitoring, hardened images are deployment responsibilities. | Deployment policy-as-code, CSP/security headers, TLS validation, secret rotation, image/config scanning. |
| API9 Improper Inventory Management | Yes | OpenAPI has 14 operations, eight expected auth operations, no duplicate IDs, no Phase 5 route, and dev Fake SMS is absent in production simulation. | Scaffold placeholder files/pages can be mistaken for implemented API scope if inventory is not maintained. | Versioned API inventory, owner/deprecation metadata, production route diff gates. |
| API10 Unsafe Consumption of APIs | Yes | Tencent errors map to safe categories, request timeout is bounded, no retry occurs, provider result is checked, credentials are secret types. Real Tencent was not called. | Real provider response/availability behavior remains unvalidated. | Contract tests in a controlled sandbox, certificate/endpoint allow-listing, telemetry with redaction, provider failover policy. |

Critical API Top 10 gap in the implemented auth scope: **none found**. API1/API3/API5 must be reassessed for every future marketplace object/function; this audit does not claim those future controls exist.

## OWASP ASVS 5.0 targeted review

The review used the requested control domains without claiming formal level verification or certification.

| Domain | Classification | Review result | Remaining work |
|---|---|---|---|
| Authentication | Implemented for Phase 1-4D | Generic login, dummy hash, account-state checks, JWT authentication, rate limits pass | Recovery, email verification, stronger authenticators are later scope |
| Password security | Implemented | Argon2id and registration policy; no plaintext persistence/logging; legacy login preserves input | Password change/reset and compromised-password screening deferred |
| Session management | Implemented with accepted limitations | Opaque hash-only refresh, cookies, CSRF, rotation, reuse, families, limits, logout | Cross-tab coordination and immediate access-JWT revocation deferred |
| Access control | Partially implemented | Auth identity and session/user scoping pass; backend is documented authority | Marketplace object/function authorization does not exist yet |
| Input validation | Implemented for auth APIs | Strict Pydantic/Zod contracts, length/format normalization, unknown fields rejected | Continue endpoint-specific schemas in future APIs |
| Cryptography | Implemented for current scope | Argon2id, HMAC-SHA256 OTP, SHA-256 token hashes, secure random tokens, HS256 allow-list | Production key lifecycle/rotation and managed storage pending |
| Secure configuration | Implemented in application; deployment partial | Fail-closed production simulation, explicit CORS, dev capability removal | TLS, CSP, hardened containers, secret manager and config scanning pending |
| Error handling | Implemented | Generic 401/403/500/provider errors; no stack/database/provider detail | Central production error telemetry with redaction pending |
| Logging and monitoring | Partially implemented | Sensitive logging scans pass; database health logs only safe class/code | Security-event audit trail, correlation, monitoring and alerting pending |
| API/web services | Implemented for auth inventory | Strict route inventory, bearer challenge, cache-control, CORS, dependency checks | Formal gateway/edge controls and future API authorization pending |
| Client-side security | Implemented with deployment partial | Memory-only state, HttpOnly refresh, no storage, no unsafe sinks/logging, safe redirect/cache | Production CSP, SRI/asset policy as applicable, cross-tab coordination pending |

Summary classifications:

- Implemented: authentication core, password storage/verification, refresh sessions, auth input validation, current cryptography, safe errors, current auth API controls, frontend auth-state protections.
- Partially implemented: broader access control, production configuration deployment, security logging/monitoring, client deployment hardening.
- Deferred: account recovery/change, email verification, distributed limits, cross-tab refresh coordination, real SMS, immediate access-token revocation, stronger authenticators.
- Not applicable in current auth scope: user-controlled outbound URL fetching and marketplace object authorization implementation.
- Certification claimed: **NO**.

## Authentication threat model

| Threat | Control | Evidence | Residual risk |
|---|---|---|---|
| Credential stuffing | Peer and HMAC-identifier login limits, generic errors, Argon2id | Rate-limit and enumeration tests | Process-local limits; no bot reputation/challenge layer |
| Brute force | Five peer logins/minute and ten identifier attempts/15 minutes | Deterministic limiter and `Retry-After` tests | Distributed attacker/replica bypass until shared limiter |
| User enumeration | Unknown/wrong/inactive login response parity and dummy hash; generic unknown-phone resend | Login and phone-verification tests | Registration duplicate responses intentionally identify conflicts in current product design |
| Password cracking after DB theft | Argon2id password hashes | Hash-format/verification tests and model inspection | Strength depends on user password and production DB protection |
| Weak passwords | Registration length/upper/lower/digit policy | Negative schema tests | No compromised-password service; existing login intentionally accepts legacy passwords |
| OTP brute force | Six digits, five-attempt cap, expiry, resend/hourly limits | OTP attempt/expiry/rate tests | Limits are database/account scoped; broader distributed abuse controls pending |
| OTP replay | Latest code only, verified marker, user verified state, fake message consumption | Old/new code and consumption tests | Real provider delivery-channel compromise remains external |
| OTP leakage | HMAC-only DB, no normal API/log output, local inbox isolated | DB/source/log tests | Local dev inbox deliberately exposes OTP to loopback when explicitly enabled |
| Fake SMS exposure | Development + explicit flag + fake provider + actual-loopback check; production route absent | Unit/integration and production simulation | Local machine compromise remains out of application scope |
| JWT forgery | Strong configured secret, HS256 allow-list, signature/issuer/audience verification | Wrong signature, modified, none/unsupported algorithm tests | Production secret custody and rotation pending |
| JWT replay | Short 15-minute expiry, DB state recheck on `/auth/me` | Lifetime/claims/me tests | No access-token blacklist; accepted 15-minute residual |
| Refresh-token theft | HttpOnly scoped cookie, Secure production guard, SameSite, Origin and CSRF checks | Cookie/CSRF/config/browser evidence | Malware/XSS can still act from an active origin; TLS/CSP required |
| Refresh-token database theft | Only SHA-256 hashes stored; token has high entropy | Hash-only DB tests and schema inspection | Online session abuse still possible through compromised application tier |
| Refresh replay | Parent revocation, replacement link, family-wide reuse response | Automated and live A-B-C replay | A replay intentionally invalidates legitimate tokens in that family |
| Rotation race | `SELECT ... FOR UPDATE`, transaction, unique hash, bounded collision retry | Deterministic concurrent refresh test | Cross-tab race may trigger safe family revocation and UX disruption |
| Token-family theft | Random family UUID, DB-bound user/family, absolute expiry | Family schema and isolation flows | Device/family management UI is deferred |
| CSRF | Separate token, cookie/header constant-time equality, DB hash binding, Origin validation | Missing/mismatch/foreign-origin tests | Same-site topology assumption must hold in deployment |
| Login CSRF | Exact allowed Origin when supplied and explicit CORS | Foreign-origin login creates no session | Non-browser requests without Origin remain allowed by design |
| Session fixation | Server generates new random refresh/CSRF/family at login; rotation replaces both | Login/rotation cookie tests | Browser compromise can interfere with its own session |
| CORS abuse | Explicit allowed origins, credentials enabled, no wildcard, fixed headers/methods | Middleware test and production wildcard rejection | Deployment origin changes require reviewed configuration |
| Origin spoofing | Server reads actual Origin and actual connection peer; ignores forwarding headers | Foreign Origin and forged-forwarding tests | Trusted-proxy deployment needs a deliberate peer-trust design |
| XSS token access | Access token memory-only; refresh HttpOnly; no dangerous sink in reviewed frontend | Source scan and storage/cookie tests | XSS can act with in-memory token; CSP and prevention remain essential |
| Token persistence | No Zustand persist, localStorage, sessionStorage, IndexedDB, tokenStorage | Source scan, tests, 7/7 browser evidence | Browser process memory remains accessible to same-origin script |
| Cache leakage | Auth responses no-store; private auth/query cache cleared | Backend cache headers and frontend cache-isolation tests | Future private query keys must be marked private consistently |
| Open redirect | Same-origin single-slash path parser; external/scheme/script/data/backslash rejected | Route-path tests | Future redirect helpers must reuse the same policy |
| Logout CSRF | Current logout requires Origin and CSRF when a token exists | Logout CSRF tests | Missing-token logout is idempotently accepted and only clears local cookies |
| Logout-all authorization bypass | Valid Bearer required; user ID comes only from token | No-body/other-user integration and live tests | Access JWT remains usable until expiry |
| Cross-user revocation | Repository filters by validated current user; family operations use stored family | User/family live isolation and integration tests | Future admin/session APIs will require new authorization review |
| Multi-tab race | Backend row locking and reuse detection fail safely | Concurrent backend test | Frontend single-flight is per tab, so safe family revocation/UX disruption can occur |
| Rate-limit bypass | Actual peer, HMAC identifier/token keys, bounded store, forwarding headers ignored | Rate-limit key/peer tests | Multi-process/distributed bypass accepted until shared store |
| Sensitive logging | No frontend console use; backend AST/source scans; safe DB health event | Static scans and fake-SMS no-output tests | Production security logging design is not yet deployed |
| Production misconfiguration | Startup validation rejects insecure auth/session/Fake-SMS settings; debug forced off | Isolated production simulation | Infrastructure/TLS/header/secret-manager controls remain external |
| Secret leakage | `.env` ignored, examples tracked, secret types, no bundle secrets or tracked credential files | Git/env/bundle/tracked-file scans | Operational handling and rotation processes still required |
| Unsafe third-party provider behavior | Bounded timeout, no retry, safe error mapping, delivery status check | Provider unit tests | Real Tencent sandbox/production behavior is pending |

## CORS and rate-limit review

| Control | Verified setting/result |
|---|---|
| Credentialed CORS | Enabled only with explicit origins |
| Wildcard origin | Rejected |
| Allowed session header | `X-CSRF-Token` explicitly allowed |
| Foreign session Origin | Rejected |
| Registration | 20 per 60 seconds per connection peer; bounded store |
| Login peer | 5 per 60 seconds |
| Login identifier | 10 per 15 minutes using an HMAC key |
| Refresh peer | 20 per 60 seconds |
| Refresh session | 10 per 60 seconds using an HMAC key |
| Logout peer | 10 per 60 seconds |
| Logout-all user | 5 per 60 seconds using authenticated user ID |
| Excess response | Safe 429 with `Retry-After` |
| Forwarded header | Does not override actual peer |
| Distributed store | Not implemented; accepted pre-production limitation |

SameSite Lax assumes frontend and API remain same-site in production. A truly cross-site topology is an architecture change requiring explicit cookie, CORS, Origin, CSRF, and browser-compatibility review; it must not be handled by merely weakening SameSite.

## Production configuration review

The isolated production simulation passed all required fail-closed cases:

- missing, weak, and placeholder JWT secret blocked;
- unsupported JWT algorithm blocked;
- insecure refresh cookie blocked;
- unsafe SameSite blocked;
- invalid cookie name/path blocked;
- absolute lifetime shorter than refresh lifetime blocked;
- wildcard credentialed CORS blocked;
- Fake SMS provider and Fake inbox blocked;
- debug resolved to false;
- development Fake SMS routes absent.

The frontend production build passed and contained no backend JWT/database/Tencent/OTP secret identifiers, no local Fake SMS endpoint/module, and no auth debug logging. No real Tencent call or real SMS occurred during the audit.

## Residual risks and disposition

| # | Residual risk | Disposition |
|---:|---|---|
| 1 | Access JWT remains valid for up to 15 minutes after logout/logout-all | Accepted MVP limitation |
| 2 | Rate limiting is process-local | Accepted pre-production limitation; distributed store required before scale |
| 3 | Refresh single-flight is per tab | Accepted MVP UX/availability risk; backend fails safely |
| 4 | Real Tencent SMS is pending | Deferred integration scope |
| 5 | TLS, CSP, monitoring, secret rotation and distributed limiting are not deployed | Production prerequisites |
| 6 | Docker image build was not rechecked because Docker CLI was unavailable | Tooling verification limitation |
| 7 | Starlette TestClient emits one third-party deprecation warning | Non-security dependency warning |
| 8 | No standalone npm typecheck script exists | Non-blocking tooling gap; direct and build type checks pass |

## Blocking issues

None. No critical or high authentication issue remains in the Phase 1-4D scope.

## Security requirements for Phase 5

Phase 5 may proceed only as a separately approved change. Password recovery/change and email verification should preserve these controls:

- generic account-discovery responses and bounded delivery/verification attempts;
- cryptographically random, hashed, short-lived, single-use recovery material;
- strict request/response schemas and no client-selected target user after authentication;
- atomic consumption/change transactions;
- password hashing through the central Argon2id helper;
- revocation of all refresh families after a successful password change/reset;
- safe notification and provider error handling;
- no recovery material in URLs, logs, browser storage, analytics, or response bodies beyond the intended delivery channel;
- negative tests for enumeration, replay, race, cross-user targeting, mass assignment, rate limits, rollback, and sensitive logging.

**PHASE 4D COMPLETE: YES**

**AUTHENTICATION SECURITY REGRESSION: PASSED**

**READY FOR PHASE 5: YES**
