# Phase 2 — User Registration API

## Objective

Phase 2 implements secure account creation through `POST /api/v1/auth/register`. The endpoint accepts an email address, a mainland Chinese mobile number, or both; creates the user and mandatory `BUYER` role atomically; and creates a hashed phone-verification-code record when a phone number is supplied.

This phase does not implement login, tokens, SMS delivery, code verification, password recovery, seller onboarding, or frontend registration.

## Endpoint

```text
POST http://localhost:8000/api/v1/auth/register
Content-Type: application/json
```

A valid request returns HTTP `201 Created`. Registration does not issue access or refresh tokens and does not log the user in.

## Response format

Successful responses contain only public account state:

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "email": "user@example.com",
  "phone_number": "+8613800000000",
  "phone_verified": false,
  "email_verified": false,
  "account_status": "ACTIVE",
  "roles": ["BUYER"],
  "phone_verification_required": true,
  "created_at": "2026-07-17T12:00:00Z"
}
```

For email-only registration, `phone_number` is `null` and `phone_verification_required` is `false`. Passwords, hashes, phone codes, tokens, and internal SQLAlchemy state are never returned.

## Request examples

Email only:

```json
{
  "email": "user@example.com",
  "password": "StrongPassword123"
}
```

Phone only:

```json
{
  "phone_number": "+8613800000000",
  "password": "StrongPassword123"
}
```

Email and phone:

```json
{
  "email": "user@example.com",
  "phone_number": "13800000000",
  "password": "StrongPassword123"
}
```

## Validation rules

- At least one of `email` or `phone_number` is required.
- Email whitespace is removed, format is validated, and the value is stored lowercase.
- Valid mainland Chinese mobile numbers are accepted in common local, `+86`, and `0086` formats and stored in E.164 format.
- Password length is 8–128 characters and must include an uppercase letter, lowercase letter, and digit.
- Password characters are not trimmed.
- Unknown fields are forbidden, so a client cannot submit roles, account status, verification flags, hashes, or timestamps.

## Registration workflow

```text
Request validation
→ duplicate email/phone checks
→ Argon2 password hashing
→ user creation
→ BUYER role creation
→ hashed phone code creation when applicable
→ transaction commit
→ safe response
```

The route delegates to a registration service, and the service owns one SQLAlchemy transaction. Repositories only query, add, and flush; they never commit or raise HTTP exceptions.

## Database changes

Phase 2 adds no tables and creates no Alembic migration. It uses the existing Phase 1 schema:

- Every successful registration inserts one row in `users`.
- Every successful registration inserts one `BUYER` row in `user_roles`.
- Phone registrations insert one row in `phone_verification_codes`.
- Email-only registrations do not insert a phone-code row.

If any required insert fails, the full operation is rolled back.

## Security decisions

- Raw passwords are never stored or returned; passwords use Argon2 through `pwdlib`.
- Six-digit codes use Python's cryptographically secure `secrets` module.
- Raw phone codes are never stored, logged, or returned.
- Phone codes are protected with HMAC-SHA256 and the dedicated ignored local setting `VERIFICATION_CODE_HASH_SECRET`.
- A placeholder for that setting is tracked only in `backend/.env.example`.
- Code verification uses a constant-time comparison helper for the next phase.
- The client cannot select a role; registration always assigns only `BUYER`.
- No JWT is issued during registration.
- Duplicate pre-checks provide friendly errors, while database unique constraints and `IntegrityError` handling protect against races.

## Error responses

- `201 Created`: registration completed.
- `409 Conflict`: normalized email or phone is already registered. Business codes are `EMAIL_ALREADY_REGISTERED` and `PHONE_ALREADY_REGISTERED`.
- `422 Unprocessable Entity`: invalid or missing identifier, invalid phone/email, weak password, or forbidden field.
- `500 Internal Server Error`: unexpected failures or missing phone-code hashing configuration; the response does not expose internal details.

## Tests

Focused Phase 2 result:

- Unit: 36 passed, 0 failed.
- Integration: 25 passed, 0 failed.
- Total: 61 passed, 0 failed, 0 skipped.

Full backend regression result:

- Total: 83 passed, 0 failed, 0 skipped.

Integration tests use the existing SQLAlchemy session fixture and roll back isolated transactions. They cover successful email/phone/both registration, persisted defaults, normalization, duplicates, response filtering, missing configuration, transaction failures, and safe `IntegrityError` conversion.

## Postman

Collection: `documentation/postman/UniShop_Phase_2_Registration.postman_collection.json`

Before running phone requests locally, set a strong independent value for `VERIFICATION_CODE_HASH_SECRET` in the ignored `backend/.env`, then restart FastAPI.

## Completion checklist

- [x] Exact registration route registered and visible in OpenAPI.
- [x] Email-only, phone-only, and combined registration covered by automated integration tests.
- [x] Email and Chinese phone normalization implemented.
- [x] Password policy and Argon2 hashing implemented.
- [x] `BUYER` is the only assigned role.
- [x] Phone-code records use a six-digit code and keyed hash.
- [x] Raw secrets are neither stored nor returned.
- [x] Duplicate and race-conflict handling implemented.
- [x] Atomic rollback behavior tested.
- [x] Existing schema and Alembic revision retained.
- [x] Phase 2 and full backend automated tests pass.
- [x] Postman collection created.
- [x] Live email-only, phone-only, and combined smoke requests passed with a generated process-only secret; exact smoke rows were removed.

Local configuration note: before normal local phone registration, add a strong persistent `VERIFICATION_CODE_HASH_SECRET` to the ignored `backend/.env` and restart FastAPI. The application deliberately returns a safe configuration error when this required secret is absent.
