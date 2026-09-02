# Phase 5D Email Verification Threat Model

Review date: 2026-08-31

Scope: authenticated email ownership challenge request, fake development delivery, verification, abuse controls, authorization, transactions, concurrency, errors, configuration, and data preservation.

This is a targeted engineering review informed by OWASP API Security Top 10 2023 and OWASP ASVS 5.0 concepts. It is not a penetration test, certification, or compliance claim.

| Threat | Attack path | Control and evidence | Residual risk |
|---|---|---|---|
| IDOR/BOLA | Submit another user's ID or code | Identity is only the validated Bearer subject; schemas accept no identity/email; cross-user test preserves both accounts | Database or signing-key compromise is outside this endpoint boundary |
| Property/mass assignment | Submit role, status, email, phone, verification flags, or admin fields | Empty resend schema and one-field verify schema use `extra="forbid"`; negative HTTP tests return sanitized 422 | Future schema expansion requires review |
| Brute force | Guess six-digit codes | Durable five-attempt cap, conditional increments, user/peer HTTP limits, 10-minute expiry | A token holder can exhaust a challenge and cause temporary denial |
| Unicode digit confusion | Submit full-width, Arabic-Indic, spaced, mixed, short, or long digits | Strict ASCII `[0-9]{6}` validation and sanitizer tests | None identified for schema-valid input |
| Predictable challenge | Generate with weak PRNG or timestamps | `secrets.randbelow(1_000_000)` with zero padding | Six digits require rate and attempt controls |
| Raw-code disclosure | Store/log/return the challenge | MySQL stores only HMAC; no sensitive logging; fake inbox is explicit development-only | Raw code necessarily exists briefly in memory and in the recipient email channel |
| Purpose confusion | Reuse phone/reset digest for email | Dedicated `email-verification:v1` HMAC prefix and dedicated table/repository/service | Shared root secret still requires secure rotation and storage |
| Timing comparison | Compare digests with normal equality | Candidate HMAC always computed and `hmac.compare_digest` used, including dummy-hash path | Whole-request timing can still vary with database/provider state |
| Replay | Reuse successful, expired, exhausted, or superseded code | Conditional one-time consumption, expiry/attempt predicates, newest-active selection, and replay tests | None identified within database consistency assumptions |
| Duplicate active challenges | Concurrent resend leaves two codes usable | User-row lock, inactive pending state, newest-row activation check, old-active invalidation in one transaction | Lock contention can reduce availability |
| Concurrent valid verification | Two workers accept same code | User/challenge row locks and conditional consumption; real MySQL test yields exactly one success | Database failover/isolation behavior needs infrastructure validation |
| Lost attempt increments | Simultaneous wrong guesses overwrite count | User lock plus atomic capped SQL increment; seven-worker test ends at exactly five | Intentional cap prevents distinguishing additional attempts |
| Verify/resend race | Old code verifies while new delivery is pending | Pending is inactive; activation rechecks user/newest/email state; race test cancels stale pending | A delivered but cancelled real email cannot be recalled, though its code is unusable |
| Delayed provider resurrection | Slow delivery activates an older pending row | Final newest-created check and conditional activation; stale delivery is cancelled | External provider may still deliver a stale, unusable message |
| Provider failure | Undelivered code becomes usable or old code is destroyed | Pending/activated split; failure cancels pending and preserves prior active code | Repeated provider failures consume durable generation history by design |
| Email flooding | Repeated authenticated resend | 60-second durable cooldown, five/hour durable cap, 10/15-minute peer limit, five/hour user limit | Distributed replicas need a shared HTTP limiter |
| Forwarded-header bypass | Spoof loopback or rotate IP headers | Only actual `request.client.host` is trusted; forwarded-header tests cover limiter and fake inbox | A trusted-proxy design must be separately reviewed before deployment |
| Fake provider in production | Expose raw-code inbox publicly | Startup rejects fake provider/inbox outside development; production OpenAPI excludes routes | Deployment must use validated environment variables |
| Cross-user fake inbox read | Query another email/user | Inbox accepts no identifier, requires Bearer user, stores HMAC user reference, and returns only that principal's message | Local developer with database/signing secret has broader trusted access |
| Weak secret | Use missing, short, or placeholder HMAC key | Production/fake-provider startup guard requires a non-placeholder secret of at least 32 characters | Entropy cannot be proven from length alone; managed generation is operational |
| Account-status bypass | Suspended token verifies or reactivates account | Authentication reloads ACTIVE state; service rechecks under user lock; only `email_verified` can change | Independent administrative races rely on database row locking |
| Stale authenticated principal | Email/status changes after dependency resolution | Service reloads/locks user and rechecks email/status before challenge mutation/activation | Future email-change flows need explicit challenge binding/versioning |
| Transaction partial failure | User verifies while code remains reusable or inverse | Service-owned transaction covers consume, flag update, and invalidation; failure injection rolls back all | Commit-outcome ambiguity during infrastructure failure needs operational reconciliation |
| Session regression | Verification revokes refresh sessions or changes password | Phase 5D never calls credential/session repositories; preservation test covers hash, roles, phone, status, and refresh row | Clients must refetch `/auth/me` to observe current state |
| Validation reflection | Pydantic returns code/input/context/docs URL | Global allow-list sanitizer plus authenticated Phase 5D reflection tests | Future exception handlers must preserve the policy |
| Sensitive error/logging | Expose HMAC, provider/SQL exception, token, or body | Fixed public errors, no body/security-value logging, no-store headers, captured-log tests | Infrastructure access logs require deployment-level redaction |
| SQL injection | Submit SQL syntax in code/extra fields | Strict schema and bound SQLAlchemy expressions; no raw request-derived SQL | ORM/driver vulnerabilities remain dependency risks |
| Resource exhaustion | Flood database/HMAC/provider work | Bounded input, peer/user rate limits, durable cooldown/hour cap, bounded fake store | HMAC/DB work still consumes finite resources; distributed limiting is pending |

## Security invariants

1. The authenticated database principal is the only possible verification target.
2. A code is exactly six ASCII digits and is stored only as an email-purpose HMAC.
3. A challenge cannot verify before confirmed delivery activation.
4. Only the newest active same-user challenge can verify.
5. Expired, used, superseded, pending, cancelled, and exhausted challenges never succeed.
6. Incorrect attempts cannot be lost or exceed the durable budget under concurrency.
7. `email_verified` and challenge consumption commit together or both roll back.
8. No credential, session, role, phone, status, or other user's state is mutated.
9. Fake delivery is authenticated, loopback-only, bounded, memory-only, and absent from production.
10. Public responses and logs contain no code, digest, secret, email body, token, cookie, or internal exception.

## Targeted OWASP disposition

- API1 Broken Object Level Authorization: target and challenge queries are derived from the authenticated subject; client identity selection is impossible.
- API2 Broken Authentication: existing JWT verification, ACTIVE reload, bounded challenge attempts, replay controls, and constant-time HMAC protect the flow.
- API3 Broken Object Property Level Authorization: allow-list schemas forbid every account property.
- API4 Unrestricted Resource Consumption: durable and HTTP limits, bounded storage, input bounds, and provider gating reduce abuse; distributed limiting remains residual.
- API5 Broken Function Level Authorization: backend Bearer authentication gates both account functions and the development inbox.
- API8 Security Misconfiguration: production guards reject fake/weak/unsupported configuration; no-store and safe errors are tested.
- API10 Unsafe Consumption of APIs: provider results are treated as untrusted confirmation; failure and delay cannot activate stale/undelivered challenges.
- ASVS 5.0 authentication, account verification, input validation, cryptography, session interaction, errors/logging, configuration, and data-protection concepts were reviewed. Certification is not claimed.

## Accepted residual risks

Process-local HTTP limits, absence of a real production email provider, short code-space denial potential, deployment secret/TLS/monitoring requirements, and infrastructure-specific database failover behavior remain documented risks. They do not weaken the Phase 5D invariants in the current single-process development architecture.
