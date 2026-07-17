# Phase 1 — Authentication Database

## Objective

Phase 1 establishes the database layer required for authentication without implementing API,
password-hashing, JWT, OTP-delivery, or frontend behavior. The schema stores users, their roles,
hashed refresh tokens, hashed phone verification codes, and hashed password reset codes.

All `DATETIME` values in these tables represent UTC. MySQL `DATETIME` does not retain timezone
metadata, so application code must continue treating stored and retrieved values as UTC.

## Tables

### `users`

Stores the account identifier, password hash, verification state, account status, login timestamp,
and audit timestamps. IDs are UUID strings stored as `CHAR(36)`. Email and phone number are nullable
individually but unique when present, and a database check requires at least one of them.

### `user_roles`

Associates a user with one or more `BUYER`, `SELLER`, or `ADMIN` roles. The combination of user and
role is unique, allowing multiple different roles without duplicate assignments.

### `refresh_tokens`

Stores only a unique hash of each refresh token, along with expiration, revocation, and creation
timestamps. Raw refresh tokens are never persisted.

### `phone_verification_codes`

Stores only a hash of each verification code, its phone number, expiry, attempt count, verification
timestamp, and creation timestamp. Attempts cannot be negative.

### `password_reset_codes`

Stores only a hash of each reset code, its expiry, optional usage timestamp, and creation timestamp.

## Relationships

- User 1 → many UserRoles
- User 1 → many RefreshTokens
- User 1 → many PhoneVerificationCodes
- User 1 → many PasswordResetCodes

Every dependent foreign key references `users.id` with `ON DELETE CASCADE`. SQLAlchemy relationships
use matching `back_populates` definitions and `cascade="all, delete-orphan"` on the user side.

## Security decisions

- Password hashes only; no raw password column exists.
- OTP/code hashes only; no raw phone verification code exists.
- Refresh token hashes only; no raw refresh token exists.
- Reset code hashes only; no raw password reset code exists.
- A database check requires at least one email address or phone number per user.
- One account can have multiple roles, while duplicate user/role pairs are rejected.
- Real database credentials remain in ignored local environment configuration and are not documented.

## Migration

- Revision ID: `a75289cfd4a9`
- Migration filename: `a75289cfd4a9_create_authentication_tables.py`
- Previous revision: base (none)
- Tables created: `users`, `user_roles`, `refresh_tokens`, `phone_verification_codes`,
  `password_reset_codes`
- Alembic-managed table: `alembic_version`
- Model discovery: `alembic/env.py` imports only `app.models`, whose Phase 1 exports register only the
  five authentication models. Placeholder marketplace model modules are not imported.
- Validation result: upgrade succeeded; current revision and head both equal `a75289cfd4a9`.
- Downgrade review: dependent tables are dropped before `users`; the downgrade was reviewed but not
  executed because this task prohibits destructive database changes.
- Unexpected tables created: none

## Tests

- Result: 22 passed, 0 failed, 0 skipped
- Test database strategy: tests use the configured development MySQL schema after migration, but each
  test runs inside an outer transaction with SQLAlchemy savepoints and always rolls back. No test user,
  role, token, or code persists.
- Post-test row counts: zero in all five authentication tables
- Coverage includes supported user identifiers, required identifier checks, unique email/phone/token
  constraints, defaults, multiple roles, duplicate roles, missing foreign keys, non-negative attempts,
  secure hash-only columns, and database-level cascade deletion.

## Phase completion checklist

- [x] Shared account-status and user-role enums implemented
- [x] Five SQLAlchemy 2 authentication models implemented
- [x] Relationships, checks, unique constraints, indexes, and cascades implemented
- [x] Alembic discovers only the five Phase 1 models
- [x] First migration reviewed and applied successfully
- [x] Current Alembic revision equals head
- [x] Actual MySQL tables, columns, constraints, indexes, and foreign keys validated
- [x] No unexpected marketplace tables created
- [x] Twenty-two model tests pass with no persistent test data
- [x] No raw password, OTP, refresh token, or reset code column exists
- [x] No API route, JWT flow, service, seed account, or frontend feature added
