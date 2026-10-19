# ADR: private product associations and serialized bounded writes

Status: implemented, pending independent Phase 12 final audit and Git closure.

## Decision

Favorites and recent history are independent composite-key associations between
`users` and `product_listings`. They store one UTC DATETIME(6) each, never copies
of product/seller/media data. CASCADE foreign keys remove only dependent personal
rows on physical parent deletion; hiding or archiving a listing retains them.
One additive revision `c12d3e4f5a6b` follows `b11b2c3d4e5f`.

Routes handle HTTP/dependencies; strict schemas define external contracts;
`FavoritesService` and `RecentlyViewedService` own transactions and business
policies; repositories compose parameterized SQL without commits or HTTP errors.
Every write locks the authoritative ACTIVE actor row first through the existing
`lock_active_user`, then changes only that user's associations. A fixed lock order
serializes duplicate saves, quota checks, history upserts/pruning, deletes and
clears. Current `FOR UPDATE` association reads avoid stale quota/retention state
after waiting under MySQL REPEATABLE READ, even if authentication opened a read
snapshot first. No global locks, global cleanup jobs or external lock service.
The existing whole-transaction retry handles only InnoDB deadlocks (1213), at
most three attempts. Unrelated errors propagate to the safe HTTP boundary.

Favorite saves preserve their original timestamp and count retained hidden rows
toward the configured cap. History uses MySQL `ON DUPLICATE KEY UPDATE` with
`GREATEST(existing, observed)` to resist out-of-order timestamps, then prunes a
bounded current-user set. Retention timestamp ties use product ID; public page
ties use immutable public slug. Clear and record outcomes follow transaction
order; a later record is allowed after clear.

Both list repositories drive a single projection SELECT from the current user's
association table, reuse the canonical `publicly_visible()` joins/predicate, and
apply eligibility before the `limit+1` keyset. The shared public-card SQL and
serializer are small extractions from Phase 11B; browse sorting, full-text search,
hints, filters, cursors and response contracts remain unchanged. Indexed per-user
time lookups bound the working set to 500/100; sorting public-slug ties can require
a bounded sort. No all-product scan, full ORM graph, N+1, OFFSET, exact per-page
COUNT, or speculative counters.

Private cursors contain version, keyed context digest, timestamp and public slug.
The context binds user identity, purpose and limit without publishing raw user
IDs. The key is HMAC-derived from existing validated shared signing configuration
with a dedicated personal-list domain; signatures use a second explicit domain.
Canonical base64url, exact payload fields, duplicate-key rejection, timestamp
validation and constant-time comparison reject token confusion. Existing Phase
11B key/token behavior is untouched. Key rotation invalidates cursors.

## Consequences and limits

Personal lists reflect request-time public visibility, never permanent access.
Standard database snapshots can race later visibility changes; public image reads
independently re-check eligibility. Keyset pagination is deterministic for stable
data, not a cross-request snapshot of changing history. The user row lock also
serializes other account operations, so requests must keep transactions short.
Fixed caps deliberately trade unbounded history for predictable query/write work.
Rate limits remain process-local; distributed controls belong to Phase 19.

All private responses and errors are non-cacheable. No third-party activity
tracking, public favorite counts or frontend UI is introduced. A future frontend
must explicitly record successful views and discard cached personal data during
account switching. Production operational/storage/dependency gates remain
separate; this decision makes no production-capacity claim.
