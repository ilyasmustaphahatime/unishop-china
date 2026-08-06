# Phase 4B Refresh Session Threat Model

This is a focused engineering threat model, not an OWASP ASVS certification. Test evidence refers to `test_refresh_session_security.py` and `test_refresh_session_routes.py` unless stated otherwise.

| Threat | Attack path | Control | Test evidence | Residual risk / future consideration |
|---|---|---|---|---|
| Refresh-token theft | Cookie copied from a client | High-entropy opaque value, HttpOnly, Secure in production, scoped path, short rotation lifetime | Cookie and production-config tests | XSS or endpoint compromise can still act as the user; Phase 4C needs CSP and careful client handling |
| Database token leakage | Attacker reads `refresh_tokens` | Only SHA-256 hashes and CSRF hashes are stored | Login hash-only test and model audit | An online attacker with DB write access can corrupt sessions |
| Replay and reuse | A rotated/older token is submitted | Single-use rotation and family-wide `reuse_detected` revocation | Rotation/reuse integration test | Strict detection can terminate a family during a legitimate client race |
| Rotation race / concurrent refresh | Two requests submit one parent | Transaction, `SELECT FOR UPDATE`, unique hash, atomic insert/revoke/link | Deterministic two-thread MySQL test | Phase 4C must use single-flight refresh |
| Transaction partial failure | Child insert succeeds but parent state fails, or reverse | Service-owned transaction/savepoint; cookies set only after return/commit | Injected repository failure test | Database outage returns generic 500 and requires login if client state is uncertain |
| CSRF | Foreign site automatically sends cookies | SameSite=Lax, exact Origin check, double-submit cookie/header, DB-bound CSRF hash | Missing/mismatched/header/cookie/foreign-Origin tests | XSS can read the CSRF cookie; CSP and frontend hygiene remain necessary |
| Login CSRF / session fixation | Foreign login or attacker-selected old cookie | Present Origin must be exact; password login always creates a new UUID family and replaces cookies | Foreign login and separate-family tests | Non-browser clients without Origin remain intentionally supported |
| Logout CSRF | Foreign site ends a session | Origin and database-bound double-submit CSRF when cookie exists | Logout CSRF/Origin tests | Missing-cookie logout intentionally remains harmless/idempotent |
| Logout-all authorization bypass | Client submits another user ID | Bearer `get_current_user`; no body or client-selected identity | User-scoped logout-all tests | Issued access token remains valid until expiry |
| User-to-user revocation | Repository query is broadened | Family ID or authenticated internal user ID predicates; parameterized SQLAlchemy | Independent-user/family tests | Application/DB administrator compromise is outside this control |
| Cookie scope/transmission error | Cookie leaks to broad domain/path or HTTP production | No Domain, auth-only path, production Secure guard, SameSite validation | Cookie helper and configuration tests | Subdomain architecture changes require a new review |
| Credentialed CORS error | Arbitrary Origin receives credentialed response | Explicit origins only; wildcard rejected; narrow methods/headers | CORS and foreign-Origin regression tests | Reverse-proxy origin rewriting must be configured safely |
| Weak randomness / hash leakage | Guessable token or token/hash returned/logged | `secrets.token_urlsafe(64/32)`, SHA-256, schema-bound responses, no logging | Randomness/hash tests and secret scan | Runtime memory and TLS endpoint security remain trusted |
| Session-family exhaustion | Repeated logins grow rows and active devices | Per-user ACTIVE family cap; oldest family revoked transactionally | Family-limit test | Historical revoked rows need a future bounded retention job |
| Absolute-lifetime bypass | Repeated rotation extends login forever | Immutable family expiry and child expiry clamping | Rotation and absolute-expiry tests | User must reauthenticate after the limit |
| Inactive-account refresh | Suspended user renews access | User reloaded and locked; non-ACTIVE family revoked | Inactive-account test | Existing access JWT can live for up to 15 minutes |
| Sensitive logging | Tokens, cookies, passwords, OTPs, secrets reach logs | No logging in session path; safe generic responses; tracked-secret audit | Capture/log scans and response tests | Infrastructure access logs must also redact Authorization/Cookie headers |
| Rate-limit bypass / DoS | Header spoofing, many tokens, unbounded keys | Actual peer, HMAC session keys, user keys, bounded thread-safe limiter, Retry-After | Rate-dimension and bounded-limiter tests | Shared Redis-class limiter needed for horizontal deployment and stronger distributed abuse resistance |
| Access token after logout | JWT remains usable | Fifteen-minute maximum, database status reload for `/me` | Phase 4A token tests | Immediate revocation requires a future blacklist/version design |

## OWASP mapping

- OWASP API Security Top 10 (2023): API1 Broken Object Level Authorization (user-scoped logout-all); API2 Broken Authentication (opaque rotation, replay detection, account reload); API4 Unrestricted Resource Consumption (family and rate limits); API5 Broken Function Level Authorization (bearer-protected logout-all); API7 SSRF is not introduced because session code performs no outbound request; API8 Security Misconfiguration (cookie/CORS/startup guards); API10 Unsafe Consumption is not introduced.
- OWASP ASVS 5.0 areas relevant to authentication, session management, access control, validation and encoding, cryptography, secure configuration, and error handling/logging. Controls are mapped as engineering guidance only; no compliance or certification claim is made. The official ASVS project page is the source of truth for versioned requirement identifiers.
