# Private offers API — Phase 14

All paths below are relative to /api/v1. Bearer access JWT required; current active
account and conversation membership checked server-side. No cookie authentication,
admin bypass, client participant IDs or internal IDs. Responses and errors are
Cache-Control: no-store, Pragma: no-cache and Referrer-Policy: no-referrer.

| Method/path | Input | Success |
|---|---|---|
| POST /offers | conversation_ref, amount, client_offer_id | 201 Offer; identical replay 200 |
| GET /offers | limit, cursor, conversation_ref, role, status | 200 items/next_cursor |
| GET /offers/{offer_ref} | none | 200 Offer |
| POST /offers/{offer_ref}/counteroffers | amount, client_offer_id | 201 Offer; identical replay 200 |
| POST /offers/{offer_ref}/accept | no body | 200 Deal |
| POST /offers/{offer_ref}/reject | no body | 200 Offer |
| POST /offers/{offer_ref}/withdraw | no body | 200 Offer |

Example initial body (references are illustrative):

```json
{"conversation_ref":"cv-0123456789abcdef0123456789abcdef","amount":"45.50","client_offer_id":"00000000-0000-4000-8000-000000000001"}
```

Only JSON decimal strings are accepted: 0.01 through 9999999999.99, up to two
fractional digits, fixed two-decimal output. Numbers, booleans, signs, exponent,
whitespace, leading zero variants, nonfinite values and silent rounding are rejected.
Client IDs are canonical lower-case UUID strings. Server derives role, product,
participants, state and microsecond UTC timestamps. Unknown body fields, duplicate
JSON keys, duplicate/unknown query fields and noncanonical page limits are rejected.

Offer response fields: offer_ref, conversation_ref, product_slug, role (caller),
proposer_role, amount, currency, status, created_at, expires_at, closed_at,
closed_by_role, closure_reason, parent_offer_ref, counteroffer_ref, deal_ref.
Role values are buyer/seller; states are PENDING, ACCEPTED, REJECTED, WITHDRAWN,
COUNTERED, EXPIRED, CANCELLED. Closure reason is null, EXPIRED or PRODUCT_UNAVAILABLE.
All dates are UTC ISO timestamps. Expired pending storage is projected consistently;
GET never materializes expiry. Create/counter return an opaque Location header.

Buyer starts. Recipient accepts/rejects/counters; proposer withdraws. Countering
closes its parent and creates a new proposal. An identical retry uses the original
client ID and canonical terms; conflicts return 409. Transition retries by the same
authorized role return the existing outcome, including acceptance after archival.
Current eligibility is required for new commitments; history and permitted rejection/
withdrawal remain available to an active actor with an inactive counterparty.

Pagination: descending (created_at, offer_ref), default20/max50. Optional filters:
owned conversation_ref, caller role buyer/seller and one lifecycle status. Cursor
is signed and bound to actor, purpose, filters and size; reuse the same query fields.
No offset, arbitrary sort, participant IDs or total-count scan. Status filtering occurs
before LIMIT. Terminal-state/expiry changes can affect membership between pages.

## Safe errors and budgets

OpenAPI documents 400 cursor, 401 credentials/inactive actor, 403 role/verification/
origin, 404 missing/nonmember, 408 input timeout, 409 lifecycle/expiry/availability/
idempotency conflict, 413 byte limits, 415 content type, 422 strict input, 429 budget,
500 generic unexpected failure and 503 unavailable persistence/auth/cursor configuration.
Errors are {"detail": "safe message"}; validation may use detail entries containing
type/loc/msg, never submitted values or SQL. 429 includes Retry-After.

Before parsing: body 1,024 actual bytes, query 1,200 bytes, body deadline5 seconds;
application/json for proposal bodies, no bodies on read/transition routes. In-memory
per-peer budgets: read240/write60 per minute. Per-account read120/write20 per minute,
shared across offers/deals; key stores cap at10,000 and fail closed on exhaustion.
These are single-process controls, not distributed quotas. Raw transport URL logs
for offers/deals are suppressed, including rejected URL credentials/cursors.

No payments, shipping, cancellation/relisting, chat event or consent handoff side effects.
See [architecture](../architecture/ADR_PHASE_14_OFFERS_DEALS.md),
[deals](deals-api.md), and [verification](../phases/PHASE_14_DEALS_OFFERS.md).
