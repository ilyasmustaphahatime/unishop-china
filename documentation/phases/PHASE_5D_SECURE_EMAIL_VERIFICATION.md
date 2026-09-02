# Phase 5D: Secure Email Verification

Completion date: 2026-08-31

Branch: `feature/authentication`

Baseline: `e441418`

Previous Alembic head: `aca2dda0ef53`

Phase 5D Alembic head: `d5f0c1e2a3b4`

## Scope and endpoints

Phase 5D adds authenticated ownership verification only for an email already stored on an account:

- `POST /api/v1/auth/email/resend-code`
- `POST /api/v1/auth/email/verify`

It does not add or change email addresses, change login eligibility, revoke sessions, alter passwords, start Phase 5E, or implement MFA, OAuth, passkeys, profiles, seller verification, or marketplace features.

Both endpoints require the existing Bearer authentication dependency and exact allowed-Origin validation for browser requests. The identity comes only from the validated JWT subject and an ACTIVE user reloaded from MySQL. The resend request accepts only `{}`. The verify request accepts only `{"code":"123456"}`. Extra identity, email, role, status, or verification fields receive a sanitized 422.

Resend returns the same 202 body for an eligible account, an account without email, or an already verified account:

```json
{
  "message": "If this account is eligible, an email verification code will be sent.",
  "expires_in_seconds": 600
}
```

Invalid, expired, superseded, used, exhausted, and cross-user verification attempts share one no-store HTTP 400 contract. Successful verification returns only the success message and `email_verified: true`. All success and error paths use `Cache-Control: no-store` and `Pragma: no-cache`.

## Challenge and cryptography

Codes are generated with `secrets.randbelow`, formatted as exactly six ASCII digits, and validated with the strict `^[0-9]{6}$` schema already used by authentication challenges. Full-width, Arabic-Indic, mixed, spaced, short, long, non-string, and alphabetic values are rejected.

MySQL stores only HMAC-SHA256. The Phase 5D purpose input is:

```text
unishop-china:email-verification:v1\0<ASCII code>
```

This separates email verification from phone verification, password reset, refresh tokens, CSRF, and rate-limit identifiers while reusing the environment-managed `VERIFICATION_CODE_HASH_SECRET`. Verification uses `hmac.compare_digest`. Raw codes exist only transiently in application memory or the optional protected development inbox and are never logged.

## Migration decision and schema

One additive migration was required. The phone table binds challenges to a phone number and phone purpose, while password-reset challenges have public recovery and credential-replacement semantics. Reusing either would create purpose confusion and unsafe coupling.

Revision `d5f0c1e2a3b4`, with the single down-revision `aca2dda0ef53`, creates `email_verification_codes`:

- UUID `id` primary key;
- `user_id` foreign key to `users.id` with `ON DELETE CASCADE`;
- 64-character `code_hash`;
- `expires_at`;
- durable non-negative `attempts`, default zero;
- nullable `activated_at` for confirmed-delivery activation;
- nullable `used_at` for consumption, cancellation, and supersession;
- `created_at`;
- indexes on `user_id` and `expires_at`.

The new table is empty on upgrade, so existing rows require no backfill. Downgrade drops only this isolated table. A real MySQL downgrade/upgrade cycle passed, existing table fingerprints remained stable, one Alembic head remained, and `alembic check` reported no drift.

## Provider-safe resend transaction

`EmailVerificationService` owns transactions; repositories never commit. Resend uses three stages:

1. Lock the authenticated user, re-check ACTIVE/email/unverified eligibility, enforce durable cooldown/hourly limits, and insert an inactive pending challenge.
2. Deliver outside the database transaction through `EmailVerificationDeliveryProvider`.
3. Lock the user and newest challenge again. Only the still-newest pending row for the same unchanged email may activate. Activation occurs before older active challenges are consumed, inside the same transaction.

Provider failure cancels the pending row but leaves the previous delivered challenge active. An unconfirmed challenge never has `activated_at` and can never verify. If another request supersedes a delayed delivery, the delayed row is cancelled and cannot reactivate. If the old code verifies while delivery is delayed, the user becomes verified and the pending row is cancelled. These rules avoid unsafe provider/database races and partial state.

## Verification transaction and concurrency

Verification locks the user row and newest active challenge. It re-checks ACTIVE state, email presence, current `email_verified`, activation, expiry, consumption, and the attempt budget. Incorrect available submissions use a conditional atomic increment capped at five. Correct submissions conditionally consume the challenge, set only `users.email_verified = true`, and invalidate other active same-user email challenges in one transaction.

MySQL concurrency tests prove:

- two correct submissions produce exactly one successful transition;
- seven simultaneous incorrect submissions produce exactly five durable attempts without lost increments;
- simultaneous resend requests leave at most one usable challenge;
- verification during delayed resend cannot resurrect or activate the stale pending challenge.

Used, expired, superseded, exhausted, inactive, and pending challenges cannot replay. User A cannot submit User B's challenge because challenge lookup is always filtered by the authenticated subject.

## Abuse controls

Durable controls:

- challenge lifetime: 10 minutes;
- maximum incorrect attempts: 5;
- resend cooldown: 60 seconds;
- rolling generation cap: 5 per user per hour.

Process-local HTTP controls:

- resend peer: 10 per 15 minutes;
- resend authenticated user: 5 per hour;
- verify peer: 20 per 15 minutes;
- verify authenticated user: 10 per 15 minutes.

User limiter keys are HMAC-derived and retain neither raw email nor raw user ID. Peer limits use only `request.client.host`; `X-Forwarded-For`, `X-Real-IP`, and `Forwarded` do not change the key. Every HTTP 429 includes `Retry-After`. The rolling database limit computes its retry interval from the oldest challenge still inside the hour.

## Provider architecture and development inbox

The service depends on `EmailVerificationDeliveryProvider`, not a vendor. Phase 5D intentionally adds no SMTP or external network integration. The production default is disabled.

The optional fake provider is:

- enabled only when `APP_ENV=development` and provider is `fake`;
- memory-only, bounded, expiring, and process-local;
- keyed by an HMAC reference to the authenticated user and never retains email;
- exposed at `GET /api/v1/dev/fake-email/latest` only when explicitly enabled;
- protected by Bearer authentication and actual loopback peer validation;
- unable to read or delete another user's message;
- absent from production routing and OpenAPI.

Production startup rejects fake provider/inbox settings, non-local inbox policy, unsupported providers, and weak/missing/placeholder verification secrets. Real email is not sent.

## Validation, errors, logging, and sessions

Pydantic schemas forbid extras and bound the only submitted value. The existing global sanitizer returns only safe error type, field location, and fixed message; it does not return Pydantic `input`, `ctx`, URLs, exception representations, or submitted values.

No Phase 5D path logs a code, HMAC, secret, email body, request body, password, token, cookie, CSRF value, Authorization header, provider credential, or database password. SQLAlchemy expressions remain parameterized.

Email verification is not a credential change. Password hashes, roles, phone state, account status, refresh sessions, reset challenges, and access JWT claims are unchanged. Existing sessions remain active. `/auth/me` reloads MySQL and immediately reflects `email_verified: true`.

## Verification evidence

- Pre-implementation backend: 465 passed.
- Pre-implementation frontend: 49 passed.
- Phase 5D focused suite: 57 passed.
- Full backend after Phase 5D: 522 passed.
- Full frontend after Phase 5D: 49 passed.
- Ruff, compile, FastAPI import, OpenAPI, TypeScript, ESLint, and production build: pass.
- `pip check`: no broken requirements.
- `pip-audit`, `npm audit`, and `npm audit --omit=dev`: no known vulnerabilities.
- Alembic current/head: `d5f0c1e2a3b4`; drift none.
- Existing database row counts and ID fingerprints preserved; synthetic challenge/user leftovers: zero.

## Residual risks

1. HTTP limiters and the development provider are process-local; horizontally scaled production needs a reviewed shared limiter.
2. An attacker with a valid user token can exhaust five attempts and temporarily deny that challenge; a new code is subject to cooldown and hourly controls.
3. Real email deliverability, bounce handling, reputation, and vendor authentication are not exercised because no production provider is approved.
4. Production TLS, managed secret rotation, monitoring with redaction, and proxy trust configuration remain deployment responsibilities.
5. Existing access JWTs contain no verification claim by design; `/auth/me` is the current database-backed source.

## Phase boundary

Phase 5D is complete. Phase 5E is not started. No email-changing, MFA, OAuth, passkey, profile, seller, product, chat, admin, payment, or other future functionality was added.
