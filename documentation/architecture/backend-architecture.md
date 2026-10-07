# backend architecture

Verified 2026-10-07 through Phase 8. This is a modular monolith, not a completed
marketplace or a production release.

## Request and dependency direction

```text
main.create_app: configuration, CORS, ingress limits, safe errors, private headers
  -> mounted API routers: auth, profiles, seller verification, catalog/admin
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
does not grant roles or listing permissions. Catalog owns cities/two-level
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
