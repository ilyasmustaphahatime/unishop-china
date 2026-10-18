# Public product browse/search API (Phase 11B)

`GET /api/v1/products` is anonymous and returns only currently public,
published listings. It does not accept a Bearer token and does not expose owner
data. Responses use `Cache-Control: no-store` because seller/catalog eligibility
can change between requests.

## Query parameters

| Parameter | Contract |
|---|---|
| `q` | Optional NFC-normalized Unicode keyword query; 2–80 characters after whitespace normalization, at most eight words, each with at least two alphanumeric characters. Unicode letters, numbers, combining marks and spaces are accepted; punctuation/Boolean operators are rejected. |
| `city` | Optional exact active city slug (2–63 lowercase ASCII characters). |
| `category` | Optional exact active category slug; a root filter does **not** implicitly include children. |
| `min_price`, `max_price` | Optional exact CNY decimals, 0 through `9999999999.99`, at most two decimal places; `max_price >= min_price`. No floats, signs or exponents. |
| `condition` | `new`, `like_new`, `good`, or `fair`. |
| `sort` | `newest` (default), `price_asc`, or `price_desc`. |
| `limit` | Integer 1–50, default 24. |
| `cursor` | Server-issued opaque, signed continuation token, at most 512 characters. |

Repeated or unknown query keys are rejected. Raw query strings over 1,024 bytes
are rejected before parsing. Public browse is also limited to 60 requests per
minute per peer in the current process, on top of the existing product read
budget. Malformed requests consume that budget.

## Response

```json
{
  "items": [
    {
      "public_slug": "item-0123456789abcdef01234567",
      "title": "Example desk",
      "price": "150.25",
      "currency": "CNY",
      "condition": "good",
      "city": {"slug": "qingdao", "name_en": "Qingdao", "name_zh": "青岛", "province_en": "Shandong", "province_zh": "山东", "country_code": "CN"},
      "category": {"slug": "furniture", "name_en": "Furniture", "name_zh": "家具", "description": null, "parent_slug": null},
      "cover_image": {"ref": "img-0123456789abcdef0123456789abcdef", "url": "/api/v1/products/item-0123456789abcdef01234567/images/img-0123456789abcdef0123456789abcdef"},
      "seller": {"public_handle": "seller-example", "display_name": "Example Seller", "seller_verified": true},
      "published_at": "2026-10-14T12:00:00"
    }
  ],
  "next_cursor": null,
  "has_more": false
}
```

The example values are illustrative. `cover_image` is `null` when no image
exists. `next_cursor` is non-null only when another page is known to exist.
There is no exact total count, OFFSET, internal UUID, private storage key,
seller contact detail, or verification evidence in the response.

`newest` orders by `(published_at DESC, public_slug DESC)`; price sorts by
`(price, public_slug)` in the requested direction. All continuation predicates
are strict. Reuse a cursor with the same normalized query, filters, sort **and
limit**. Invalid/tampered/replayed cursors return generic HTTP 400. Invalid
query parameters return 422, oversized raw input 413, rate-limit failures 429
with `Retry-After`, and unavailable database/signing operations 503. Errors do
not echo untrusted values. Changing the cursor signing key intentionally
invalidates previously issued cursors; clients restart at page one.

Search uses MySQL `FULLTEXT(title, description) WITH PARSER ngram` in Boolean
mode, with server-added required terms. Each input word is an ngram phrase and
all words are required; results are sorted by the selected public sort, **not**
relevance. Chinese two-character terms, Arabic and Latin scripts are supported
without translation. One-character words, punctuation search, stemming,
linguistic synonyms, exact word boundaries and cross-language translation are
not supported. MySQL stopword behavior may exclude some words. The index is
not a semantic search engine. Search is evaluated in the same public-visibility
SQL query as every result and never reveals hidden listings in result/count or
cursor fields.

Each page is a new database read; keyset pagination is deterministic for stable
sort values but is **not** a cross-request snapshot. Publishing, pausing,
deactivation, price changes, or edits between pages may change membership or
ordering. Clients should restart pagination after changing filters or a
significant refresh.

Example: `GET /api/v1/products?q=桌子&city=qingdao&sort=price_asc&limit=24`.
