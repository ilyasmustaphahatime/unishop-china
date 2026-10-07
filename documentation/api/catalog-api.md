# Cities, categories and minimal admin API

Phase 8, verified 2026-10-07. Base: `/api/v1`. No products, listing permissions,
search, chat, orders or full admin dashboard are implemented by this phase.

## Public reads

| Method/path | Contract |
|---|---|
| `GET /cities` | `{ "items": [PublicCity] }`; active only |
| `GET /cities/{slug}` | One active `PublicCity`; otherwise generic 404 |
| `GET /categories` | `{ "items": [CategoryTree] }`; active roots with active children |
| `GET /categories/{slug}` | One `PublicCategory`; child hidden if parent inactive |

PublicCity fields: `slug`, `name_en`, `name_zh`, `province_en`, nullable
`province_zh`, `country_code` (`CN`). PublicCategory fields: `slug`, `name_en`,
`name_zh`, nullable `description`, nullable `parent_slug`. Root tree objects add
`children`, containing nonrecursive PublicCategory objects. Lists sort by
`sort_order`, then slug; ordering fields themselves are not public response data.
No database UUIDs, actor identifiers, audit metadata, credentials or storage keys.

## Administrator endpoints

Both `/admin/cities` and `/admin/categories` provide:

| Method/path suffix | Behavior |
|---|---|
| `GET` collection | Flat list including inactive resources; 200 |
| `POST` collection | Create an active resource; 201 |
| `PATCH /{slug}` | Update allowlisted metadata; 200 |
| `POST /{slug}/activate` | Strict empty JSON body `{}`; 200 |
| `POST /{slug}/deactivate` | Strict empty JSON body `{}`; 200 |

All require a valid Bearer access token, an ACTIVE account and the current MySQL
ADMIN role. Cookies, client state and claimed role/body fields confer no authority.
Role and account checks use current locking reads within the service transaction.
Revoked roles return 403; missing/invalid/inactive authentication returns 401.
No role-grant endpoint or admin user is created. Use an already authorized admin.

Admin responses add only `is_active` and `sort_order` to the public detail fields.
No DELETE endpoint, slug rename, client-specified internal ID or raw ORM output.

City create example:

```json
{
  "slug": "fuzhou",
  "name_en": "Fuzhou",
  "name_zh": "福州",
  "province_en": "Fujian",
  "province_zh": "福建",
  "country_code": "CN",
  "sort_order": 10
}
```

City patch permits only names, province names and sort order. Category create
accepts `slug`, `name_en`, `name_zh`, optional `description`, optional `parent_slug`
and `sort_order`. Category patch permits the same except immutable `slug`.
`parent_slug: null` makes a root. An active root is required as a parent, and a
category with children cannot become a child. Deactivate active children before
their parent; activate the parent before its children. No automatic cascade.
Duplicate slugs, capacity or hierarchy conflicts return generic 409; missing
resources return 404. Public inactive resources also return 404.

## Validation and limits

- Slugs are immutable, canonical lowercase ASCII, 2-63 characters, starting with
  a letter and using alphanumeric segments separated by one hyphen. Pattern:
  `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`. Uppercase is rejected, not silently normalized.
  Reserved public handles plus `city` and `category` are rejected. No UUID aliases,
  spaces, percent encoding, Unicode confusables, traversal, query or fragment syntax.
- Names/provinces: nonempty plain text, maximum 80 characters. Optional description:
  maximum 500. Controls, unsafe bidirectional/format characters and invalid Unicode
  are rejected. Render accepted content as text, never HTML. SQL-shaped text is
  inert data in parameterized SQLAlchemy statements.
- Sort order is a strict integer 0-10000 (not boolean). Extra fields, empty patches
  and null required fields return sanitized 422 without reflecting submitted values.
- Catalog capacities: 200 cities and 500 categories, including inactive rows.
  Category depth is exactly at most two levels; the database also enforces it.
- Actual-peer limits before JSON parsing: public 180/minute, admin 90/minute.
  Authenticated admin operations also share a 30/user/minute and 90/peer/minute
  budget. Forwarded headers do not choose the peer. 429 includes `Retry-After`.
  The authenticated catalog budget now uses the shared HTTP limiter algorithm;
  its 429 detail is "Too many catalog requests. Please try again later." instead
  of the former misleading profile wording. Status, budgets and header are unchanged.
- Admin POST/PATCH bodies are limited to 16 KiB of actual bytes and 15 seconds,
  including chunked requests; oversize returns 413, timeout 408. Percent-encoded
  catalog paths return 404. These are bounded process-local limits, not distributed.
- Private responses remain no-store. Database/audit errors return fixed 503 without
  SQL, payload or stack details. Successful writes and minimal audit events commit
  together; audit insertion or commit failure prevents success and rolls back data.

## Audit and integration

Internal `admin_catalog_audit` stores server-derived actor, action, type, public
resource slug, timestamp and only the names of changed fields. It does not store
raw bodies, credentials or private profile values, and has no public read API.
Actions are CITY_CREATED/UPDATED/ACTIVATED/DEACTIVATED and
CATEGORY_CREATED/UPDATED/REPARENTED/ACTIVATED/DEACTIVATED.

Profile `city` write values are these public slugs; see [profile API](profile-api.md).
Deactivation blocks new assignments, not historical profile display or completed
onboarding. The frontend shares public catalog queries (60-second stale time,
one retry), not private user/admin data. Server checks always override stale UI data.
`/categories` is a read-only directory, not a product listing page.

## Migration and operation

Run `python -m alembic upgrade head` from `backend` with its existing virtualenv
and local `.env`. Do not regenerate applied migrations. The chain is
`c7d8e9f0a1b2 -> d8e9f0a1b2c3 -> e8f0a1b2c3d4`.
The first migration refuses unknown old city labels before any MySQL DDL; resolve
such historical values deliberately rather than inventing a mapping. Six cities
are seeded once; categories start empty. The second migration closes SQL NULL
semantics for composite parent keys. Downgrade testing is disposable-database-only;
do not downgrade or reset the development database to rerun tests.

Production is not approved. See the [Phase 8 completion report](../phases/PHASE_8_CITIES_CATEGORIES_ADMIN_FOUNDATION.md)
for exact test evidence, dependency advisories and environment limitations.
