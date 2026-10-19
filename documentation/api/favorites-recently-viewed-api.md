# Private favorites and recently viewed API (Phase 12)

All paths below are relative to `/api/v1`. Every operation requires the existing
Bearer access token and an ACTIVE account. Ordinary buyers need no seller
verification or completed seller profile to manage these private lists. The
server derives ownership exclusively from the authenticated user; there is no
user-ID parameter. Cookie-only authentication is not accepted.

| Method | Path | Result |
|---|---|---|
| PUT | `/me/favorites/{slug}` | 200 `{"favorited":true}`; idempotent, original save time retained |
| DELETE | `/me/favorites/{slug}` | 204; unknown, absent and now-hidden associations behave identically |
| GET | `/me/favorites` | Private currently-public product cards, newest save first |
| POST | `/me/favorites/lookup` | Batched private membership for public products |
| POST | `/me/recently-viewed/{slug}` | 204; explicitly record or refresh a public product view |
| GET | `/me/recently-viewed` | Private currently-public product cards, newest view first |
| DELETE | `/me/recently-viewed/{slug}` | 204; idempotent current-user removal, including hidden products |
| DELETE | `/me/recently-viewed` | 204; physically delete only the current user's history |

Slugs use the existing exact `item-` plus 24 lowercase hexadecimal characters.
No operation except lookup accepts a request body. An unexpected nonempty body
returns 422; actual request bodies over 4,096 bytes return 413. Lookup requires
`Content-Type: application/json` (otherwise 415) and exactly this schema:

```json
{"product_slugs":["item-0123456789abcdef01234567"]}
```

Supply 1–50 unique, valid slugs. Duplicate slugs, extra fields, nulls and incorrect
types return safe 422 errors. Lookup returns every submitted slug mapped to a
boolean. Hidden, nonexistent, and not-favorited products uniformly map to `false`;
membership belonging to other users never affects the result.

```json
{"favorites":{"item-0123456789abcdef01234567":false}}
```

Both list endpoints accept only `limit` (canonical integer 1–50, default 24) and
`cursor` (server-issued string, maximum 512 characters). Repeated or unknown
query keys return 422, and raw queries over 1,024 bytes return 413. All other
operations reject query parameters. Lists return:

```json
{
  "items": [],
  "next_cursor": null,
  "has_more": false
}
```

Each favorite item contains `product` (the existing complete public `ProductCard`
contract from [browse/search](product-browse-search-api.md)) and `favorited_at`.
History items contain the same `product` and `last_viewed_at`. Association times
are UTC RFC3339 strings with an explicit `Z` offset; product fields preserve the
existing browse contract. There are no internal UUIDs, private storage keys,
seller contact information, evidence, owner fields, or exact totals. The current
first ordered product image becomes the optional public cover on each read.

Order is `(association timestamp DESC, public_slug DESC)`. Continue with the same
user, list type and page size. Cursors are versioned and HMAC signed, with a
purpose-separated key and keyed user/list/limit context. Tampered, malformed,
cross-user, cross-list, public-browse or changed-limit cursors return generic
400 `Invalid cursor.`. Changing `BROWSE_CURSOR_SIGNING_KEY` invalidates private
cursors too; development may reuse the validated JWT key as a derivation source.
No raw user identity or internal product ID appears in the cursor payload.

Each page evaluates canonical public eligibility in SQL before `limit+1`:
PUBLISHED listing, eligible ACTIVE verified/onboarded seller and active city,
category and parent. Hidden associations remain stored and can reappear after
eligibility is restored. A favorite is never an access grant. PUT/record on a
hidden or nonexistent product returns the same generic 404. Removal does not
require public visibility. A changed list between requests is not a snapshot;
re-viewing a product changes its ordering and may alter later pages. Restart at
page one after significant changes or account switching.

`PERSONAL_FAVORITES_LIMIT` defaults to 500 (allowed 1–500), counting hidden saved
associations. A repeat PUT for a still-public saved product succeeds even at the
cap; a new product beyond the cap returns 409 `Saved listing limit reached.`.
No saved items are silently evicted. `PERSONAL_HISTORY_LIMIT` defaults to 100
(allowed 1–100). Recording a view upserts one row, never moves its timestamp
backwards, and prunes only that user's oldest excess rows. Timestamp ties during
retention use a private deterministic product-ID tie-breaker; public pagination
uses public slugs. Clear and record serialize on the user: a later recording may
create an entry after a successful clear. Public product GET never records views.

All personal responses, including validation/auth/rate/storage errors, carry
`Cache-Control: no-store`, `Pragma: no-cache`, and `Referrer-Policy: no-referrer`.
Per process, actual-peer boundaries allow 240 reads/minute or 120 writes/minute
before parsing; authenticated operations additionally share 180 requests/minute
per peer, 120 reads/minute per user, or 60 writes/minute per user. Malformed JSON
consumes the pre-parser peer budget. Rate failures return 429 with `Retry-After`.
Distributed controls are deferred to Phase 19. Input time is bounded to 15 seconds.

Expected errors: 401 missing/invalid/expired/inactive identity for otherwise valid
requests; 404 unavailable product on save/record; 409 save quota; 400 cursor;
422 schema/query; 413 byte limits; 408 slow input; 415 lookup media type; 405
unsupported method; 429 rate budget; safe 503 database/service unavailability.
Early input boundaries can reject malformed requests before authentication.
Errors never return raw SQL, driver messages or request values.

Future frontend callers must explicitly POST a view after displaying successful
public details and clear private UI caches on account switching. Phase 12 adds
no frontend recording, screens, anonymous tracking, analytics or public counts.
