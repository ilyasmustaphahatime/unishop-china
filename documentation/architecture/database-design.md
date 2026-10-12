# database design

Verified through Phase 9 on 2026-10-09. Runtime and Alembic share the validated backend environment
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
| Products | product_listings (UUID PK, unique opaque public slug; RESTRICT seller/city/category FKs; DECIMAL(12,2); eight checks; owner updated/id ordering and FK indexes) |

SQLAlchemy expressions bind values. Internal UUIDs are not public catalog/profile
navigation aliases. FKs/uniqueness protect integrity independently of frontend
validation. Locked entity reads use populate_existing to replace stale identities.

## Migration chain

```text
a75289cfd4a9 -> c91e4a7b2d6f -> aca2dda0ef53 -> d5f0c1e2a3b4
 -> f6a1b2c3d4e5 -> a61b2c3d4e5f -> b7c1d2e3f4a5 -> c7d8e9f0a1b2
 -> d8e9f0a1b2c3 -> e8f0a1b2c3d4 -> f9a1b2c3d4e5 (sole head)
```

Current/head/history and alembic check pass. Phase 9 adds only product_listings,
without rewriting existing rows or seeding products. Phase 8 refuses unknown city labels before MySQL DDL, seeds six cities once
and starts categories empty. Additive e8 closes nullable composite-parent UNKNOWN
semantics. No development reseed/downgrade/truncate or real-data deletion occurred.

Upgrade/downgrade/upgrade and old-data preservation were verified only in the
script-owned disposable MySQL instance for the scoped Phase 9-to-8 and prior
profile/seller/catalog cycles. The final adversarial audit also verified an empty
base-to-head upgrade. It found an inherited full rollback-to-base failure in
`c91e4a7b2d6f`: downgrade drops a foreign-key-supporting index before its foreign
key (MySQL 1553). That historical migration remains unchanged; full-history
rollback is NOT certified and needs a separately approved resolution. See the
[final audit](../phases/PHASE_9_FINAL_ADVERSARIAL_AUDIT.md).
Never run destructive downgrade tests on
working development/production. Ordered count/SHA-256 fingerprints across all 14
pre-existing tables are unchanged after regression/live cleanup; product_listings
is empty after cleanup. This is not backup-recovery proof. Phase 9 downgrade drops
listings and must never be run as a development/production test.

See [the full review](PHASE_1_TO_8_ARCHITECTURE_REVIEW.md).
