# ADR: MySQL ngram search and signed keyset browse pagination

Status: accepted for Phase 11B local implementation, pending independent audit
and target MySQL 8 performance verification.

## Context

The existing MySQL `product_listings` table has immutable public slugs,
`published_at`, exact DECIMAL prices, public city/category relations, and
private seller/media relations. Phase 11B must serve anonymous English,
Chinese, Arabic and French browsing without a new external search service.
The local database is MySQL 9.4; deployment target is MySQL 8.

## Decision

- Centralize eligibility in `publicly_visible()` SQL and use it from both
  detail/media and browse. This makes page limits/cursors count public rows,
  never hidden rows.
- Use an additive MySQL ngram full-text index on title and description.
  Normalize/bound Unicode input, reject punctuation/operators, and construct
  required Boolean terms server-side. This avoids natural-mode's union-of-
  bigrams false matches and supports CJK two-character terms. Search has no
  relevance sort in this phase.
- Use a single projected SQL query with joins and a correlated indexed cover
  lookup. `limit+1` avoids exact counts and N+1 queries.
- Use `(published_at, public_slug)` or `(price, public_slug)` keysets, with a
  versioned, HMAC-SHA256 cursor bound to normalized query/filter/sort/limit by
  a separately domain-tagged keyed context digest (not a guessable bare hash).
  Never encode an internal row ID. A dedicated shared signing key is required
  outside development; development derives a purpose-separated key from JWT
  configuration if not explicitly set.
- Use six ordering indexes (global newest/price plus city/category newest/price)
  and one full-text index. The measured optimizer selected pathological
  tiny-catalog-first plans at 20k rows; a global ordering index then took
  ~266ms to find one rare-category product. Product-side scalar slug lookups,
  `STRAIGHT_JOIN` and an index hint chosen from a fixed server-side allowlist
  made both common and rare filters indexed. Query plans must be rechecked on
  target MySQL 8 and different distributions; no optimizer hint substitutes
  for production workload profiling.

## Consequences and alternatives

MySQL ngram at token size 2 does not handle one-character searches and its
stopword/collation semantics are not language-aware. A bounded leading-wildcard
LIKE fallback was rejected for this phase because it adds O(N) scanning to
large catalogs. An external search engine, automatic translation, ranking
pipeline, denormalized search documents and snapshot cursor service are out of
scope. If measured search latency, multilingual relevance, or catalog scale
exceed this approach, evaluate an external index in a separately reviewed
phase with visibility-safe ingestion, deletion and consistency guarantees.

Local 20k-row synthetic testing demonstrated low-millisecond broad, common-
filter and rare-filter pages but roughly 0.7–0.8 second common-term full-text
pages; this is a
measured limitation, not a one-million-user capacity claim. Process-local
rate limiting also requires distributed enforcement before production.
