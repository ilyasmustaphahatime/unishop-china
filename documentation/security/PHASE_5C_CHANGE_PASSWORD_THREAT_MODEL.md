# Phase 5C Authenticated Password Change Threat Model

Review date: 2026-08-22

Scope: authenticated principal, current-password proof, new-password policy, reset/session invalidation, rate limiting, CSRF decision, transactions, concurrency, validation, errors, logging, and database preservation.

This is an engineering threat model informed by relevant OWASP API Security Top 10 2023 and OWASP ASVS 5.0 concepts. It is not a penetration test, external assessment, certification, or compliance claim.

| Threat | Attack path | Control | Test evidence | Residual risk |
|---|---|---|---|---|
| Stolen access token | Attacker submits change with a valid victim JWT | Current password is independently required; ACTIVE user reloaded and locked | Valid token plus wrong current password cannot mutate state | Attacker who also knows the current password can change it |
| Stolen refresh token | Attacker tries to use a refresh cookie as change authority | Endpoint reads only Bearer access authentication; refresh cookie is not authority | Bearer-only success and unauthenticated-cookie boundary tests | A stolen refresh token can obtain access through the separately protected refresh flow until revoked |
| Current-password guessing | Repeated guesses with a stolen access token | User limit 5/15 minutes, peer limit 10/15 minutes, Argon2 verification, generic error | Wrong-current and both limiter tests | Distributed peers/process replicas can cross process-local endpoint limits |
| CSRF | Cross-origin site submits an ambient-cookie request | Bearer header is non-ambient; refresh cookie ignored; exact Origin defense in depth | No-CSRF-cookie Bearer success; foreign Origin blocked before mutation | Non-browser requests without Origin remain supported; token theft is the relevant authority threat |
| IDOR | User A submits User B's ID | Identity comes only from validated JWT subject; schema forbids identity fields | User/victim mass-assignment tests preserve both hashes | Future alternate endpoints must preserve this server-side identity boundary |
| Mass assignment | Submit role, admin state, hash, session, token, status, or verification fields | `extra="forbid"` request allow-list with two password fields | Eleven privileged/internal field cases return sanitized 422 | Future schema expansion requires review |
| Password-policy bypass | Submit weak, oversized, non-string, or silently truncated new password | Shared registration/reset validator, strict string, 8-128 bound | Policy unit tests and HTTP validation tests | No breached-password screening or history is in scope |
| Same-password reuse | Set new password equal to current password | Verify new plaintext against current Argon2 hash and reject generically | Same-password test preserves hash, reset, and sessions | Password history beyond the current value is not implemented |
| Weak hashing | Replace Argon2id with weak or custom hashing | Existing `PasswordHash.recommended()` helper reused | Persisted `$argon2id$` prefix and old/new verification assertions | Library parameter changes require future review and capacity tuning |
| Plaintext persistence | Save submitted password or expose it in ORM state | Only derived hash assigned; request schema is transient | DB hash differs from both plaintext values | Plaintext necessarily exists briefly in application memory |
| Sensitive validation reflection | Pydantic returns raw `input`, context, or nested secret | Global allow-list validation handler returns fixed fields/messages only | Recursive oversized, weak, nested, and extra-field response scans | Future custom handlers must retain sanitization |
| Sensitive logging | Log body, passwords, Bearer token, cookies, CSRF, hash, or internal error | Flow adds no body/security-value logging and uses generic public errors | `caplog` and response scans with synthetic credentials/token/error | Future telemetry must implement explicit redaction |
| Session persistence after change | Old browser/device refresh token remains valid | All user refresh rows revoked in the credential transaction; cookies cleared | Three owner sessions revoked and old raw token returns 401 | Existing access JWT remains usable until expiry |
| Cross-user session revocation | User A change revokes User B sessions | Repository update is filtered by server-resolved User A ID | User B refresh row remains active | Database compromise can bypass application filters |
| Outstanding reset challenge | Old recovery code overwrites newly selected password | Valid outstanding challenges for same user invalidated atomically | Old challenge marked used and post-change reset fails | A challenge created after the change remains valid by design |
| Cross-user recovery invalidation | User A change consumes User B challenge | Reset update filters by authenticated User A ID | User B challenge remains unused | Future account-linking features need separate rules |
| Recovery denial of service | Authenticated attacker invalidates victim's recovery challenges | Current-password proof required; operation is rate limited | Wrong current and 429 paths preserve challenges | Attacker with token and password already controls the credential boundary |
| Concurrent password changes | Two requests use the same current password with different new values | MySQL `SELECT ... FOR UPDATE` on user before verification | Real two-session test: one success, one rejection | Database failover/isolation behavior requires infrastructure validation |
| Stale credential race | Loser verifies old hash before winner commits and overwrites winner | Lock is acquired before reading/verifying current hash | Final hash matches only recorded winner | Long lock waits can reduce availability under contention |
| Transaction partial failure | Password changes while sessions/recovery remain valid, or inverse | One service transaction covers all three mutation classes | Injected update, reset invalidation, and refresh revocation failures fully roll back | Commit outcome ambiguity during infrastructure failure needs operational reconciliation |
| SQL injection | Put SQL syntax in password or client fields | Strict Pydantic validation and SQLAlchemy bound expressions; no request-derived raw SQL | Malformed/credential tests plus source review and Ruff | ORM/driver vulnerabilities remain dependency concerns |
| Rate-limit bypass | Rotate headers, user identity, or peers | Actual connection peer plus HMAC user key; forwarded headers ignored | Spoofed `X-Forwarded-For` remains under original peer key | Multi-replica and distributed-peer attacks require shared infrastructure |
| Forwarded-header spoofing | Supply an arbitrary `X-Forwarded-For` | Limiter consumes `request.client.host` only | Stable key is the TestClient connection peer despite spoofed header | Trusted proxy support requires an explicit reviewed design |
| Account-status bypass | Use a token issued before suspension/deletion | Authentication reloads ACTIVE status; service re-checks under lock | Account changed to SUSPENDED receives 401 and is not reactivated | Race with an independent administrative status update is serialized by database locking behavior |
| Access JWT residual lifetime | Continue using an already-issued JWT after change | Short approximately 15-minute lifetime; no new token issued; refresh revoked | Original access token behavior explicitly tested and documented | Immediate access revocation is unavailable without an approved blacklist/version design |
| Cache disclosure | Intermediary/browser caches auth response | Route and middleware set no-store/no-cache on success and errors | Success, 400, 422, 429, and 500 header assertions | Misbehaving intermediaries remain operational risk |
| Database integrity | Tests or service leave orphans/partial rows | Foreign keys, atomic updates, exact synthetic cleanup, snapshot fixture | Counts and IDs restored; orphan/integrity audit | Manual database changes remain outside application controls |

## Security invariants

1. Only the validated Bearer subject can be the password-change target.
2. Possession of an access token without the current password is insufficient.
3. The current user row is locked before the authoritative password hash is read and verified.
4. The new password must satisfy the shared policy and must not verify against the current hash.
5. Password update, same-user reset invalidation, and same-user refresh revocation either all commit or all roll back.
6. No refresh or reset state belonging to another user is changed.
7. Rate-limit denial occurs before service mutation and uses no raw credential as a key.
8. Public responses and logs contain no submitted passwords, hash, token, cookie, CSRF value, or internal database detail.
9. Phase 5C creates no session and no schema revision.

## OWASP disposition

- API1 Broken Object Level Authorization: the target identity is derived exclusively from the authenticated subject; body-selected identity is forbidden.
- API2 Broken Authentication: current-password re-authentication, Argon2id, session revocation, ACTIVE-state checks, and short JWT lifetime protect the credential boundary.
- API3 Broken Object Property Level Authorization: the strict two-field schema rejects privileged/internal properties.
- API4 Unrestricted Resource Consumption: bounded per-user and per-peer limits constrain Argon2 work; distributed limiting remains residual.
- API5 Broken Function Level Authorization: the backend Bearer dependency, not frontend navigation state, gates the function.
- API6 Unrestricted Access to Sensitive Business Flows: credential guessing and repeated changes are rate limited and generically handled.
- API8 Security Misconfiguration: no-store, strict Origin checks, secret-backed HMAC limiter keys, and no-migration drift checks are tested.
- ASVS 5.0 password, re-authentication, session invalidation, cryptography, input validation, errors/logging, CSRF, and concurrency concepts were reviewed. Certification is not claimed.

## Phase boundary

The review covers only Phase 5C. Phase 5D, MFA, passkeys, OAuth, password history, email verification, and marketplace authorization remain absent.
