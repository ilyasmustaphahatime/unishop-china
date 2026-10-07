# database design

Verified 2026-10-07. Runtime and Alembic share the validated backend environment
URL, MySQL/PyMySQL and metadata. The dedicated unishop_app account connects to
unishop_china with utf8mb4 and pool_pre_ping. Credentials are not documented here
or committed. Bootstrap SQL is not the migration authority.

## Ownership and integrity

| Domain | Tables / constraints |
|---|---|
| Auth | users (UUID PK, unique email/phone, account state); user_roles (user FK, unique role per user); phone_verification_codes, password_reset_codes, email_verification_codes (user FKs, nonnegative attempts); refresh_tokens (user FK, unique hash, family/expiry/revocation fields, replacement FK) |
| Profiles | user_profiles (unique user FK, unique immutable public handle, city FK); historical city label retained for safe migration/downgrade; display resolved from city reference |
| Seller | seller_verifications (owner/reviewer FKs, opaque review reference, active-slot uniqueness, expiry/state constraints); seller_evidence (request FK, unique kind, private metadata); seller_verification_audit (request/actor references, minimal event) |
| Catalog | cities (unique slug); categories (unique slug, level checks, complete composite parent FK); admin_catalog_audit (server-derived actor/action/slug and changed field names); catalog_write_lock (single row serializes structural/capacity changes across sessions) |

SQLAlchemy expressions bind values. Internal UUIDs are not public catalog/profile
navigation aliases. FKs/uniqueness protect integrity independently of frontend
validation. Locked entity reads use populate_existing to replace stale identities.

## Migration chain

```text
a75289cfd4a9 -> c91e4a7b2d6f -> aca2dda0ef53 -> d5f0c1e2a3b4
 -> f6a1b2c3d4e5 -> a61b2c3d4e5f -> b7c1d2e3f4a5 -> c7d8e9f0a1b2
 -> d8e9f0a1b2c3 -> e8f0a1b2c3d4 (sole head)
```

Current/head/history and alembic check pass. This review changes no migration or
schema. Phase 8 refuses unknown city labels before MySQL DDL, seeds six cities once
and starts categories empty. Additive e8 closes nullable composite-parent UNKNOWN
semantics. No development reseed/downgrade/truncate or real-data deletion occurred.

Upgrade/downgrade/upgrade and old-data preservation were verified only in the
script-owned disposable MySQL instance. Never run destructive downgrade tests on
working development/production. Ordered count/SHA-256 fingerprints across all 14
tables are unchanged after regression/live cleanup. This is not backup-recovery proof.

See [the full review](PHASE_1_TO_8_ARCHITECTURE_REVIEW.md).
