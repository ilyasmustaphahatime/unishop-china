# Private deals API — Phase 14

A deal is an accepted-price agreement, **not** payment, delivery or ownership transfer.
One agreement per product. No create/update/delete/cancel/relist endpoint exists;
POST /api/v1/offers/{offer_ref}/accept is the sole application creation workflow.

| Method/path | Input | Success |
|---|---|---|
| GET /api/v1/deals | limit, cursor, conversation_ref, role | 200 items/next_cursor |
| GET /api/v1/deals/{deal_ref} | none | 200 Deal |

Bearer access JWT and current active account required. Reads join the accepted
proposal and conversation and scope membership before returning data. Nonparticipants
(including unrelated admins) get404. An active participant retains history when
the product is archived or the counterparty is inactive. No internal IDs, identity
profiles, winning-buyer identity for a losing buyer, or private evidence/contact fields.

Response fields: deal_ref, accepted_offer_ref, conversation_ref, product_slug,
role (caller buyer/seller), status (AGREED), amount (two-decimal string), currency
(CNY), agreed_at (UTC), product_title_snapshot, product_condition_snapshot.
Price/currency/participants resolve through the immutable accepted proposal and
conversation. The title/condition are snapshots at acceptance. No duplicate editable
price or fulfillment state exists.

Lists descend by (agreed_at, deal_ref), default20/max50. Optional role and owned
conversation_ref filters; no status filter because agreement has one state. Signed
cursor binds actor, deals purpose, filters, size and position. Offer cursors cannot
be reused. No request body on either operation. Unknown/duplicate queries rejected.

The complete [offer error, privacy and rate-limit contract](offers-api.md) also
applies. All successful/error responses are private/no-store. Accurate bearer,
query, opaque-path, response and error contracts are present in /openapi.json.
Missing cursor configuration fails503; corrupt application-invariant agreement
state fails closed rather than projecting a nonaccepted price.

See [architecture](../architecture/ADR_PHASE_14_OFFERS_DEALS.md) and
[verification report](../phases/PHASE_14_DEALS_OFFERS.md). Production ready: **NO**.
