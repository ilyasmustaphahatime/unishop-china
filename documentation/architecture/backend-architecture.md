# backend architecture

Verified through Phase 10 on 2026-10-12. This is a modular monolith, not a completed
marketplace or a production release.

## Request and dependency direction

```text
main.create_app: configuration, CORS, ingress limits, safe errors, private headers
  -> mounted API routers: auth, profiles, seller verification, catalog/admin, products/seller-products
    -> dependencies: Bearer identity, peer/user budgets, Origin and CSRF
      -> strict Pydantic request contracts
        -> domain services: authorization, invariants, transaction ownership
          -> repositories and provider/storage adapters
            -> SQLAlchemy Session / MySQL
```

Routes own HTTP parsing, status/headers, cookies and response DTOs. Services own
business transitions and authoritative checks. Repositories own queries, current
locking reads and conditional updates, never final commits. Services also construct
and modify ORM entities inside their unit of work: this is an explicit SQLAlchemy
unit-of-work design, not a persistence-free domain framework.

## Modules and cross-cutting boundaries

Auth owns registration, phone/email verification, login, JWTs, refresh families,
password reset/change and logout. Profiles owns one own profile, onboarding,
immutable handles and minimal public projections. Seller owns private draft,
three-image submission, independent admin review and rejection retry; approval
does not grant roles; listing authority separately checks current approval. Catalog owns cities/two-level
categories and activation/hierarchy/capacity rules. Admin is authority-gated access
to seller/catalog operations, not another persistence domain or a dashboard.

Delivery and StorageProvider interfaces isolate external adapters. Profile city
assignment calls CityService; public badge reads a narrow seller repository boolean.
Neutral rules live in common/plain_text and common/evidence_limits. Shared HTTP
peer/HMAC-user limiting lives in api/rate_limits; domains keep budgets, namespaces
and HTTP error contracts. Seller error mapping lives in its errors module, not
another route module. core/authorization is intentionally application policy using
user persistence, not a persistence-free utility.

## Transaction convention

Services are commit owners. get_db supplies, rolls back unhandled failures and
closes a Session; it never commits business operations. Refresh/email/change use
commit_request_transaction: preserve operation savepoint semantics when an auth
read already opened the transaction, then commit once, recovering the Session on
commit failure. Profile/seller/catalog use transaction, additionally rolling back
outer state on failure. Login/reset composition retains caller-owned boundaries;
do not substitute a helper that commits early. Repositories never commit.

Locks stay through commit; locked entity reads refresh cached identities. Only
existing whole DB transactions retry bounded InnoDB 1213 deadlocks; delivery/storage
side effects are not retried. Seller/catalog audit inserts share the mutation
transaction. Evidence bytes are returned only after EVIDENCE_READ audit commits.

See [the full review and invariant/test map](PHASE_1_TO_8_ARCHITECTURE_REVIEW.md).

## Phase 9 listing boundary

ProductListing owns immutable seller identity/slug, plain text, Decimal price,
fixed CNY, four lifecycle states and catalog FKs. Thin routes call ProductService
for current eligibility, BOLA, transitions and transactions. ProductRepository owns
bounded joined projections/current reads and eight savepoint collision retries
limited to the named unique-slug constraint. No media or transaction domain.
ProfileService exposes completed-onboarding rules. Shared authorization checks
approved seller state separately from Phase 7 request eligibility and JWT roles.

Lock order: user -> seller verification (eligible operations) -> profile (eligible
operations) -> owned listing -> existing catalog DB mutex -> city/category
references. Creation has no existing listing to lock. The catalog mutex serializes
assignment/publication and hierarchy changes; bounded owner reads acquire it before
locking joined references. Current locked reads refresh identities and bypass old
REPEATABLE READ snapshots. Public detail is one visibility statement selecting
safe profile labels/eligibility flags, not email, phone, passwords, or evidence.
Existing transaction/1213 retry conventions are reused. No process mutex, Redis,
queue, external-side-effect retry, or generic product audit system was introduced.

The conservative catalog mutex is a throughput tradeoff for this small catalog;
benchmark before scaling. Partial edits serialize; conflicting same-field edits are
last-writer-wins, not an invented version/ETag framework. A shared actual-byte/time
JSON reader preserves Phase 8 bounds and supports Phase 9 pre-parse budgets.
See [historical Phase 9 evidence](../phases/PHASE_9_PRODUCT_LISTINGS.md).

## Phase 10 product media boundary

Six thin image routes -> dependencies/strict DTOs -> ProductImageService ->
ProductImageRepository and a narrow ProductImageStorage adapter. No duplicate
product authority: image services reuse current Phase 9 eligibility/ownership and
the same public visibility query. Media is never encoded into a listing PATCH or
stored in MySQL. Opaque refs are independent of private random object keys.

Upload preflights locked current authority/parent/quota, bounded-reads and sanitizes,
then saves bytes once. Final pure-DB metadata transaction reacquires/rechecks these
rules; only that DB work retries deadlocks. Failed commit compensates the new file.
Reorder and metadata deletion serialize on the parent and resequence through
reserved positions 8..15 before committing contiguous 0..7. Delete metadata commits
before physical cleanup; failure is an invisible orphan, not rollback-to-public.

Pre-parse actual-byte/time/spool and peer concurrency boundaries protect multipart;
authentication/user budgets precede parsing; decoder concurrency is bounded.
Local storage uses containment/link guards, exclusive temporary writes/fsync and
exclusive hard-link publication. It is separate from seller evidence, ignored and
never static-served; production local adapter is disabled. Report-only audit is
explicitly not a reconciler/cleanup job. Real MySQL races and failure-injection
tests verify these boundaries; see [Phase 10 gate](../phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md).
