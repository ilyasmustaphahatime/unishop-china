# Final Pre-Phase-7 Security Audit

Audit date: 2026-09-05. Scope: the committed application through Phase 6 plus the focused fixes below. Evidence distinguishes executed tests, source review, accepted limitations, and unavailable tooling. No certification is claimed.

## 1. EXECUTIVE RESULT

Pre-Phase-7 security gate complete: YES. Ready for Phase 7: YES. Production ready: NO. Production remediation still required: YES. Migration required: NO.

New confirmed findings: Critical 0; High 2 (fixed); Medium 5 (fixed); Low 2 (fixed). Unresolved Critical/High/Medium: 0. Informational observations: browser automation unavailable; installed MySQL differs from the historical MySQL 8 target. Previously accepted product/deployment risks are reassessed in sections 17-18.

## 2. BASELINE

- Branch: `feature/authentication`.
- Baseline and final HEAD: `7556729c26ebc342b56d099efa548e1a97ee7c5e`.
- Commit: `feat: implement profiles and onboarding`.
- Initial tree: clean; no staged or untracked files. Git status, diff whitespace check, and `git fsck --full` passed.
- Both the local origin-tracking ref and a fresh `git ls-remote origin refs/heads/feature/authentication` returned the exact expected commit.
- Untouched backend baseline: 597 passed; frontend baseline: 68 passed. No tests disappeared.
- Untouched TypeScript, ESLint, build, compile/import, Ruff, pip check, pip-audit, and both npm audits passed.
- Alembic current/head: `f6a1b2c3d4e5`, one head.
- Database: local MySQL 9.4.0, connected through SQLAlchemy/PyMySQL. This audit does not establish identical behavior on MySQL 8.

## 3. SECURITY FINDINGS

### P7-001

- Severity: HIGH. Status: FIXED.
- Component: login and user repository locking.
- Description/attack: an old-password login paused during password verification could resume after a concurrent password change and create an unrevoked refresh family.
- Evidence: the new real-MySQL test reproduced one active family after the change. It now observes zero.
- Impact: a holder of the old password could regain persistent session authority after credential replacement.
- Root cause: the identifier/password read preceded acquisition of the user lock; an ORM identity-map entry could also retain stale state.
- Fix: acquire the user lock before password verification and refresh existing ORM state on locking user reads. Login and credential changes now serialize through the same user row.
- Regression: `test_login_racing_password_change_cannot_leave_old_credential_session`; full login, reset, change, and concurrency suites.
- Residual: stateless access tokens retain their documented short lifetime; lock contention may require retry.

### P7-002

- Severity: HIGH. Status: FIXED.
- Component: delayed forgot-password delivery activation.
- Description/attack: a pending reset challenge created before password change could become active when its delayed provider call returned afterward.
- Evidence: the new real-MySQL delivery-interleaving test reproduced a usable challenge after password change.
- Impact: possession of that stale recovery challenge could replace the newly changed password.
- Root cause: activation checked account state and newest challenge but did not bind delivery to the credentials observed at issuance.
- Fix: retain the credential digest only in request memory and require the locked current digest to match before activation. Nothing sensitive is added to storage, logs, or responses.
- Regression: `test_delayed_reset_delivery_cannot_activate_after_password_change`; all forgot/reset/change tests.
- Residual: a person who continues to control the recovery channel can request a new challenge; securing that external channel remains necessary.

### P7-003

- Severity: MEDIUM. Status: FIXED.
- Component: frontend session, API retry, and private-profile cache lifecycle.
- Description/attack: late refresh/bootstrap responses restored cleared state; an old failure cleared a new user; an old profile mutation receiving 401 could be retried with the next user's token. Metadata-free mutation cache entries also survived cleanup.
- Evidence: five new negative frontend tests failed against the baseline before fixes.
- Impact: shared-browser account confusion, unintended cross-session writes, and private data retention.
- Root cause: async operations lacked a session generation check, while cache clearing depended on query metadata alone.
- Fix: memory-only session versions guard request dispatch, responses, retries, bootstrap, login, and profile mutation callbacks. Logout invalidates local authority immediately and drains dispatched refresh traffic before cookie revocation. Login waits for pending session traffic. Private profile keys are cleared even without metadata. Bearer injection is restricted to relative API destinations.
- Regression: nine `session-boundary.test.ts` cases, two delayed profile mutation tests, existing single-flight/one-retry/auth/cache suites.
- Residual: coordination is per tab. Simultaneous refreshes from different tabs may trigger safe family revocation and require sign-in.

### P7-004

- Severity: MEDIUM. Status: FIXED.
- Component: logout during/after refresh rotation.
- Description/attack: logout with the previous cookie did nothing once that token was marked rotated, leaving its active successor on the server.
- Evidence: the new test reproduced one surviving active token after logout.
- Impact: logout could fail to terminate the intended refresh family in a rotation race.
- Root cause: revocation depended on the presented row still being active.
- Fix: after validating the original cookie/header/database CSRF binding, revoke all still-active rows in its family regardless of that row's rotation state.
- Regression: `test_logout_with_rotated_cookie_revokes_the_surviving_family`, refresh/logout isolation and replay tests.
- Residual: access-token expiry remains unchanged; unrelated families remain untouched.

### P7-005

- Severity: MEDIUM. Status: FIXED.
- Component: bounded process-local limiter.
- Description/attack: filling the key map evicted an unexpired budget; revisiting the evicted identifier restored its allowance.
- Evidence: the original memory-bound test explicitly accepted this behavior; the new churn attack reproduced it.
- Impact: high-cardinality traffic could bypass an existing budget.
- Root cause: live-key eviction was used to enforce the memory cap.
- Fix: expired entries are reclaimed, but a full map rejects new keys with a bounded positive Retry-After. Existing budgets remain intact.
- Regression: `test_limiter_key_churn_cannot_reset_an_unexpired_budget`, revised bounds test, full limiter and endpoint tests.
- Residual: saturation can deny new keys until expiry. Shared limits and edge abuse protection are needed in production.

### P7-006

- Severity: MEDIUM. Status: FIXED.
- Component: phone resend/verification HTTP abuse controls.
- Description/attack: durable per-phone/challenge limits did not limit a peer rotating numbers or repeatedly submitting malformed requests.
- Evidence: both routes lacked a peer-limit dependency; the new test fills one shared peer budget using malformed verification requests and checks resend plus spoofed forwarding headers.
- Impact: repeated database work/provider eligibility lookups without a per-peer request budget.
- Root cause: only challenge-level controls existed on these endpoints.
- Fix: a bounded, shared phone-verification peer budget (default 20/60 seconds) executes before schema-valid service work; forwarded values do not select its key.
- Regression: `test_phone_limit_counts_malformed_requests_and_ignores_forwarded_peer`, full phone/dev-provider suites; independent test-budget fixture.
- Residual: distributed attackers need shared/edge production controls; durable cooldown and attempt rules remain unchanged.

### P7-007

- Severity: MEDIUM. Status: FIXED.
- Component: Docker context and repository secret-file exclusions.
- Description/attack: frontend `COPY . .` had no `.dockerignore`; a local environment file, dependency directory, or key could enter an image/build context.
- Evidence: frontend `.env` exists locally and the baseline frontend context had no ignore file. No image was built or published to demonstrate leakage.
- Impact: accidental distribution of developer configuration or future local key material through build artifacts.
- Root cause: Git ignores are not Docker context exclusions.
- Fix: frontend context excludes environments, keys, credentials, logs, dependencies, build/test outputs and uploads. Backend key/environment exclusions and root Git ignore coverage are strengthened. Placeholder examples remain permitted.
- Regression: `test_both_build_contexts_exclude_environment_and_private_key_material` plus existing Docker policy tests, ignore checks, and source review.
- Residual: no Docker CLI is available, so actual image-layer inspection is NOT RUN. The provided images/Compose/nginx configuration remain development scaffolding.

### P7-008

- Severity: LOW. Status: FIXED.
- Component: sensitive HTTP cache policy.
- Description/attack: private GET/profile/phone/error responses did not consistently carry explicit cache prohibitions.
- Evidence: five response-header regressions failed on the baseline; the live HTTP audit verifies successful private-profile responses too.
- Impact: unnecessary private-response retention by browser or intermediary caches.
- Root cause: middleware covered a short list of POST token/password routes only.
- Fix: all methods under the auth/private-profile/dev namespaces receive `Cache-Control: no-store` and `Pragma: no-cache`, including generic unhandled private failures. Intentionally public profile responses are separate.
- Regression: private response matrix, controlled 500 test, and live lifecycle.
- Residual: browser/UI cache semantics still require real-browser regression on a functioning browser environment.

### P7-009

- Severity: LOW. Status: FIXED.
- Component: Origin validation.
- Description/attack: invalid Origin values ending in one or more slashes were normalized and accepted.
- Evidence: trailing-slash cases in the exact-match regression failed before the fix.
- Impact: a broader accepted syntax than the documented origin boundary; no attacker-origin suffix bypass was demonstrated.
- Root cause: request-side `rstrip('/')` normalization.
- Fix: compare the supplied Origin exactly to the configured origin set.
- Regression: six suffix variants, malicious CORS preflights, existing scheme/host/port/null/CSRF tests.
- Residual: missing Origin remains allowed for non-browser clients; cookie-authorized mutations independently require the bound CSRF proof.

## 4. AUTHENTICATION REVIEW

| Flow | Result and evidence |
|---|---|
| Registration | PASS: normalized email/phone, bounded password policy, Argon2id, buyer-only creation, strict extras, safe conflicts, rollback, and real duplicate race |
| Login | PASS: generic unknown/wrong/inactive 401, dummy Argon2, canonical identifiers, limits, new credential-change serialization |
| JWT | PASS: HS256 allow-list; signature, issuer, audience, type, UUID subject, required claims, timestamps, expiry/skew; hostile and missing claims tested |
| Refresh | PASS: random opaque 512-bit token, SHA256 lookup digest, CSRF digest binding, atomic rotation, reuse/family revocation, expiry/cap |
| Logout/logout-all | PASS: scoped revocation, idempotency, cookie clearing, rotated-cookie regression, other-user isolation |
| Forgot/reset | PASS: generic request response, purpose-separated HMAC, cooldown/hour/HTTP budgets, pending-delivery safety, expiry/newest/attempt/replay checks, atomic credential/session mutation |
| Password change | PASS: bearer identity, current-password proof, same-password rejection, row lock, reset/session invalidation, no replacement session |
| Phone | PASS: six ASCII digits, secure generation, HMAC, durable attempts, newest/expiry/consumption, ACTIVE policy, concurrent resend/verification, peer budget |
| Email | PASS: bearer owner only, ACTIVE, domain-separated HMAC, pending/activation/cancellation, durable limits, failure preservation, concurrent verification/resend |
| Authoritative status | PASS: dependencies load current ACTIVE state; sensitive services recheck under locks; JWT role claims do not grant authority |

JWT roles are not trusted. Duplicate JSON claim handling is delegated to the signed-token library; an attacker cannot make conflicting claims authoritative without a valid signing key. No perfect timing indistinguishability is claimed. HMAC purpose separation is exercised across phone, email, and reset challenges. Already verified phone verification is idempotent; its 200 response does not consume or apply another challenge.

## 5. AUTHORIZATION REVIEW

IDOR/BOLA, property/function authority, cross-user isolation and profile ownership: PASS. All own-profile operations derive identity from the bearer principal. Query parameters cannot select an owner; strict bodies reject internal/public IDs, contact/role/status fields, verification flags, timestamps and client-set completion. Public UUID knowledge grants only the intentionally minimal read. Backend API tests bypass frontend guards.

Account-state matrix (ACTIVE versus each of SUSPENDED/BANNED/DELETED):

| Flow | ACTIVE | Every non-ACTIVE state |
|---|---|---|
| Login, /auth/me | Allowed with valid credentials | Generic 401 |
| Refresh | Valid current family may rotate | Rejected; family revoked |
| Phone resend | Eligible unverified phone may receive code | Generic accepted response; no challenge issued |
| Phone verify | Current eligible challenge may verify | Invalid-code failure; no flag mutation |
| Email resend/verify | Bearer owner, eligible channel/challenge | 401 at auth boundary; service rejects stale state |
| Forgot password | Generic 202; eligible delivery only | Same generic response; no active challenge issued |
| Reset password | Valid challenge may replace credentials | Generic invalid reset; no mutation |
| Password change | Current-password proof required | 401 at auth boundary; service rejects stale state |
| Own profile GET/PATCH/completion | Allowed; completion requires committed fields | 401; no mutation |
| Public profile | Visible only after completion | Same 404 as absent/incomplete profile |

Registration has no authenticated target account; duplicates retain the accepted conflict contract. Logout can only remove authority and does not reactivate an account.

## 6. SESSION / BROWSER SECURITY

Cookie helpers use matching set/delete paths and no Domain. Refresh is HttpOnly, SameSite=Lax, `/api/v1/auth`; CSRF is readable, SameSite=Lax, `/`; both Secure in production. Runtime production configuration and cookie attributes were exercised. Tokens are not stored in localStorage, sessionStorage or IndexedDB; no frontend persistence/sensitive rendering sink was found.

State-changing endpoint boundary matrix (paths below `/api/v1`):

| Endpoint | Authority | Cookie authority | CSRF | Origin policy/reason |
|---|---|---|---|---|
| POST /auth/register | New credentials | None | Not required | Public bootstrap; no victim session authority |
| POST /auth/login | Password | Creates cookies | Not required to establish session | Exact when present; login-CSRF defense for browsers |
| POST /auth/refresh | Refresh cookie | Yes | Cookie/header/DB binding | Exact when present |
| POST /auth/logout | Refresh cookie, if present | Yes | Bound proof if cookie present | Exact when present; empty logout is idempotent |
| POST /auth/logout-all | Bearer | None | Not required | Exact when present; cookie cannot select target |
| POST /auth/password/forgot | Identifier | None | Not required | Exact when present; generic response |
| POST /auth/password/reset | Identifier + reset code | None | Not required | Exact when present; reset proof is authority |
| POST /auth/password/change | Bearer + current password | None | Not required | Exact when present |
| POST /auth/phone/resend-code | Public identifier; eligibility/limits | None | Not required | No Origin requirement; no ambient user authority |
| POST /auth/phone/verify | Phone + current OTP | None | Not required | No Origin requirement; OTP ownership proof |
| POST /auth/email/resend-code, /verify | Bearer owner | None | Not required | Exact when present |
| PATCH /profile/me | Bearer owner | None | Not required | CORS controls browser access; no cookie authority |
| POST /profile/onboarding/complete | Bearer owner | None | Not required | Same bearer-only boundary |
| GET /profile/me (lazy first creation) | Bearer owner | None | Not required | Creates only the caller's one constrained row |
| DELETE dev inbox message | Actual loopback; email also bearer owner | None | Not required | Development only; a mailbox handle cannot grant production authority |

Absent Origin remains accepted for non-browser clients. Foreign, malformed, suffix, scheme/port mismatch and null origins are rejected where required. CORS uses explicit origins, methods and headers; no wildcard credential policy. Profile guards are UX only. Redirect tests cover external/protocol-relative/unsafe destinations; no untrusted redirect sink was found.

Browser regression: ENVIRONMENT BLOCKED. The in-app browser setup failed before obtaining a tab because sandbox metadata lacked `sandboxPolicy`. No fresh reload, visual or browser-storage PASS is claimed. Prior user-verified Phase 4C 7/7 evidence is historical; current unit/component/source and real HTTP checks are fresh.

## 7. PROFILE / ONBOARDING SECURITY

PASS: unique user/public IDs, foreign key, lengths, supported-city checks, server-generated immutable API public ID, NFC/trim/control/bidi validation, inert React text, separate public response, required-field completion and invalidation, user-row serialization and rollback.

The DB enforces uniqueness/FK/length/city constraints. Valid onboarding completion and public-ID immutability are enforced by the service/API; there is no additional database CHECK tying the completion boolean to required fields, nor a trigger preventing privileged direct SQL from changing public IDs. No API bypass was demonstrated; adding a migration without a confirmed vulnerability is not justified. Unicode combining marks, legitimate RTL text and emoji remain usable; markup is treated as plain text rather than incorrectly advertised as sanitized HTML.

## 8. RATE LIMITING

Defaults below are configuration defaults, not disclosed local environment contents. HTTP budgets use locked sliding-window process memory, bounded at 10,000 keys by default. User/identifier/session keys use namespaced HMAC references; actual peer IP selects network keys. No request forwarding header is read as limiter identity.

| Endpoint | Dimension / default budget | Window | Storage/key | Retry-After |
|---|---|---|---|---|
| Register | Peer 20 | 60s | Memory, peer | Yes |
| Login | Peer 5; identifier 10 | 60s; 900s | Memory, peer/HMAC | Yes |
| Phone resend + verify | Shared peer 20 | 60s | Memory, peer | Yes |
| Phone resend | Phone cooldown 1/60s; 5/hour | 60s; 3600s | MySQL challenges | Cooldown yes; legacy hourly error has no header |
| Phone verify | 5 wrong attempts/challenge | Challenge lifetime | MySQL atomic counter | Exhaustion requires a new challenge, not a timed budget reset |
| Forgot | Peer 10; identifier 5 | 900s; 3600s | Memory, peer/HMAC | Yes |
| Forgot issuance | User cooldown 60s; 5/hour | 60s; 3600s | MySQL challenges | Generic 202 when suppressed |
| Reset | Peer 10; identifier 5 | 900s | Memory, peer/HMAC | Yes |
| Reset attempts | 5/challenge | Challenge lifetime | MySQL counter | Generic invalid reset |
| Password change | Peer 10; user 5 | 900s | Memory, peer/HMAC | Yes |
| Email resend | Peer 10; user 5 | 900s; 3600s | Memory, peer/HMAC | Yes |
| Email issuance | Cooldown 60s; 5/hour | 60s; 3600s | MySQL | Yes |
| Email verify | Peer 20; user 10 | 900s | Memory, peer/HMAC | Yes |
| Email attempts | 5/challenge | Challenge lifetime | MySQL counter | Invalid-challenge response |
| Refresh | Peer 20; presented token 10 | 60s | Memory, peer/HMAC | Yes |
| Logout | Peer 10 | 60s | Memory, peer | Yes |
| Logout-all | User 5 | 60s | Memory, internal user ID | Yes |
| Profile PATCH | Peer 60; user 30 | 60s | Memory, peer/HMAC | Yes |
| Onboarding complete | Peer 30; user 10 | 60s | Memory, peer/HMAC | Yes |
| Public profile | Peer 120 | 60s | Memory, peer | Yes |

Own-profile GET, /auth/me and health have no dedicated HTTP budget; production edge/concurrency limits must cover reads and invalid parsing/oversized bodies. Schema-invalid login/reset bodies do not reach password hashing, but parser-level resource use is not globally bounded by these dependencies. Shared Redis or equivalent is required before multiple workers/replicas. Saturation now rejects new keys instead of forgiving live budgets.

## 9. DATABASE / TRANSACTION / CONCURRENCY

Preservation checks covered every column through deterministic table fingerprints, without printing column data.

| Table | Before/final rows | Before/final fingerprint prefix |
|---|---:|---|
| users | 4 | `891bef3bf220acaf` |
| user_roles | 4 | `be38e6e535ea4f63` |
| phone_verification_codes | 3 | `c0c2eaa4a03ddbcb` |
| refresh_tokens | 7 | `e72016e35f65c478` |
| password_reset_codes | 0 | `4f53cda18c2baa0c` |
| email_verification_codes | 0 | `4f53cda18c2baa0c` |
| user_profiles | 0 | `4f53cda18c2baa0c` |

All orphan checks, duplicate profile owner/public ID counts, negative attempts, and invalid completed profiles: zero. Synthetic HTTP/test records: cleaned. No legitimate users, roles, challenges, profiles or refresh rows were changed.

Full suites exercised real MySQL registration/refresh/reset/change/phone/email/profile races. Three additional stress runs each passed 36 selected concurrency/rollback cases (389 unrelated integration tests deselected). Rollback tests include registration, refresh, reset, change, phone/email, profile creation/update and completion. The new login/reset-delivery/logout races failed before repair and pass afterward.

Existing cross-feature tests allow and verify safe InnoDB deadlock rollback plus explicit retry. This audit does not claim no deadlock can occur; only successful operation results establish the corresponding invariant. An initial read-only audit query referenced `attempt_count` instead of `attempts`; it was corrected, changed no data and is not an application defect.

## 10. ALEMBIC

Current/head: `f6a1b2c3d4e5`; one head; no drift. Chain: `a75289cfd4a9 -> c91e4a7b2d6f -> aca2dda0ef53 -> d5f0c1e2a3b4 -> f6a1b2c3d4e5`.

No migration added. After tests stopped, local app ports were inactive and `user_profiles` was confirmed empty. The existing Phase 6 downgrade to `d5f0c1e2a3b4`, upgrade back to head, current/heads/check and full fingerprint preservation passed. No database reset/create_all shortcut was used. Do not repeat the downgrade on a database containing legitimate profiles.

## 11. FRONTEND SECURITY

Auth state, storage, refresh single-flight, one-retry limit, routing, profile cache and XSS controls: PASS with the fixes above. Frontend suite: 79 passed (12 files), zero failed/skipped. TypeScript, ESLint, production build: PASS. A fresh Vite process returned HTTP 200, served the React entry, and injected the configured `VITE_API_BASE_URL` into the API module. The process was stopped. Built assets contain no fake-delivery or future seller/admin/product page implementations searched for in the audit. Visual rendering/reload remains browser-blocked.

## 12. DEPENDENCIES

`pip check`: PASS. `pip-audit`: no known vulnerabilities. `npm audit`: 0. `npm audit --omit=dev`: 0. No dependency/lockfile upgrade was necessary. Backend requirements remain version ranges and several frontend manifest entries use `latest`; production should build from reviewed locks/pinned resolved dependencies and use a reproducible install. No claim is made that an advisory scan rules out unknown vulnerabilities. One third-party Starlette TestClient deprecation warning remains.

## 13. CONFIGURATION / SECRETS / DOCKER

Real backend/frontend `.env` files are ignored, untracked and unchanged. Example configurations were checked without publishing secret values; no suspicious secret-variable value was found. Root and both Docker ignore policies were checked, including the separate three-line `.env.example` rate-limit diff.

A local history scan inspected 612 Git blobs, comparing current local secret values in memory (including encoded forms), checking private-key/AWS-key patterns and secret-bearing historical filenames. No matches were found. Contextual runtime/repository pattern and logging review found no hardcoded live credentials or request-body/token/challenge logging in implemented flows. This is a bounded structural/pattern scan; dedicated gitleaks/trufflehog tools were unavailable, and unknown historical secret formats cannot be ruled out absolutely.

Production rejects unsafe JWT/verification configuration and fake providers/inboxes, forces debug off and secure cookies. A fresh subprocess loaded production environment settings and verified its real global application route/configuration behavior. Real SMS/email remain intentionally disabled. OpenAPI/docs exposure is currently intentional but must be decided for deployment.

Uvicorn may trust configured proxy peers. Audit HTTP used `--no-proxy-headers`. Production must restrict direct backend access and explicitly configure trusted proxies that replace/sanitize forwarded headers. Loopback-only development helpers must not be published through a local reverse proxy. Host/proxy values do not construct reset links or select profile ownership in the current code.

## 14. OPENAPI

Local configured application: 23 operations = 13 auth + 4 profile + 4 health + 2 fake-SMS development operations. Production: 21 operations; 0 dev, 0 duplicate operation IDs, 0 Phase 7 operations. Bearer security declarations appear on protected routes; public/cookie endpoints deliberately do not claim bearer authority. Response schemas separate private and public profiles. Login/refresh intentionally expose access tokens, while no password/hash/raw challenge appears in production responses. Dev inbox schemas intentionally contain codes and are absent from production.

## 15. OWASP API TOP 10 2023

Targeted mapping uses the [official OWASP API Security Top 10 2023](https://owasp.org/API-Security/editions/2023/en/0x11-t10/). These are engineering conclusions from local evidence.

| Category | Relevant / evidence / result |
|---|---|
| API1 | Yes: bearer-owned profile and reset/email cross-user tests; PASS |
| API2 | Yes: JWT, credential/session races, OTP/reset tests; P7-001/002/004 fixed |
| API3 | Yes: strict mass assignment and minimal public schemas; PASS |
| API4 | Yes: limits, churn, malformed phone traffic; P7-005/006 fixed; production edge/shared quotas outstanding |
| API5 | Yes: authoritative ACTIVE and absence of exposed admin/seller functions; PASS |
| API6 | Yes: durable OTP/recovery/provider budgets and isolation; PASS for current scope; distributed abuse controls deferred |
| API7 | No user-controlled remote fetch in implemented routes; fixed server-configured delivery adapter reviewed; future URL/upload work needs a new review |
| API8 | Yes: cookies, CORS, Origin, cache, secrets/build contexts; P7-007/008/009 fixed; deployment controls outstanding |
| API9 | Yes: generated local/production OpenAPI and route/bundle inventories; PASS |
| API10 | Yes: Tencent adapter response/timeout/error handling and fake-provider failure tests; PASS for simulated integration; live provider verification NOT RUN |

## 16. OWASP ASVS TARGETED REVIEW

Reference: [OWASP ASVS 5.0](https://owasp.org/www-project-application-security-verification-standard/). Applicable groups reviewed: authentication, session management, access control, validation/output encoding, API services, cryptography, error handling/logging, data protection and configuration.

Passed: tested controls described above after remediation. Findings: P7-001 through P7-009. Limitations: no exhaustive requirement-by-requirement ASVS level assessment, no live provider exercise, no production TLS/proxy/header deployment, no fresh browser execution. Certification claim: NONE.

## 17. ACCEPTED RESIDUAL RISKS

| Risk | Classification / reason / future work |
|---|---|
| Registration identifier enumeration | LOW, accepted: deliberate actionable duplicate contract, no credential/session disclosure. Revisit generic asynchronous registration if product privacy assumptions change. |
| Legacy phone verification-state distinction | LOW, accepted: idempotent verified-phone success and challenge-status responses can distinguish eligibility; registration already exposes membership. Does not grant new verification authority. Reassess identifiers/status privacy together. |
| Stateless access after logout/reset/change | LOW, accepted: normally 15 minutes plus configured clock skew; sensitive operations still enforce current account state. Consider credential/session version revocation if immediate bearer invalidation becomes required. |
| Process-local limits | Production remediation: acceptable for local/single-worker development, inadequate as a shared multi-worker limit. Use shared storage before scaling. |
| Saturated limiter | Availability tradeoff: rejects new keys until expiry; does not reopen exhausted budgets. Add edge/distributed abuse protection and metrics. |
| Per-tab refresh coordination | LOW availability/UX residual: cross-tab concurrent refresh can revoke a family and require sign-in. No unbound successor/session authority accepted. |
| InnoDB deadlock victims | INFORMATIONAL: complete rollback and safe retry are required; instrument production outcomes. |
| Six-city allow-list | Product limitation; Phase 8 owns managed city/category data. |
| Real delivery disabled | Intentional: development providers isolated; live provider integration requires separate approval/configuration and tests. |
| MySQL version | INFORMATIONAL: audited 9.4.0; certify the exact supported production version separately. |
| Browser tooling | ENVIRONMENT BLOCKED: rerun browser storage/cookies/reload/multi-user checks when available; automated/source/live-HTTP evidence is not mislabeled as a browser test. |

## 18. PRODUCTION REMEDIATION

Before production: shared rate-limit storage and edge request/body/concurrency/time limits; TLS and secure origin configuration; CSP, frame-ancestors/X-Frame-Options, nosniff, Referrer-Policy, HTTPS-only HSTS and suitable Permissions-Policy; explicit proxy/Host trust and restricted backend access; managed secrets and rotation; least-privilege DB/runtime identities, backups and recovery verification; structured redacted security monitoring and alerting; real provider approval/budgets and delivery-failure tests; reproducible dependency/image builds; production ASGI/static-asset serving instead of the current Vite/Compose development stack; required non-placeholder database credentials in deployment config; actual Docker image-layer audit; exact supported database/runtime compatibility testing; a fresh full browser regression and review of public docs/OpenAPI policy. Private seller evidence must receive its own Phase 7 threat model before implementation.

## 19. PHASE BOUNDARY

Phase 7 functional code present: NO. Future marketplace functionality present: NO. Existing scaffold files include seller/product/chat/admin names and unregistered heading-only frontend placeholders; they have no functional API/table/service workflow and are not mounted/bundled into the active routes. No seller evidence, uploads, KYC, products, chat or moderation functionality was added.

## 20. FINAL TEST MATRIX

| Check | Result |
|---|---|
| Backend full | PASS: 695; baseline 597; +98 cases; 0 failed/skipped |
| Frontend full | PASS: 79; baseline 68; +11 cases; 0 failed/skipped |
| TypeScript / ESLint / build | PASS |
| Python compile / import / Ruff | PASS |
| pip check / pip-audit | PASS / no known vulnerabilities |
| npm audit / --omit=dev | 0 / 0 |
| Real Uvicorn + MySQL lifecycle | PASS: 41 checks; real fake-provider HTTP delivery; exact cleanup |
| Vite HTTP/environment | PASS; audit process stopped |
| Additional concurrency/rollback stress | PASS: 36 cases x 3 runs |
| Browser | ENVIRONMENT BLOCKED; no fresh browser PASS claimed |
| OpenAPI/production isolation | PASS: local 23 / production 21 / production dev 0 |
| Secret/history scan | PASS within documented pattern scope; 612 history blobs |
| DB preservation/orphans/invariants | PASS; fingerprints unchanged; no synthetic leftovers |
| Alembic | PASS: current/head, one head, no drift, empty-profile downgrade/upgrade |
| Docker image build | NOT RUN: Docker unavailable; context policy tests/source review PASS |

## 21. FILES CHANGED

All paths are relative to the project root. No file was deleted.

| File | Reason |
|---|---|
| `.gitignore` | Exclude environment variants and key/credential files |
| `backend/.dockerignore` | Exclude nested environments and key/credential material |
| `backend/.env.example` | Document only three new phone peer-limit defaults |
| `backend/app/api/v1/auth/dependencies.py` | Add bounded phone peer limit |
| `backend/app/api/v1/auth/routes.py` | Apply peer limit to both phone actions |
| `backend/app/core/config.py` | Validate phone-limit settings |
| `backend/app/core/rate_limit.py` | Preserve live budgets when key capacity is reached |
| `backend/app/core/session_security.py` | Exact request Origin comparison |
| `backend/app/main.py` | Uniform private no-store policy including generic failures |
| `backend/app/repositories/user_repository.py` | Refresh authoritative state on locking reads |
| `backend/app/services/auth_service.py` | Lock before login password verification |
| `backend/app/services/password_reset_service.py` | Bind delayed reset activation to credential state |
| `backend/app/services/refresh_session_service.py` | Terminate family using a rotated, CSRF-bound logout cookie |
| `backend/scripts/audit_security_http.py` (new) | Reproducible private Uvicorn/MySQL synthetic lifecycle with exact cleanup |
| `backend/tests/conftest.py` | Isolate new phone peer budgets between tests |
| `backend/tests/integration/test_pre_phase7_security.py` (new) | 93 adversarial HTTP/state/concurrency/rollback regressions |
| `backend/tests/integration/test_profile_routes.py` | Add four ownership/contact mass-assignment fields |
| `backend/tests/unit/test_docker_build_security.py` | Both contexts' key/environment exclusion regression |
| `backend/tests/unit/test_login_authentication.py` | Test doubles accept locking repository contract |
| `backend/tests/unit/test_rate_limit.py` | Assert capacity rejection preserves unexpired budget |
| `frontend/.dockerignore` (new) | Exclude local secret/generated/runtime data from COPY context |
| `frontend/src/app/queryClient.ts` | Clear private profile keys even without query metadata |
| `frontend/src/features/auth/api.ts` | Serialize login with outstanding session traffic and reject stale results |
| `frontend/src/features/auth/session.ts` | Guard bootstrap generation and coordinate logout |
| `frontend/src/features/profiles/hooks.ts` | Reject stale mutations/callback cache writes |
| `frontend/src/services/apiClient.ts` | Session generation checks, logout/refresh coordination and relative bearer scope |
| `frontend/src/stores/authStore.ts` | Memory-only session generation |
| `frontend/tests/unit/profile-cache-security.test.ts` | Delayed update/completion cache regressions |
| `frontend/tests/unit/session-boundary.test.ts` (new) | Nine stale-session/credential-request regressions |
| `documentation/CURRENT_PROJECT_STATUS.md` | Current gate evidence; distinguish historical totals/test isolation |
| `documentation/README.md` | Link this security gate |
| `documentation/api/authentication-api.md` | Document changed phone/cache/credential/Origin behavior |
| `documentation/architecture/frontend-architecture.md` | Document session-version and late-result boundaries |
| `documentation/security/PRE_PHASE_7_SECURITY_AUDIT.md` (new) | Findings, matrices, evidence, limitations and readiness |

## 22. GIT STATE

Final HEAD remains `7556729c26ebc342b56d099efa548e1a97ee7c5e`. Audit edits/new files remain unstaged for human review. No staged files. Commit created: NO. Push performed: NO. Diff whitespace checks and Git integrity checks pass; LF-to-CRLF notices are formatting advisories, not failed whitespace checks. No dependency lockfile or migration changed.

## 23. FINAL VERDICT

Authentication subsystem secure enough for Phase 7: YES. Profile/onboarding subsystem secure enough for Phase 7: YES. Critical unresolved: 0. High unresolved: 0. Medium unresolved: 0. Phase 7 may begin: YES.

Pre-Phase-7 security gate passed. Phase 7 Seller Verification may begin.

This is permission to proceed with separately scoped development, not a production deployment approval. The fresh browser gate remains environment-blocked and production prerequisites remain outstanding.
