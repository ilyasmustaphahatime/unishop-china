# Pre-Phase-4 Security Audit

## Scope and standard

This is a targeted review of implemented Phase 1–3 behavior, not an ASVS certification or penetration test. It uses the stable [OWASP ASVS 5.0.0](https://owasp.org/www-project-application-security-verification-standard/) and [OWASP API Security Top 10 — 2023](https://owasp.org/API-Security/editions/2023/en/0x00-toc/).

## Implemented controls

- Strict server-side Pydantic validation with unknown fields forbidden.
- Registration cannot assign roles, status, verification flags, hashes, timestamps, or administrator state.
- SQLAlchemy expressions bind request data as parameters; no request-derived raw SQL exists.
- Password hashing remains Argon2id.
- OTP storage remains HMAC-SHA256 with `hmac.compare_digest`.
- Registration assigns only `BUYER`.
- Registration has a bounded peer-address sliding-window limit and ignores forwarding headers.
- Resend retains a 60-second cooldown and five-per-hour limit.
- Verification retains expiry and five-attempt enforcement.
- Error responses hide provider errors, stack traces, constraint names, and database details.
- Production/staging force debug mode off.
- Fake SMS is fail-closed outside development, loopback-only, memory-only, disabled by default, and absent from production OpenAPI.
- Browser authentication state is process-memory only; tokens and users are not persisted in local or session storage.
- No secret-bearing `.env` file is tracked.

## OWASP API Security Top 10 mapping

| Risk | Result | Evidence or limitation |
|---|---|---|
| API1 Broken Object Level Authorization | Not applicable yet | No authenticated object endpoint exists. Phase 4 must enforce ownership server-side; frontend route guards are not authorization. |
| API2 Broken Authentication | Partial | Registration/OTP controls pass, but login and session management are intentionally not implemented. |
| API3 Broken Object Property Level Authorization | Pass for current APIs | Strict schemas and mass-assignment negative tests reject privileged properties. |
| API4 Unrestricted Resource Consumption | Partial | Registration, resend, and OTP attempts are bounded; the registration limiter is per process and no distributed limiter exists. |
| API5 Broken Function Level Authorization | Not applicable yet | No protected backend function exists; the development inbox has environment and loopback gates. |
| API6 Unrestricted Access to Sensitive Business Flows | Pass for current flows | Registration anti-automation and phone resend/verification limits have negative tests. |
| API7 Server-Side Request Forgery | Pass for current APIs | No request-controlled URL fetch exists; Tencent configuration is server-owned and disabled in tests. |
| API8 Security Misconfiguration | Pass for current scope | Debug/fake/CORS/default checks pass, local duplicate non-secret environment keys are normalized, and JavaScript/Python dependency audits are clean. |
| API9 Improper Inventory Management | Pass | OpenAPI paths are enumerated; no duplicate prefix or Phase 4 backend path exists. |
| API10 Unsafe Consumption of APIs | Pass for implemented adapter | Tencent uses configured endpoint/timeout and maps provider errors safely; no call occurs in fake/test mode. |

## ASVS 5.0.0 targeted mapping

| Area | Result | Evidence or limitation |
|---|---|---|
| Encoding, sanitization, and injection prevention | Pass | Typed validation and SQLAlchemy parameter binding; no request-derived command or raw SQL construction. |
| Validation and business logic | Pass for implemented flows | Phone/email/password/OTP validation, strict fields, transaction rollback, limits, and negative tests. |
| Authentication | Partial | Password and OTP foundations pass; Phase 4 authentication is intentionally absent. |
| Session management and tokens | Not implemented | Unsafe browser persistence was removed; Phase 4 must select a server-enforced session design. |
| Authorization | Not implemented | No protected object API exists; Phase 4 must implement deny-by-default function and object authorization. |
| Cryptography | Pass for current scope | Argon2id and keyed HMAC with constant-time comparison; secrets remain external configuration. |
| Error handling and logging | Pass | Safe errors and tests show no password, token, or OTP logging/output. |
| Configuration | Pass for current scope | Production debug and fake-provider guards pass; ignored local non-secret development keys are normalized and dependency audits are clean. |
| Data protection | Pass for current scope | No raw OTP in MySQL, no browser secret persistence, no tracked real secret. |
| API/web-service security | Partial | Current public APIs are inventoried and tested; authenticated APIs do not exist yet. |

## Dependency security

- `pip check` passes.
- `pip-audit` 2.10.1 is recorded as a development-only security tool and reports no known vulnerabilities across 72 installed backend packages.
- The patched `brace-expansion` release removes its previously reported high-severity advisory.
- The former `react-router` 7.18.1 advisory `GHSA-qwww-vcr4-c8h2` affected unstable RSC APIs. This client-rendered Vite SPA did not use that code path.
- React Router is now on patched `react-router` 8.3.0, the removed v8 `react-router-dom` compatibility package is no longer installed, and imports follow the supported v8 package layout.
- `npm audit` reports zero vulnerabilities.
- No forced audit fix, vulnerable downgrade, or unrelated dependency upgrade was performed.

## Conclusion

Current Phase 1-3 controls pass their negative security tests, dependency audits are clean, local duplicate non-secret environment keys are resolved, and the project is ready to begin Phase 4. Login, session management, and server-side object authorization remain intentionally unimplemented until Phase 4.
