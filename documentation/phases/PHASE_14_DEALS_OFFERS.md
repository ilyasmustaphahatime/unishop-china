# Phase 14 — Deals & Offers Backend

Implementation report finalized 2026-11-08. Local implementation evidence, not
independent audit approval, Git closure or production certification.

## 1. Executive summary

**READY FOR INDEPENDENT FINAL AUDIT. Production ready: NO.**

Implemented private immutable proposals and accepted agreements using existing
conversation membership, product visibility, JWT authorization and transaction
conventions. Required local gates passed: 127 focused Phase 14 tests, 553 related
regressions, one full backend run (1,951 passed), three real-MySQL concurrency rounds,
real HTTP smoke, isolated migration round-trip, static checks and exact data cleanup.
No frontend feature, payment, notification or Phase 15 implementation.

The same implementation brief was reattached on 2026-11-08; existing work was
continued, not recreated. No staging, commit or push was performed.

## 2. Implemented architecture and business rules

Routes -> services -> repositories -> SQLAlchemy/MySQL. Existing deal placeholders
are reused. OfferService owns policy and commit; DealService provides private reads;
repositories never commit. No independent nested service transaction or new infrastructure.

Initial buyer offer -> recipient accept/reject/counter; proposer withdraws. Each
counter is an immutable linked child. States: PENDING, ACCEPTED, REJECTED, WITHDRAWN,
COUNTERED, EXPIRED, CANCELLED. All terminal states remain terminal. Each proposal
expires exactly24 hours after creation; equality is expired. Effective expiry is
projected read-only and filtered before pagination; replacing a pending slot
materializes expiry. Price follows the existing Decimal-string convention,
0.01..9999999999.99 CNY, exact DECIMAL(12,2), no invalid-input rounding.

One pending proposal per conversation and one agreement per product. Acceptance
atomically closes the winner, creates the deal, archives the product and closes
competing proposals. Title/condition are captured at acceptance; price resolves
through the accepted proposal. A deal is not payment, delivery or ownership transfer.

Full lifecycle and rationale: [ADR](../architecture/ADR_PHASE_14_OFFERS_DEALS.md).

## 3. Database schema and migration

Additive revision **e14f5a6b7c8d**, parent **d13e4f5a6b7c**. Historical revisions unchanged.

- offers: opaque ref, conversation/product composite FK, optional parent/conversation
  composite FK, immutable role/amount/currency/client UUID/creation/expiry, lifecycle
  closure and generated nullable active slot.
- Unique public ref, client key scoped to conversation/proposer, pending slot,
  non-null parent; CHECKs for money, role/root buyer, valid states, exact24h and
  consistent closure fields. Explicit composite unique FK targets.
- deals: opaque ref, unique accepted offer and unique product, matching composite
  FK, agreement timestamp and title/condition snapshots. No duplicate agreed price.
- RESTRICT history FKs. Added unique conversations(id,product_listing_id) target.
  Conversation/time, product/status and agreement/time indexes plus existing
  participant indexes support scoped lookups and bounded candidate lists.

Development migrated forward only. Actual development and disposable native server:
**MySQL9.4.0**, not an asserted MySQL8 certification.

## 4. API endpoints and OpenAPI status

All paths relative to /api/v1, bearer authenticated and participant scoped:

| Method/path | Result |
|---|---|
| POST /offers | 201 proposal / 200 identical retry |
| GET /offers | Private keyset page |
| GET /offers/{offer_ref} | Private proposal |
| POST /offers/{offer_ref}/counteroffers | 201 child / 200 identical retry |
| POST /offers/{offer_ref}/accept | 200 agreement, including retry |
| POST /offers/{offer_ref}/reject | 200 proposal |
| POST /offers/{offer_ref}/withdraw | 200 proposal |
| GET /deals | Private keyset page |
| GET /deals/{deal_ref} | Private agreement |

Verified nine authenticated operations, safe error models and opaque-reference
patterns. Updated the deliberate deals exclusion with an exact operation whitelist;
did not loosen privacy tests. Default20/max50, signed actor/purpose/filter/size/position
cursors. [Offers contract](../api/offers-api.md); [deals contract](../api/deals-api.md).

## 5. Security and concurrency controls

- Nonmembers404, wrong proposal role403; global roles cannot bypass membership.
- Active verified participants and canonical current seller/product eligibility
  for new commitments. Active participants retain history with inactive counterparties.
  Authorized rejection/withdrawal and identical outcome recovery remain possible.
- Sorted account locks -> product -> catalog/eligibility -> conversation -> proposal
  -> competing offers. Current locking reads for mutation outcomes avoid stale
  REPEATABLE READ snapshots. Bounded existing deadlock retry; one product-level
  unique deal as final guard; success only after commit.
- Transaction-neutral manual archive closure, no circular service dependency.
- Strict JSON, extra-field/duplicate-key rejection, 1,024-byte bodies, 1,200-byte
  queries, five-second body deadline, duplicate credential/origin rejection,
  bounded peer/account budgets, safe no-store errors and transport log suppression.
- Explicit projections omit internal UUIDs, storage/evidence/contact fields and
  other participants' negotiation terms. No automatic messages/consent/events.
- Initial race tests exposed stale-snapshot retry recovery; fixed and retained as
  regressions. Initial EXPLAIN exposed global history scans; participant-first
  indexed joins now pass three plan checks with300 synthetic offers. Final
  projection count is constant; heavy-user history sorting is a documented limit.

## 6. Exact test commands and results

Working directory: backend. PowerShell, existing .venv. No dependency installation.

Focused final suite — **127 passed**, one inherited TestClient warning:

~~~powershell
.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/unit/test_offer_contracts.py tests/unit/test_offer_security.py tests/integration/test_offer_routes.py tests/integration/test_offer_concurrency.py -q --tb=short
~~~

Relevant product/auth/chat regression — **553 passed**, one inherited warning:

~~~powershell
.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/unit/test_public_handles.py tests/unit/test_access_tokens.py tests/unit/test_login_authentication.py tests/unit/test_refresh_session_security.py tests/unit/test_chat_domain.py tests/unit/test_chat_security.py tests/unit/test_chat_websocket.py tests/integration/test_product_listings.py tests/integration/test_login_routes.py tests/integration/test_refresh_session_routes.py tests/integration/test_chat_routes.py tests/integration/test_chat_concurrency.py -q --tb=short
~~~

One consolidated full backend run — **1,951 passed**, zero failures/skips,
150.33 seconds, one existing Starlette TestClient/httpx deprecation warning:

~~~powershell
.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -q --tb=short
~~~

Real independent MySQL transactions, three isolated synthetic rounds:
**11/11, 11/11, 11/11 passed**, 1.92/2.43/2.44 seconds. Each test verifies complete
database fingerprints after scoped cleanup. Scenarios include create/counter
retries/conflicts, two buyers, duplicate accept, accept vs reject/withdraw/counter/
archive, and expiration while blocked on a product lock.

~~~powershell
1..3 | ForEach-Object {
  .venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/integration/test_offer_concurrency.py -q --tb=short
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
~~~

Live Uvicorn + MySQL — **PASS**, create/counter/accept/replay, competing cancellation,
role/BOLA/privacy, archived listing, retained chat history, no automatic message/
contact rows and exact full-data cleanup:

~~~powershell
.venv\Scripts\python.exe -B -m scripts.offers_http_checks --allow-development-synthetic-writes
~~~

Isolated native MySQL — **PASS**, base -> d13e4f5a6b7c -> e14f5a6b7c8d ->
d13e4f5a6b7c -> e14f5a6b7c8d, pre-existing data/schema preservation and no drift.
Fresh temporary datadir, separate random loopback port, ephemeral credentials,
owned server stopped and directory removed; development never downgraded.

~~~powershell
.venv\Scripts\python.exe -B -m scripts.offers_migration_checks --mysqld 'C:\Program Files\MySQL\MySQL Server 9.4\bin\mysqld.exe'
~~~

Static/environment/migration gates — **all PASS**:

~~~powershell
.venv\Scripts\python.exe -B -m ruff check --no-cache app alembic tests scripts
.venv\Scripts\python.exe -B -m pip check
.venv\Scripts\python.exe -B -m alembic current
.venv\Scripts\python.exe -B -m alembic heads
.venv\Scripts\python.exe -B -m alembic history
.venv\Scripts\python.exe -B -m alembic check
git diff --check
~~~

Current/head both e14f5a6b7c8d, one linear history, no new upgrade operations.
Python compilation — **376 source files PASS**, without bytecode writes:

~~~powershell
@'
from pathlib import Path
paths = sorted(p for folder in ('app','alembic','tests','scripts') for p in Path(folder).rglob('*.py'))
for path in paths:
    compile(path.read_bytes(), str(path), 'exec')
print(len(paths))
'@ | .venv\Scripts\python.exe -B -
~~~

OpenAPI generation plus strict private inventory/errors are tested in
test_public_handles.py and test_offer_routes.py. A separate generated-schema check
confirmed all nine Phase14 operations carry authentication. No frontend edits or
frontend tests were needed. No broad full-suite repeat was performed.

## 7. Database integrity evidence

All24 tables fingerprinted after tests and cleanup. All21 pre-existing application
data tables are byte-value identical to the original baseline; the22nd existing
table, alembic_version, has only the expected revision advance. All21 unaffected
prior schema hashes match; conversations changes only by the approved composite
unique key. New offers/deals tables are empty. No legitimate rows reset/reseeded.

The pre-existing application row counts and matching post-run SHA-256 digests follow.
Hashes are over sorted serialized full row values, not just counts.

| Table | Prior row count | Post-run digest / expected change |
|---|---:|---|
| admin_catalog_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| alembic_version | 1 | Expected revision advance |
| catalog_write_lock | 1 | 43de3a417d75f4818c5a553268b80ce3a5805109a3bbc6b605e9fb0b8f50b485 |
| categories | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| cities | 6 | ad2ed1eafd49ac32f110f092a6ac8061ab5c407831504316fd4496789c9feb4d |
| conversations | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| email_verification_codes | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| messages | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| password_reset_codes | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| phone_verification_codes | 3 | 8197760737495661900356aca2ac4efb6d45fb0c188693071dd6aaee593ef4f3 |
| product_favorites | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| product_images | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| product_listings | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| product_recent_views | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| refresh_tokens | 9 | 0ae052650e2cea6d98d27901342f85eee7a7033ad9bb1a12bd3557b871399e38 |
| seller_evidence | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| seller_verification_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| seller_verifications | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| user_profiles | 1 | c5d19ff87bc92218c23f5887086ddf295dc9655f969f4f20544f42e8d1e922b7 |
| user_roles | 4 | ec52899644779f82c0ade540defda2df2c1dd7dd6f0760097210ae7016587e0d |
| users | 4 | eeb0bfa7947a725cc10c0bdef5052796e8f855bb1509883f834ba73ec3a9115f |
| wechat_share_requests | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

No current evidence supports a claim of MySQL8 runtime compatibility from this
phase: native9.4 was the executed engine. The isolated script verifies real DDL,
rather than substituting SQLite or downgrading development.

## 8. Dependency audit status

Backend requirements.txt, requirements-dev.txt and pyproject.toml, plus frontend
package.json/package-lock.json, match recorded baseline SHA-256. No install,
uninstall, upgrade or dependency-resolution operation was performed. pip check:
No broken requirements found. Conditional dependency-audit reruns were not triggered.
Phase13 zero-advisory results remain historical evidence, not a new vulnerability
scan or a production-readiness claim. TLS/registry settings were not changed.

## 9. Complete changed-file manifest

**39 Phase14 paths:15 modified tracked +24 new**, all unstaged.
Unrelated LICENSE and postman/README.md are explicitly excluded.
No output/ or tmp/ path belongs to this manifest.

Modified tracked:

~~~text
backend/app/api/v1/deals/routes.py
backend/app/api/v1/router.py
backend/app/core/chat_logging.py
backend/app/main.py
backend/app/models/__init__.py
backend/app/models/conversation.py
backend/app/models/deal.py
backend/app/repositories/deal_repository.py
backend/app/schemas/deal.py
backend/app/services/deal_service.py
backend/app/services/product_service.py
backend/tests/conftest.py
backend/tests/unit/test_public_handles.py
documentation/CURRENT_PROJECT_STATUS.md
documentation/README.md
~~~

New:

~~~text
backend/alembic/versions/e14f5a6b7c8d_offers_deals.py
backend/app/api/offer_dependencies.py
backend/app/api/v1/offers/__init__.py
backend/app/api/v1/offers/routes.py
backend/app/common/offers.py
backend/app/core/offer_limits.py
backend/app/core/offer_security.py
backend/app/models/offer.py
backend/app/repositories/offer_repository.py
backend/app/schemas/offer.py
backend/app/services/offer_authorization.py
backend/app/services/offer_cursor.py
backend/app/services/offer_service.py
backend/scripts/offers_http_checks.py
backend/scripts/offers_migration_checks.py
backend/tests/fixtures/offers.py
backend/tests/integration/test_offer_concurrency.py
backend/tests/integration/test_offer_routes.py
backend/tests/unit/test_offer_contracts.py
backend/tests/unit/test_offer_security.py
documentation/api/deals-api.md
documentation/api/offers-api.md
documentation/architecture/ADR_PHASE_14_OFFERS_DEALS.md
documentation/phases/PHASE_14_DEALS_OFFERS.md
~~~

## 10. Known limitations and unresolved findings

No unresolved local Phase14 correctness/security/migration gate blocker was found.
Independent final audit is still required. Production ready remains **NO**.

- Single-process bounded rate limits and the inherited catalog guard serialize
  writes; they are not distributed quotas or demonstrated high-scale throughput.
- Participant-first queries avoid global history scans but can sort a large
  participant history. Pagination is non-snapshot across time/state changes.
- JWT access-token lifetime/logout behavior remains inherited. Provision signing
  material, production storage/secrets and deployed TLS/WSS privately.
- MySQL8, browser acceptance, full Docker/NGINX runtime and production load were not
  newly verified. Native9.4 disposable migration testing passed without Docker.
- P12-ARCH-LOW-01 and P12-AUDIT-OPENAPI-01 remain unresolved. The prior Phase13 LOW
  global-count/unfiltered-test-fixture observation remains; new fixtures are scoped.
- Frontend offers, payments, shipping, escrow, notifications, agreement cancellation,
  relisting, retention policy and Phase15 remain outside scope.
- One inherited TestClient deprecation warning; no dependency changes to silence it.

## 11. Git state and protected-file verification

Branch feature/authentication; HEAD unchanged:
0368378ae97601512fb7abfe10bbc3431d74d57e. Zero staged paths, zero deletions.
No staging/commit/push or Phase15 work. Source hashes checked against797 original
files: exactly the15 intended existing paths differ; no missing original file.
LICENSE and postman/README.md raw hashes match pre-implementation values despite
their pre-existing Git status flags.

All13 protected artifacts remain present, untracked, unstaged and SHA-256-identical:

| Protected path | SHA-256 |
|---|---|
| output/pdf/unishop-full-architecture-flow.pdf | F535B7703BA8962A6A37A34DD1E4F180D984E302A9EF0F13FF8E369B16B75278 |
| tmp/pdfs/build_unishop_architecture.py | 4DDA59ADC49DEA386F524393FE6302BE332133F0A4F72BED1DEABFD0CA4C3571 |
| tmp/pdfs/rendered/page-01.png | D9256564C46324898EBE7C901EACD45D9C93053A9886B571537266BDBC45F7B1 |
| tmp/pdfs/rendered/page-02.png | 7BE9E52C25EA8ABDA05B9E0B79F47BB4E2BD532A3BA840F5E2B4C81AA3D72F50 |
| tmp/pdfs/rendered/page-03.png | 97B51766023C5FA7AF1894D6C8CFE2C7D1F6258916F4FDD62DFAEF0A0D20A936 |
| tmp/pdfs/rendered/page-04.png | 1EA753CFDFE3EE00C7F4F2CD9579AE78B3B06F2F7C11B940ED4121F7EF5BFAE2 |
| tmp/pdfs/rendered/page-05.png | E16E7DF37300CE06798D044F8B87536C6EA5503EF312D7E549C685384CF32F8E |
| tmp/pdfs/rendered/page-06.png | D64019C131A5C04CB4BCF70EA91E160B0CBCAA2DCD0E3C82076F03083518C986 |
| tmp/pdfs/rendered/page-07.png | 5203FB5ADA9F691C68DAB165C2B74C0130827CCB50077C4931341033E05C6E62 |
| tmp/pdfs/rendered/page-08.png | 85FA0D00A9C78C2E4CF242696643A124DC245523E198467711CB158D29713032 |
| tmp/pdfs/rendered/page-09.png | C034B0C8D9BD10AB085BF5776FC6EEB5F285370D7E5A811E96048D57370CDF82 |
| tmp/pdfs/rendered/page-10.png | EF6B99542D8359C929E433F4DFEE9CF2D69A8C4B1EA567713854E99C7FC38B9D |
| tmp/pdfs/rendered/page-11.png | 95E1490B14E6B3B489FA9311EB7F8B2B3732C07D9436F392785EC13BCA66073E |

git diff --check passes. New Phase14 files are additionally checked as individual
no-index diffs because ordinary git diff does not inspect untracked files.
Line-ending conversion notices under existing Git configuration are not whitespace
errors; no line-ending settings were changed.

**READY FOR INDEPENDENT FINAL AUDIT**
