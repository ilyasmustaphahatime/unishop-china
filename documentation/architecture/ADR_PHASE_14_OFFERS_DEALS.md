# Phase 14: private offers and immutable agreements

Status: implemented; awaiting independent final audit. Production ready: **NO**.
Decision date: 2026-11-07. Scope: backend modular monolith only.

## Boundaries

Routes authenticate bearer JWTs, validate strict transport contracts and project safe errors.
OfferService owns proposal policy, idempotency and the complete mutation transaction.
DealService only reads participant-scoped agreement projections. Repositories perform
parameterized SQL and never commit. Neutral policy/cursor types live in common/offers.py.
The existing deal model/repository/service/schema/router placeholders are reused.

An existing Phase 13 conversation is the immutable buyer/seller/product boundary.
There is no independently editable participant list, agreed price, payment state or
completion state. References are random of-/dl- plus 32 hexadecimal characters, not
internal UUIDs. There is no global-admin ownership bypass.

## Business rules

| Source | Actor/action | Destination |
|---|---|---|
| No proposal | Buyer creates | PENDING |
| PENDING | Recipient accepts | ACCEPTED + one deal + ARCHIVED product |
| PENDING | Recipient rejects | REJECTED |
| PENDING | Proposer withdraws | WITHDRAWN |
| PENDING | Recipient counters | COUNTERED + a new linked PENDING proposal |
| PENDING | Server deadline reached | EXPIRED |
| PENDING | Manual archive or competing acceptance | CANCELLED (or EXPIRED if already due) |

Every proposal has immutable decimal-string CNY terms and an exact 24-hour deadline.
Equality is expired. Reads compute effective expiration without writes; replacement
materializes expiration before taking the one-pending slot. Countering never edits
an earlier amount. Alternating roles are derived from the conversation and parent.
Terminal rows never reopen. Initial/counter retries compare canonical amount and
parent identity under the unique conversation/role/client UUID key.

One agreement maximum per listing, forever in this phase. Acceptance captures the
current title and condition; it does not copy another editable price. No cancellation,
relisting, quantity, payment, delivery or ownership-transfer claims are introduced.

## Transaction and lock policy

1. Buyer and seller User rows, sorted by internal UUID.
2. Product listing row.
3. Existing catalog write guard and canonical current seller/product eligibility reads.
4. Conversation row.
5. Target proposal and relevant idempotency/pending/deal guards.
6. Competing pending offers, ordered by public reference, while holding the product.

Existing transaction helpers own commit/rollback; only confirmed InnoDB deadlocks
retry, at most three whole attempts. No external side effect occurs inside a transaction.
ProductService manual archival calls the transaction-neutral repository closure helper;
it never calls an independently committing OfferService operation. Acceptance does
not call ProductService. Shared product locks serialize both paths, and neither
acquires a new participant account after taking the product lock.

Mutation replay/result projections use current locking reads after context locks.
Real MySQL races demonstrated why an earlier authentication REPEATABLE READ snapshot
must not be used to recover a concurrently committed proposal/deal. The regression
suite retains that case. Read endpoints use ordinary scoped projections after a current
active-actor check. Success is returned only after transaction commit, including replays.

Acceptance closes the winner, inserts a uniquely product-bound deal, archives the
listing and closes competitors atomically. Known unique-key conflicts become safe
409 errors; persistence failures become safe 503 errors. Commit failure rolls back
winner, competitors, deal and archival together.

## Eligibility, privacy and history

Creation, countering and acceptance require active email/phone-verified participants
and canonical public-product eligibility (seller verification/profile, account,
catalog and listing status). State is rechecked under locks. Temporary ineligibility
blocks commitments without destroying history. An active participant can read with
an inactive counterparty, and can reject/withdraw according to proposal role.
Identical authorized outcomes are recovered before refusing an unavailable product.

All nonparticipant object reads/mutations return 404; known wrong-role participants
receive 403. No UUID, evidence/storage key, contact ciphertext, winning buyer identity
or other negotiation's price is returned. Losing offers expose only their own terms
and a generic PRODUCT_UNAVAILABLE closure. Explicit DTOs, no-store headers, bounded
input, peer/account budgets, origin policy and URL-log suppression apply to both roots
and descendants. Existing JWT lifetime/revocation semantics are unchanged.

## Schema and migration

Additive revision e14f5a6b7c8d follows d13e4f5a6b7c. Add the explicit unique conversation
(id, product_listing_id) key, offers, then deals. All history FKs use RESTRICT.
Offers enforce matching conversation/product and parent/conversation by composite
FKs, root buyer, positive DECIMAL(12,2), CNY, role/status/timestamp/closure shape,
one child per parent, idempotency uniqueness and a generated nullable PENDING slot.
Deals uniquely constrain both accepted offer and product; a composite FK binds both.
Application policy enforces ACCEPTED status and history immutability; raw database
administrator writes are not an authorized application API.

Development is forward-only. Downgrade testing runs exclusively in a newly initialized,
disposable loopback MySQL instance with synthetic credentials and a distinct datadir/port.

## Pagination and scaling tradeoffs

Default 20/max 50. Time/public-ref keysets use a separate HMAC domain with actor,
purpose, filters, page size and position binding. Existing browse signing material
is domain-separated, never a JWT fallback. Missing configuration fails closed.
Effective status filtering occurs before LIMIT. Lists are deliberately non-snapshot:
time/state changes between pages can change membership; restart traversal to refresh.

The normalized participant relation requires sorting matching actor history. Two
disjoint role branches start from existing participant indexes, then indexed offer
lookups (MySQL STRAIGHT_JOIN/FORCE INDEX), each contributes at most limit+1 candidates;
the merge is at most 102 and projection query count is constant. This avoids a global
offer scan observed in initial EXPLAIN, not all growth with a heavy user's history.
Three EXPLAIN regressions cover unfiltered offers, status-filtered offers and deals
with 300 synthetic offers. Large-history sustained-load qualification is deferred;
no denormalized per-user materialized lists or new infrastructure are introduced.

## Phase 13 and retained findings

No chat message, consent disclosure, WebSocket event or notification is generated.
Archived-product conversation history continues under the existing chat policy.
The chat protocol, crypto, seller evidence access and frontend are unchanged.
The shared transport log filter additionally suppresses offer/deal URL records.

P12-ARCH-LOW-01 and P12-AUDIT-OPENAPI-01 remain unresolved. The previously identified
Phase 13 LOW test-fixture observation (global counts/unfiltered updates in older chat
tests) is not repaired by this phase; new offer fixtures scope all mutations and
committed cleanup to synthetic identities. Existing production storage, deployment
TLS/WSS, browser, Docker/NGINX and operational acceptance blockers remain separate.
