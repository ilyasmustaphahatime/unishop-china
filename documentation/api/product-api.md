# Product Listings Core API — Phases 9-10

All paths are relative to `/api/v1`. Listing navigation uses immutable opaque
`item-` plus 24 lowercase hex characters: never an internal UUID, title, identity,
token, or storage reference. There is no public collection/feed endpoint.

| Method | Path | Authority / result |
|---|---|---|
| GET | `/products/{slug}` | Public; eligible PUBLISHED listing only, otherwise generic 404 |
| POST | `/seller/products` | Eligible authenticated seller; creates DRAFT, 201 |
| GET | `/seller/products?limit=20&offset=0` | ACTIVE owner; all own states, bounded pagination |
| GET | `/seller/products/{slug}` | ACTIVE owner; cross-owner/unknown 404 |
| PATCH | `/seller/products/{slug}` | Eligible owner; editable non-ARCHIVED listing |
| POST | `/seller/products/{slug}/publish` | Eligible owner; DRAFT/PAUSED to PUBLISHED |
| POST | `/seller/products/{slug}/pause` | ACTIVE owner; PUBLISHED to PAUSED |
| POST | `/seller/products/{slug}/archive` | ACTIVE owner; non-ARCHIVED to terminal ARCHIVED |

Owner endpoints use the existing Bearer header; never URL credentials. Action
bodies are required empty JSON objects `{}`. Invalid/repeated transitions return
409. There is no DELETE or ownership transfer.

Creation is deliberately non-idempotent: two independent valid POST requests can
create two drafts with different slugs. The frontend form permits one in-flight
submission, including during asynchronous validation, and releases that guard
after failure for an explicit retry. This is not cross-tab/API idempotency. The
shared client does not retry arbitrary network failures; its single authenticated
401 refresh retry occurs only when the failed request did not pass authentication.
After an ambiguous connection failure, inspect own listings before manually retrying.

Creation requires exactly these six fields:

```json
{
  "title": "Study desk",
  "description": "A sturdy desk in good condition.",
  "price": "150.25",
  "condition": "good",
  "city_slug": "qingdao",
  "category_slug": "study"
}
```

`study` is an illustrative catalog slug, not a seeded/fallback category. Categories
start empty: an existing database-authorized admin must create an active category.
Fetch Phase 8 city/category endpoints for actual choices.

PATCH permits only the same six fields, at least one supplied. Omitted fields stay
unchanged; explicit nulls and extra fields are rejected. Owner IDs, UUIDs, slug,
status, currency, timestamps, and media fields are never writable. Unchanged
retired references can remain while other fields are edited; assigning a reference
or publishing requires current active city/category (and active parent).

Title: NFC plain text, normalized whitespace, 3–120 Unicode code points.
Description: NFC trimmed plain text, 10–5,000 code points, LF/tab permitted;
CRLF normalizes to LF. Controls, surrogates and bidi-direction controls fail.
HTML-shaped text is data, not markup: clients render it as escaped text.
Conditions: `new`, `like_new`, `good`, `fair`.

Price is a JSON string: positive ordinary decimal notation, at most ten integer
digits and two fractional digits, maximum `9999999999.99`. No leading zeros except
`0.xx`, exponents, signs, whitespace, NaN, infinity, numeric JSON, or rounding.
Response prices have two decimal places. Currency is server-selected CNY;
Python Decimal/MySQL DECIMAL(12,2) are used, not float arithmetic.

Create/edit/publish eligibility comes from locked current database state: ACTIVE
account, verified email + phone, approved Phase 7 seller attempt, valid completed
onboarding. Approval does not grant roles: a BUYER with approval qualifies. JWT
roles do not authorize products. ACTIVE owners retain list/read/pause/archive after
losing verification/onboarding; inactive accounts cannot use any owner operation.

Public visibility additionally requires PUBLISHED status and active listing city,
category and parent. Unknown, draft, paused, archived, and now-ineligible listings
all return `{"detail":"Listing not found."}` with 404, never hidden-state details.

Public fields: `public_slug`, `title`, `description`, `price`, `currency`, `condition`,
`status` (PUBLISHED), `city`, `category`, `published_at`, `seller`, `images`. Images
are ordered safe `ref`, `position`, `url` projections, maximum eight; empty is valid.
See [product image API](product-images-api.md). City/category reuse
public catalog contracts. Seller has only `public_handle`, `display_name`,
`seller_verified: true`. No IDs, PII, roles, private evidence or session metadata.
Own responses omit seller and add status, `city_active`, `category_active`,
`created_at`, `updated_at`; internal IDs remain absent. Collection returns `items`
and nullable `next_offset`, ordered updated_at DESC then internal id DESC.
Limit 1–100 (default 20); offset 0–100000. One joined listing query, no count query.

Errors: 401 invalid/inactive identity; 403 missing eligibility; 404 inaccessible or
hidden resource; 409 lifecycle conflict; 422 validation/inactive assignment;
429 budget; 503 generic operation failure. No SQL/request-value echo.
Actual-peer budgets run before parsing (including malformed JSON): reads 180/min,
writes 90/min. Authenticated reads 60/user/min, writes 30/user/min, common peer
120/min. Process-local limits retain the existing multi-worker production blocker.
Actual body bound 32 KiB and input-time bound 15 seconds; JSON media type required.
Products/owner responses, including errors, use no-store and no-referrer.

Phase 10 adds six image operations, not writable media fields on listing PATCH.
No browsing/search, favorites, chat, deals, orders, payment, moderation, or admin
product dashboard is implemented here.
