# Phase 5A: Secure Forgot-Password Request

Completion date: 2026-08-21

Branch: `feature/authentication`

Baseline: `7764adcf09bdd97a152d4a6f8c07b2c0aae5cece`

Alembic revision: `c91e4a7b2d6f`

## Scope and outcome

Phase 5A implements only reset-challenge generation through `POST /api/v1/auth/password/forgot`. It does not verify a reset code, change a password, revoke sessions, verify email, or add frontend recovery behavior. Phase 5B is not started.

The endpoint returns HTTP 202 and the same response for existing, unknown, and inactive accounts:

```json
{
  "message": "If an account matches that information, password reset instructions have been sent."
}
```

Responses include `Cache-Control: no-store` and `Pragma: no-cache`. Provider status, account IDs, destinations, code values, and account eligibility are never returned.

## Request and normalization

`ForgotPasswordRequest` accepts exactly one bounded `identifier` field and forbids extra fields. It reuses the same `normalize_account_identifier()` path as login, which in turn reuses the established email and Mainland China phone normalizers.

- Email is trimmed, validated, and normalized to the current lowercase policy.
- Supported local, `0086`, and `+86` Mainland phone forms normalize to E.164.
- Empty, invalid, oversized, mass-assignment, and privileged fields are rejected before service work.

SQLAlchemy expressions bind normalized values as parameters. No request-derived dynamic SQL was introduced.

## Enumeration protection and eligibility

Only `ACTIVE` accounts are internally eligible. Suspended, banned, deleted, unknown, and otherwise non-matching accounts receive the same public 202 response and do not receive a challenge. The flow never reactivates an account.

Every accepted request generates and HMACs a dummy-or-real candidate and performs latest/count database queries. Unknown or ineligible requests use a fixed non-existent UUID for this comparable workload. This reduces easy architectural timing differences without claiming perfect timing indistinguishability; database cache state, contention, provider behavior, and network latency remain possible side channels.

Rate-limit behavior is based on the actual connection peer and an HMAC of the normalized identifier, not account existence. Invalid request syntax remains a normal HTTP 422 input-validation response.

## Reset challenge and persistence

- Format: six ASCII decimal digits.
- Entropy: `secrets.randbelow()` through the existing secure generator.
- Stored value: HMAC-SHA256 only; the raw code is never stored in MySQL.
- Domain separation: `unishop-china:password-reset:v1` is included before the code, so phone-verification and reset hashes cannot be substituted across purposes.
- Verification helper: future comparison uses `hmac.compare_digest`.
- Lifetime: configurable, ten minutes by default, constrained to 5-30 minutes.

The existing `password_reset_codes` model/table is reused without schema changes. Its `user_id`, `code_hash`, `expires_at`, `used_at`, and `created_at` fields are sufficient for Phase 5A. The current schema has no attempt counter; Phase 5A does not invent one because it does not verify codes.

## Newest-only and transaction behavior

`PasswordResetRequestService` owns business transactions. Repositories flush and execute targeted parameterized statements but never commit.

For an eligible issuance, one transaction locks the user, checks cooldown/hour usage, marks prior unexpired active rows used, and inserts the new row in an inactive pending state. Delivery occurs only after that transaction succeeds. A confirmed delivery starts a second transaction, locks the user again, confirms the account is still active and the row is still the latest, and then activates that exact row by clearing `used_at`.

This two-step policy ensures:

- insert or invalidation failure rolls back together;
- provider failure cannot leave an undelivered usable code;
- delayed delivery cannot reactivate an older challenge after a newer row exists;
- at most the newest successfully delivered challenge is active;
- no broad delete is used and history remains available.

A provider failure still returns the generic public response. The pending row remains inactive. A new issuance invalidates any previous usable code before provider delivery, so a targeted provider outage can temporarily disrupt recovery; this availability tradeoff is documented and Phase 5B must continue treating `used_at`, expiry, and newest-row checks as mandatory.

## Abuse controls

- Peer limit: 10 accepted requests per 15 minutes.
- Identifier limit: 5 accepted requests per rolling hour using a secret HMAC key.
- Account cooldown: 60 seconds between stored challenges.
- Database rolling limit: at most 5 stored challenges per eligible user per hour.
- Storage: bounded process-local limiter maps with expiration.
- Excess behavior: HTTP 429 with `Retry-After` and no-store headers.
- Peer trust: the socket peer is used; `X-Forwarded-For` is ignored.

These process-local controls do not aggregate across replicas. A reviewed distributed limiter is required before horizontal production scaling.

## Provider architecture

The service depends on a provider-neutral interface supporting either an email or phone destination. Phase 5A implements only:

- a disabled provider, which is the default and sends nothing; and
- an explicit development fake provider backed by bounded, expiring process memory.

No Tencent recovery call, SMTP integration, Gmail credential, or other real message delivery was added. The fake store retains no raw identifier; lookup uses an HMAC reference. Its raw code exists only in process memory until expiry, replacement, consumption, or clearing. Its optional inbox is identifier-scoped, loopback-only based on the actual peer, no-store, and present only when development, fake-provider, and inbox flags all agree.

Startup fails closed outside development if the fake provider or inbox is enabled. It also rejects a missing, weak, or placeholder reset-code HMAC secret where recovery is active or the environment is non-development. The fake route is absent from production OpenAPI.

## Logging and public errors

New runtime code emits no logs, prints, or provider exceptions. In particular it does not log identifiers, reset codes, reset hashes, passwords, tokens, cookies, provider credentials, or database credentials. The route catches service/provider failures and returns only the generic response. Normal API responses never expose the raw challenge; only the separately guarded local development inbox can retrieve it.

## Test and verification evidence

Phase 5A adds unit and MySQL-backed integration coverage for strict schemas, shared normalization, HMAC domain separation, constant-time verification, secure production guards, fake-provider isolation, existing/unknown/inactive accounts, email and China-phone flows, hash-only persistence, expiry, cooldown, hourly limits, old-code invalidation, delayed-delivery races, IP/identifier limits, spoofed forwarding headers, unsafe Origin, oversized/mass-assignment input, dummy workloads, provider failures, activation failures, invalidation/insert rollback, route inventory, and database restoration.

Final automated gates:

- Backend: 328 passed, zero failed; one third-party Starlette TestClient deprecation warning.
- Frontend: 49 passed, zero failed; typecheck, lint, and production build passed.
- Python and npm dependency audits: no known vulnerabilities.
- MySQL counts before/after: users 4, roles 4, phone codes 3, refresh rows 6, reset rows 0.
- Orphan roles, phone codes, refresh rows, and reset rows: zero.
- Alembic current/head: `c91e4a7b2d6f`; drift none; migration none.

## OWASP review

This is an engineering review, not certification.

- OWASP API2 Broken Authentication: generic recovery behavior, active-account policy, secure randomness, hash-only single-use preparation, and newest-only activation.
- API4 Unrestricted Resource Consumption: bounded peer/identifier limits, cooldown, database hourly cap, and finite in-memory stores.
- API6 Unrestricted Access to Sensitive Business Flows: spam/harassment controls and no account-existence response.
- API8 Security Misconfiguration: production fake-provider/inbox/secret guards and production route removal.
- API10 Unsafe Consumption of APIs: provider-neutral interface, confirmed-delivery check, exception containment, and no real unapproved integration.
- ASVS 5.0 focus: recovery, validation, cryptography, abuse protection, safe errors, logging, and session boundaries were reviewed. Formal ASVS verification or certification is not claimed.

## Residual risks

1. Six-digit codes require Phase 5B attempt limits, expiry, newest-only selection, and atomic single-use enforcement before any password change.
2. Rate limits and the fake inbox are process-local; multiple replicas need shared infrastructure.
3. Timing is made structurally comparable but cannot be guaranteed identical across database/provider/network states.
4. Provider failure after prior-code invalidation can cause temporary user-targeted recovery denial of service.
5. Real email and phone recovery providers, production observability with redaction, secret rotation, TLS, and distributed abuse controls remain unimplemented.

## Phase 5B handoff

Phase 5B is **NOT STARTED**. It must verify only the newest active, unexpired row; compare HMACs in constant time; enforce bounded attempts without revealing account state; consume the challenge atomically; change the Argon2id password in the same business transaction; and apply the separately approved refresh-session revocation policy. Phase 5A does not change any password or session.
