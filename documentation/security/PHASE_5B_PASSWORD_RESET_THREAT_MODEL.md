# Phase 5B Password Reset Threat Model

Review date: 2026-08-21

Scope: approved attempts migration, reset completion, credential replacement, reset lifecycle, refresh-session revocation, rate limiting, transactions, concurrency, validation, public errors, and Phase 5C boundary.

This is an engineering threat model using relevant OWASP API Security Top 10 2023 and OWASP ASVS 5.0 concepts. It is not a penetration test, external assessment, certification, or full compliance claim.

| Threat | Attack path | Control | Test evidence | Residual risk |
|---|---|---|---|---|
| Reset-code brute force | Submit all six-digit values | Five durable wrong attempts, ten peer requests/15 minutes, five HMAC-identifier requests/15 minutes, ten-minute expiry | Exact 0→5 attempt sequence, exhaustion, rate-limit tests | Distributed attackers can cross process-local endpoint limits, but the database attempt budget remains global per challenge |
| Reset-code replay | Reuse a successfully consumed code | Exact challenge is conditionally marked used in the password transaction | Successful reset followed by same-payload replay | Database/application compromise can alter state outside normal controls |
| Stolen reset code | Use intercepted code before the owner | Short expiry, newest-only, attempts, rate limits, one-time consumption | Valid/expiry/replay/newest tests | Delivery-channel compromise remains external; no MFA is added |
| Database reset-hash theft | Read `code_hash` values | Domain-separated HMAC-SHA256; secret outside database; short expiry and attempts | Hash helper and Phase 5A hash-only tests | HMAC-secret compromise enables offline six-digit enumeration |
| Account enumeration | Compare account, status, or reset-state errors | Unknown/inactive/wrong/expired/superseded/used/exhausted share one 400; dummy DB/HMAC/Argon2id path | Generic failure tests across all states | Cache/lock/network timing cannot be perfectly identical |
| Expired challenge use | Submit a correct code after expiry | Server UTC comparison against locked newest row | Expired-code test | Clock correctness and production time synchronization remain operational requirements |
| Superseded challenge use | Use Code A after Code B exists | Only newest row is locked and verified; older code is never selected | A fails, B succeeds test | Submitting A consumes one attempt from current B because it is indistinguishable from any wrong value |
| Exhausted challenge use | Submit correct code after five wrong guesses | `attempts < maximum` required for verification and conditional consumption | Five wrong then correct failure | Attacker can cause temporary recovery denial of service |
| Attempt-counter race | Send parallel wrong guesses | User/challenge row locks plus conditional SQL increment with maximum predicate | Seven concurrent requests produce attempts exactly 5 | Lock contention can reduce availability under attack |
| Concurrent double reset | Send valid code simultaneously from two processes | MySQL row locks and conditional single consumption | Two real sessions produce one success, one generic failure | Database failover semantics require production infrastructure validation |
| Password-policy bypass | Submit weak, oversized, malformed, or truncated password | Exact registration validator and 128-character bound; strict Pydantic schema | Unit and route negative validation tests | Existing policy has no breached-password screening |
| Argon2 misconfiguration | Replace or bypass password hashing | Existing `PasswordHash.recommended()` helper reused; persisted format asserted | Successful reset asserts Argon2 prefix and verification | Production resource tuning and future library changes require review |
| Plaintext password persistence | Store submitted password directly | Only derived Argon2id hash assigned; response/log exclusions | DB hash, plaintext absence, old/new verification tests | Application-memory exposure during processing remains inherent |
| Session persistence after reset | Stolen refresh token remains active | Existing user-scoped `revoke_all_for_user` in same transaction | Multiple-family revocation and old-refresh HTTP 401 test | Already-issued access JWT remains valid until expiry |
| Unrelated session revocation | Reset User A disrupts User B | Every refresh update is filtered by server-resolved user ID | Other-user refresh remains unrevoked | Future admin recovery functions need separate authorization review |
| Refresh-token theft | Use token after password reset | All active user refresh rows revoked before commit | Old raw token rejected after reset | Access JWT residual lifetime remains |
| Transaction partial failure | Fail after some credential/session changes | Service-owned transaction covers password, consumption, invalidation, refresh revocation | Four injected failure-point rollback tests | External side effects are absent from Phase 5B; future ones need outbox design |
| SQL injection | Put SQL syntax in identifier/code/password | Strict schemas and SQLAlchemy bound expressions; no dynamic SQL | Source/Ruff review and malformed input tests | ORM/driver vulnerabilities remain dependency concerns |
| Mass assignment | Submit user ID, admin role, hash, attempts, or sessions | Extra-forbid request with exactly three accepted fields | Privileged/internal-field unit and route tests | Future schema changes must preserve the allow-list |
| Rate-limit bypass | Rotate peers or identifiers | Actual peer plus normalized identifier HMAC and durable challenge budget | IP/identifier/bounded/expiry tests | Multi-replica endpoint limit bypass remains until shared storage |
| X-Forwarded-For spoofing | Forge a different client IP | Direct connection peer is used; forwarding header ignored | Forged-header request remains blocked under original peer key | Trusted proxy support needs an explicit reviewed design |
| Sensitive logging | Capture password, code, hash, tokens, cookie, or identifier | New flow emits no logging/printing and returns generic bodies | `caplog` and response-content tests plus source scan | Future operational telemetry must retain redaction |
| CSRF | Cross-origin site submits reset for a victim | Reset authority is the code, not cookie; foreign Origin rejected; no refresh cookie trusted | No-cookie success and foreign-Origin no-mutation tests | Clients without Origin are supported; code theft remains the actual authority threat |
| Recovery denial of service | Exhaust a victim's five attempts or request new codes | Peer/identifier limits, Phase 5A cooldown/hour cap, fresh-code budget | Exhaustion and fresh-challenge tests | A low-rate targeted attacker can temporarily disrupt recovery |
| Access JWT residual lifetime | Continue using stateless JWT after reset | Short approximately 15-minute access-token lifetime; all refresh paths revoked | Session tests and documented Phase 4A lifetime | Immediate access-token revocation is not implemented |
| Fake provider production exposure | Obtain codes from development inbox | Existing Phase 5A development/provider/loopback/startup guards remain | Phase 5A 45-test regression passes | Compromised local development host can read local test codes |
| Migration/schema integrity | Add unsafe or unrelated schema fields | Approved attempts-only migration, named non-negative check, model parity, drift check | Inspector test, safe downgrade/upgrade, exact count preservation | Downgrade intentionally loses attempt history and requires controlled operations |

## Security invariants

1. Only the newest ACTIVE user's unconsumed, unexpired, non-exhausted challenge may authorize reset.
2. Every incorrect comparison against an available challenge consumes one durable attempt, never more than five.
3. Successful password update, challenge consumption, other-challenge invalidation, and refresh revocation either all commit or all roll back.
4. A challenge succeeds at most once under concurrent execution.
5. Reset never creates an authenticated session or trusts an existing refresh cookie.
6. Account state and invalid-reset reasons remain absent from public errors.
7. All SQL targets use server-resolved user/challenge IDs and parameterized expressions.

## OWASP disposition

- API2 Broken Authentication: addressed for the Phase 5B recovery scope with possession-factor validation, attempts, one-time use, password hashing, and session revocation.
- API4 Unrestricted Resource Consumption: addressed with bounded rate-limit stores and durable attempts; distributed endpoint limits remain residual.
- API6 Unrestricted Access to Sensitive Business Flows: recovery abuse is constrained but targeted denial of service remains possible.
- API8 Security Misconfiguration: migration scope, secrets, development provider guards, cache policy, and route inventory are tested.
- API10 Unsafe Consumption of APIs: no new provider/API integration exists.
- ASVS 5.0 recovery, password, session, cryptography, validation, error, logging, and concurrency concepts were reviewed. Certification is not claimed.

