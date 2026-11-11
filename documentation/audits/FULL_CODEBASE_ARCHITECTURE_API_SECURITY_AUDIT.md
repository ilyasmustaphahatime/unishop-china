# UniShop China — Full Codebase Architecture, API and Security Audit

Audit dates: 10–11 November 2026 (Asia/Shanghai). Branch: `feature/authentication`.
Baseline: `9c66e1ac81c1531b6e13b4ff26f8d1200590cc86`.
Final application-code commit: `cc9f08043b9f35dbc1070681fbf4f9df98730870`. Final test-isolation commit: `e4df89008c4fb6994cf5d0a1595e4bf98c63fded`.

## A. Executive summary

**AUDIT PASSED — CODEBASE VERIFIED WITH DOCUMENTED LIMITATIONS**

**Production readiness: NO.** This is local regression and source-review evidence, not production certification or a claim that every branch is tested. No Phase 15 work, business features, framework migration, new infrastructure or development schema changes were introduced.

The modular monolith is viable and materially better verified after this audit. Confirmed corrections address expired ORM immutability, JSON ingress budgets, refresh/credential lock ordering, cross-origin browser session recovery, Unicode profile validation, dependency vulnerabilities, missing API error metadata and weak test isolation. All previously requested Phase 12/13 LOW observations are resolved with regression evidence. No unresolved CRITICAL/HIGH application finding was identified in the completed local scope.

The completed consolidated run passed **2,003 backend tests** and **405 frontend tests**. Subsequent narrow OpenAPI and identity-ingress corrections passed **215** and **305** targeted tests respectively. The final tree contains **2,015 collected backend cases**; do not misread that as a second full 2,015-case run. Three extra concurrency rounds passed **32/32/32**. Real Uvicorn/MySQL chat/WebSocket checks passed **175 assertions**, and the separate offers/deals HTTP workflow passed. MySQL remains connected, at one Alembic head with no drift. All 24 table count/content fingerprints and schema hashes match the starting baseline.

Python and both npm dependency audits now report zero known vulnerabilities. Dependency remediation did not upgrade Tailwind 3 to 4. Remaining release gates include private production media storage, production delivery providers/secrets, deployed HTTPS/WSS and reverse-proxy behavior, container runtime hardening, target-environment acceptance, fresh real-browser acceptance and operational/load/key-rotation testing.

### Evidence and inventory

The [machine-readable inventory](FULL_CODEBASE_AUDIT_INVENTORY.json) contains:

- 258 backend application Python modules, imports/responsibility docstrings and all 837 named function definitions.
- The first test observed entering 782 definitions; the other 55 are explicitly retained as unobserved, not silently treated as covered.
- 211 frontend TypeScript modules and 450 declarations/callbacks; this is an AST inventory, not frontend runtime coverage.
- Registered route handlers/dependency chains, generated OpenAPI, conditional development routes, 23 ORM tables with columns/constraints/indexes, and all 77 backend test-file counts.
- Before/after database hashes, the 13 protected artifact hashes and exact commit/path manifests. It contains no application rows, real credentials or private storage keys.

Baseline inventory covered 821 tracked/untracked files. `LICENSE` was already reported modified despite equal normalized content; the unrelated `postman/README.md` BOM change and 13 untracked PDF/rendering artifacts were preserved. They were never staged. Reviews combined automated inventories, high-risk manual code/contract inspection, existing regression tests and new negative/race tests. Parallel reviewers supplied partial findings before their execution limit; this report does not represent a separate external security certification.

## B. Architecture review

The actual design is a synchronous SQLAlchemy/MySQL modular monolith behind FastAPI, with a bounded asynchronous WebSocket transport. Services own transactions; repositories build queries and persist rows without independently committing. React uses feature API modules, Zod contracts, TanStack Query for server state and Zustand for in-memory authentication state.

| Boundary | Observations and action |
| --- | --- |
| Routes → dependencies/services | Routes handle transport, parse contracts and map safe errors. The health endpoint's direct liveness query is an intentional small exception. No new business workflow was moved into a route. |
| Services → repositories | Removed reverse imports from favorites, recent-history and browse repositories. Pagination position dataclasses now live in `backend/app/common/pagination.py`; explicit service re-exports preserve existing callers. |
| Transactions | Existing `commit_request_transaction`, `transaction` and bounded whole-transaction deadlock retry retained. No generic repository/unit-of-work framework added. |
| Cross-module authorization | Product visibility predicates, active-user locks and conversation membership remain shared. Offers reuse conversation participants/product eligibility rather than inventing seller/buyer identity from request fields. |
| Real time | Socket parsing and queues stay in the transport/manager. Message persistence and authorization remain service-owned; sessions do not cross asynchronous awaits. |
| Frontend state | Tokens stay in memory; refresh is coordinated; private query caches are cleared on session change. Logout-all now obtains revocation-only authority once if the old bearer expires. |
| Startup/shutdown | Runtime settings are validated, optional loopback-only development inboxes are explicitly registered, and the chat manager is shut down at application exit. No new background worker introduced. |

Architecture regressions now reject repository imports of service/API layers. Searches found no repository commit/rollback calls or service imports of route modules. Imports and startup passed the full suite; this is not a mathematical proof of the absence of every dynamic cycle. Offer/deal service interaction remains narrow and intentional.

`auth/dependencies.py` (~717 lines), `auth/routes.py` (~542), configuration (~452), email verification (~353) and password reset (~330) remain larger modules. Their distinct security policies were not merged into generic abstractions merely to reduce line count. Service authorization helpers still perform some direct SQL for coordinated locks; extracting each query into another wrapper would not improve the demonstrated safety boundary.

## C. Code quality review

Confirmed boundary duplication was removed from pagination type ownership, not from different business policies. Error-shape documentation reuses `SafeErrorResponse`. The existing JSON ingress guard now covers authentication, profile, development-inbox and non-upload seller identity JSON; multipart evidence keeps its dedicated guard. Seller peer budgets run outside that JSON parser so malformed input still consumes the stricter existing budget.

Chat tests no longer use unscoped table counts/updates/selects; every test runs alongside unrelated synthetic conversation/message/consent rows and asserts those rows are unchanged. The refresh/reset race tests no longer accept a deadlock-induced credential-change failure as a successful result.

No functional module was deleted. Automated inventory found 67 explicit backend placeholder modules and 79 short frontend scaffold candidates. These include deferred features and should not be confused with registered implementations. Dynamic routes, dependency injection, model registration and compatibility re-exports were considered before deciding to preserve scaffolding. No unreferenced-symbol bulk deletion, speculative memoization, UI redesign or broad formatting was performed.

The root README had materially stale Phase 10/11 status, migration head and dependency claims. It is aligned with the verified Phase 14 backend state and links this audit; dated historical phase reports remain historical rather than being rewritten.

## D. API audit

The current local configuration registers **86 OpenAPI HTTP operations**, **one WebSocket route**, and **four framework documentation endpoints** (each also serves HEAD). Four additional fake password-reset/email operations appear only when their development flags/providers are enabled; these were inventoried separately. No route was added by this audit.

Every REST operation now has a documented safe fallback error shape; explicit existing per-status models override it. Safe 422 metadata does not expose submitted values. Database health's existing non-`detail` 503 body and private evidence JPEG/PNG success bytes are documented explicitly. Cookie/CSRF and socket authentication are explained below rather than falsely classified as anonymous merely because they are not HTTP Bearer operations in OpenAPI.

In the table, **PASS** means the listed family’s automated contract/behavior checks passed, not that every branch of that endpoint was executed. Schema names refer to the full definitions in the inventory and `backend/app/schemas/`. `default error` means `SafeErrorResponse`; `args` are bounded path/query/header parameters whose exact constraints are recorded in OpenAPI.

| Endpoint | Authentication / authorization | Validation | Response contract | Tests / result |
| --- | --- | --- | --- | --- |
| `POST /api/v1/offers` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | OfferCreate | 200 OfferResponse; 201 OfferResponse; default error | OFFERS: PASS |
| `GET /api/v1/offers` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | no body; args: limit, cursor, conversation_ref, role, status | 200 OfferPage; default error | OFFERS: PASS |
| `GET /api/v1/offers/{offer_ref}` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | no body; args: offer_ref | 200 OfferResponse; default error | OFFERS: PASS |
| `POST /api/v1/offers/{offer_ref}/counteroffers` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | CounterOffer; args: offer_ref | 200 OfferResponse; 201 OfferResponse; default error | OFFERS: PASS |
| `POST /api/v1/offers/{offer_ref}/accept` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | no body; args: offer_ref | 200 DealResponse; default error | OFFERS: PASS |
| `POST /api/v1/offers/{offer_ref}/reject` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | no body; args: offer_ref | 200 OfferResponse; default error | OFFERS: PASS |
| `POST /api/v1/offers/{offer_ref}/withdraw` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | no body; args: offer_ref | 200 OfferResponse; default error | OFFERS: PASS |
| `GET /api/v1/deals` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | no body; args: limit, cursor, conversation_ref, role | 200 DealPage; default error | OFFERS: PASS |
| `GET /api/v1/deals/{deal_ref}` | Bearer; conversation member; proposer/recipient action rules; current trading eligibility | no body; args: deal_ref | 200 DealResponse; default error | OFFERS: PASS |
| `POST /api/v1/chat/conversations` | Bearer; conversation member; active-account rechecks | ConversationCreate | 200 ConversationResponse; default error | CHAT: PASS |
| `GET /api/v1/chat/conversations` | Bearer; conversation member; active-account rechecks | no body; args: limit, cursor | 200 ConversationPage; default error | CHAT: PASS |
| `GET /api/v1/chat/conversations/{conversation_ref}` | Bearer; conversation member; active-account rechecks | no body; args: conversation_ref | 200 ConversationResponse; default error | CHAT: PASS |
| `GET /api/v1/chat/conversations/{conversation_ref}/messages` | Bearer; conversation member; active-account rechecks | no body; args: conversation_ref, limit, cursor | 200 MessagePage; default error | CHAT: PASS |
| `GET /api/v1/chat/conversations/{conversation_ref}/wechat` | Bearer; conversation member; buyer requests, seller decides/revokes; private approved read | no body; args: conversation_ref | 200 HandoffResponse; default error | WECHAT: PASS |
| `POST /api/v1/chat/conversations/{conversation_ref}/wechat/request` | Bearer; conversation member; buyer requests, seller decides/revokes; private approved read | no body; args: conversation_ref | 200 HandoffResponse; default error | WECHAT: PASS |
| `POST /api/v1/chat/conversations/{conversation_ref}/wechat/approve` | Bearer; conversation member; buyer requests, seller decides/revokes; private approved read | WeChatApproval; args: conversation_ref | 200 HandoffResponse; default error | WECHAT: PASS |
| `POST /api/v1/chat/conversations/{conversation_ref}/wechat/deny` | Bearer; conversation member; buyer requests, seller decides/revokes; private approved read | no body; args: conversation_ref | 200 HandoffResponse; default error | WECHAT: PASS |
| `POST /api/v1/chat/conversations/{conversation_ref}/wechat/revoke` | Bearer; conversation member; buyer requests, seller decides/revokes; private approved read | no body; args: conversation_ref | 200 HandoffResponse; default error | WECHAT: PASS |
| `GET /api/v1/me/favorites` | Bearer; current user only; current public visibility, scoped cursor | no body; args: limit, cursor | 200 FavoritesPage; default error | PERSONAL: PASS |
| `POST /api/v1/me/favorites/lookup` | Bearer; current user only; current public visibility, scoped cursor | FavoriteLookupRequest | 200 FavoritesLookupResponse; default error | PERSONAL: PASS |
| `PUT /api/v1/me/favorites/{slug}` | Bearer; current user only; current public visibility, scoped cursor | no body; args: slug | 200 FavoriteStatus; default error | PERSONAL: PASS |
| `DELETE /api/v1/me/favorites/{slug}` | Bearer; current user only; current public visibility, scoped cursor | no body; args: slug | 204 empty; default error | PERSONAL: PASS |
| `GET /api/v1/me/recently-viewed` | Bearer; current user only; current public visibility, scoped cursor | no body; args: limit, cursor | 200 RecentlyViewedPage; default error | PERSONAL: PASS |
| `DELETE /api/v1/me/recently-viewed` | Bearer; current user only; current public visibility, scoped cursor | no body | 204 empty; default error | PERSONAL: PASS |
| `POST /api/v1/me/recently-viewed/{slug}` | Bearer; current user only; current public visibility, scoped cursor | no body; args: slug | 204 empty; default error | PERSONAL: PASS |
| `DELETE /api/v1/me/recently-viewed/{slug}` | Bearer; current user only; current public visibility, scoped cursor | no body; args: slug | 204 empty; default error | PERSONAL: PASS |
| `GET /api/v1/products` | Public / credential proof; public active/eligible listings; allowlisted filters/order and signed cursor | no body; args: q, city, category, min_price, max_price, condition, sort, limit, cursor | 200 ProductBrowsePage; default error | SEARCH: PASS |
| `GET /api/v1/products/{slug}` | Public / credential proof; public visibility or current seller ownership/eligibility | no body; args: slug | 200 PublicProduct; default error | PRODUCT: PASS |
| `POST /api/v1/seller/products` | Bearer; public visibility or current seller ownership/eligibility | ProductCreate | 201 OwnProduct; default error | PRODUCT: PASS |
| `GET /api/v1/seller/products` | Bearer; public visibility or current seller ownership/eligibility | no body; args: limit, offset | 200 OwnProductList; default error | PRODUCT: PASS |
| `GET /api/v1/seller/products/{slug}` | Bearer; public visibility or current seller ownership/eligibility | no body; args: slug | 200 OwnProduct; default error | PRODUCT: PASS |
| `PATCH /api/v1/seller/products/{slug}` | Bearer; public visibility or current seller ownership/eligibility | ProductUpdate; args: slug | 200 OwnProduct; default error | PRODUCT: PASS |
| `POST /api/v1/seller/products/{slug}/publish` | Bearer; public visibility or current seller ownership/eligibility | StrictBody; args: slug | 200 OwnProduct; default error | PRODUCT: PASS |
| `POST /api/v1/seller/products/{slug}/pause` | Bearer; public visibility or current seller ownership/eligibility | StrictBody; args: slug | 200 OwnProduct; default error | PRODUCT: PASS |
| `POST /api/v1/seller/products/{slug}/archive` | Bearer; public visibility or current seller ownership/eligibility | StrictBody; args: slug | 200 OwnProduct; default error | PRODUCT: PASS |
| `GET /api/v1/products/{slug}/images/{image_ref}` | Public / credential proof; current public visibility or listing owner; private storage namespace | no body; args: slug, image_ref | 200 image/jpeg/image/png/image/webp; default error | MEDIA: PASS |
| `POST /api/v1/seller/products/{slug}/images` | Bearer; current public visibility or listing owner; private storage namespace | bounded multipart; args: slug | 201 OwnProductImage; default error | MEDIA: PASS |
| `GET /api/v1/seller/products/{slug}/images` | Bearer; current public visibility or listing owner; private storage namespace | no body; args: slug | 200 list<OwnProductImage>; default error | MEDIA: PASS |
| `PATCH /api/v1/seller/products/{slug}/images/order` | Bearer; current public visibility or listing owner; private storage namespace | ProductImageOrder; args: slug | 200 list<OwnProductImage>; default error | MEDIA: PASS |
| `DELETE /api/v1/seller/products/{slug}/images/{image_ref}` | Bearer; current public visibility or listing owner; private storage namespace | no body; args: slug, image_ref | 204 empty; default error | MEDIA: PASS |
| `GET /api/v1/seller/products/{slug}/images/{image_ref}` | Bearer; current public visibility or listing owner; private storage namespace | no body; args: slug, image_ref | 200 image/jpeg/image/png/image/webp; default error | MEDIA: PASS |
| `GET /api/v1/cities` | Public / credential proof; public active catalog; admin-only mutations with transactional audit | no body | 200 CityList; default error | CATALOG: PASS |
| `GET /api/v1/cities/{slug}` | Public / credential proof; public active catalog; admin-only mutations with transactional audit | no body; args: slug | 200 PublicCity; default error | CATALOG: PASS |
| `GET /api/v1/categories` | Public / credential proof; public active catalog; admin-only mutations with transactional audit | no body | 200 CategoryList; default error | CATALOG: PASS |
| `GET /api/v1/categories/{slug}` | Public / credential proof; public active catalog; admin-only mutations with transactional audit | no body; args: slug | 200 PublicCategory; default error | CATALOG: PASS |
| `GET /api/v1/admin/cities` | Bearer; public active catalog; admin-only mutations with transactional audit | no body | 200 list<AdminCity>; default error | CATALOG: PASS |
| `POST /api/v1/admin/cities` | Bearer; public active catalog; admin-only mutations with transactional audit | CityCreate | 201 AdminCity; default error | CATALOG: PASS |
| `PATCH /api/v1/admin/cities/{slug}` | Bearer; public active catalog; admin-only mutations with transactional audit | CityUpdate; args: slug | 200 AdminCity; default error | CATALOG: PASS |
| `POST /api/v1/admin/cities/{slug}/activate` | Bearer; public active catalog; admin-only mutations with transactional audit | StrictBody; args: slug | 200 AdminCity; default error | CATALOG: PASS |
| `POST /api/v1/admin/cities/{slug}/deactivate` | Bearer; public active catalog; admin-only mutations with transactional audit | StrictBody; args: slug | 200 AdminCity; default error | CATALOG: PASS |
| `GET /api/v1/admin/categories` | Bearer; public active catalog; admin-only mutations with transactional audit | no body | 200 list<AdminCategory>; default error | CATALOG: PASS |
| `POST /api/v1/admin/categories` | Bearer; public active catalog; admin-only mutations with transactional audit | CategoryCreate | 201 AdminCategory; default error | CATALOG: PASS |
| `PATCH /api/v1/admin/categories/{slug}` | Bearer; public active catalog; admin-only mutations with transactional audit | CategoryUpdate; args: slug | 200 AdminCategory; default error | CATALOG: PASS |
| `POST /api/v1/admin/categories/{slug}/activate` | Bearer; public active catalog; admin-only mutations with transactional audit | StrictBody; args: slug | 200 AdminCategory; default error | CATALOG: PASS |
| `POST /api/v1/admin/categories/{slug}/deactivate` | Bearer; public active catalog; admin-only mutations with transactional audit | StrictBody; args: slug | 200 AdminCategory; default error | CATALOG: PASS |
| `POST /api/v1/auth/email/resend-code` | Bearer; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | ResendEmailVerificationCodeRequest | 202 ResendEmailVerificationCodeResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/email/verify` | Bearer; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | VerifyEmailCodeRequest | 200 VerifyEmailCodeResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/password/forgot` | Public / credential proof; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | ForgotPasswordRequest | 202 ForgotPasswordResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/password/reset` | Public / credential proof; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | ResetPasswordRequest | 200 ResetPasswordResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/password/change` | Bearer; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | ChangePasswordRequest | 200 ChangePasswordResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/login` | Public / credential proof; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | LoginRequest | 200 LoginResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/refresh` | Cookie + CSRF; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | no body | 200 RefreshResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/logout` | Cookie + CSRF; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | no body | 204 empty; default error | AUTH: PASS |
| `POST /api/v1/auth/logout-all` | Bearer; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | no body | 204 empty; default error | AUTH: PASS |
| `GET /api/v1/auth/me` | Bearer; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | no body | 200 SafeAuthenticatedUserResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/register` | Public / credential proof; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | RegisterRequest | 201 RegisterResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/phone/resend-code` | Public / credential proof; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | ResendPhoneVerificationCodeRequest | 202 ResendPhoneVerificationCodeResponse; default error | AUTH: PASS |
| `POST /api/v1/auth/phone/verify` | Public / credential proof; active account or code/credential-bound account; refresh/logout use cookie+CSRF+Origin | VerifyPhoneCodeRequest | 200 VerifyPhoneCodeResponse; default error | AUTH: PASS |
| `GET /api/v1/profile/me` | Bearer; current user for writes/own profile; public safe handle projection only | no body | 200 OwnProfileResponse; default error | PROFILE: PASS |
| `PATCH /api/v1/profile/me` | Bearer; current user for writes/own profile; public safe handle projection only | ProfileUpdateRequest | 200 OwnProfileResponse; default error | PROFILE: PASS |
| `POST /api/v1/profile/onboarding/complete` | Bearer; current user for writes/own profile; public safe handle projection only | OnboardingCompleteRequest | 200 OwnProfileResponse; default error | PROFILE: PASS |
| `GET /api/v1/profiles/by-handle/{handle}` | Public / credential proof; current user for writes/own profile; public safe handle projection only | no body; args: handle | 200 PublicProfileResponse; default error | PROFILE: PASS |
| `POST /api/v1/seller-verification` | Bearer; current owner or administrator; ticket bound to authorized evidence read | StartOrSubmitRequest | 200 VerificationResponse; default error | SELLER: PASS |
| `GET /api/v1/seller-verification/me` | Bearer; current owner or administrator; ticket bound to authorized evidence read | no body | 200 VerificationResponse / null; default error | SELLER: PASS |
| `POST /api/v1/seller-verification/evidence` | Bearer; current owner or administrator; ticket bound to authorized evidence read | bounded multipart | 200 VerificationResponse; default error | SELLER: PASS |
| `POST /api/v1/seller-verification/evidence/access` | Bearer; current owner or administrator; ticket bound to authorized evidence read | EvidenceAccessRequest | 200 SignedEvidenceResponse; default error | SELLER: PASS |
| `GET /api/v1/seller-verification/evidence/content` | Bearer; current owner or administrator; ticket bound to authorized evidence read | no body; args: X-Evidence-Ticket | 200 image/jpeg/image/png; default error | SELLER: PASS |
| `GET /api/v1/admin/seller-verifications` | Bearer; current owner or administrator; ticket bound to authorized evidence read | no body; args: offset | 200 list<VerificationResponse>; default error | SELLER: PASS |
| `POST /api/v1/admin/seller-verifications/{id}/approve` | Bearer; current owner or administrator; ticket bound to authorized evidence read | ReviewRequest; args: id | 200 VerificationResponse; default error | SELLER: PASS |
| `POST /api/v1/admin/seller-verifications/{id}/reject` | Bearer; current owner or administrator; ticket bound to authorized evidence read | RejectRequest; args: id | 200 VerificationResponse; default error | SELLER: PASS |
| `GET /api/v1/health` | Public / credential proof; public safe liveness/availability only | no body | 200 object; default error | HEALTH: PASS |
| `GET /api/v1/health/database` | Public / credential proof; public safe liveness/availability only | no body | 200 object; default error | HEALTH: PASS |
| `POST /api/v1/dev/fake-sms/latest` | Loopback; loopback development only; provider/flag checks; never production | FakeSmsLookupRequest | 200 DevelopmentFakeSmsResponse; default error | DEV: PASS |
| `POST /api/v1/dev/fake-sms/consume` | Loopback; loopback development only; provider/flag checks; never production | ConsumeFakeMessageRequest | 204 empty; default error | DEV: PASS |
| `GET /` | Public / credential proof; public safe liveness/availability only | no body | 200 object; default error | HEALTH: PASS |
| `GET /health` | Public / credential proof; public safe liveness/availability only | no body | 200 object; default error | HEALTH: PASS |

### WebSocket, conditional and framework endpoints

| Endpoint | Authentication/authorization and contract | Verification |
| --- | --- | --- |
| `WS /api/v1/chat/ws` | Exact trusted Origin; no token in URL/subprotocol/Authorization header; first frame authenticates within 5 seconds; strict versioned events, 16 KiB frames, participant-only subscriptions/writes and delivery-time rechecks | 63 socket unit cases, MySQL message/idempotency tests, 175 real HTTP/WS checks: PASS |
| `POST /api/v1/dev/fake-password-reset/latest` (conditional) | Loopback-only fake delivery, explicit development flag/provider; typed lookup/consume body; safe error fallback | Development provider/route negative tests; not enabled in normal local snapshot |
| `POST /api/v1/dev/fake-password-reset/consume` (conditional) | Loopback-only fake delivery, explicit development flag/provider; typed lookup/consume body; safe error fallback | Development provider/route negative tests; not enabled in normal local snapshot |
| `GET /api/v1/dev/fake-email/latest` (conditional) | Loopback-only fake delivery, explicit development flag/provider; typed lookup/consume body; safe error fallback | Development provider/route negative tests; not enabled in normal local snapshot |
| `POST /api/v1/dev/fake-email/consume` (conditional) | Loopback-only fake delivery, explicit development flag/provider; typed lookup/consume body; safe error fallback | Development provider/route negative tests; not enabled in normal local snapshot |
| `GET/HEAD /openapi.json` | Framework documentation, no business mutation; public by current configuration | Route inventory/source check; not separate business endpoint coverage |
| `GET/HEAD /docs` | Framework documentation, no business mutation; public by current configuration | Route inventory/source check; not separate business endpoint coverage |
| `GET/HEAD /docs/oauth2-redirect` | Framework documentation, no business mutation; public by current configuration | Route inventory/source check; not separate business endpoint coverage |
| `GET/HEAD /redoc` | Framework documentation, no business mutation; public by current configuration | Route inventory/source check; not separate business endpoint coverage |

### Cross-cutting API behavior

Private auth/profile/seller/personalization/chat/offer/deal responses have no-store behavior; private images/evidence add appropriate binary and content-protection headers. BOLA returns safe missing-resource responses where intended; an authenticated participant with the wrong action role may receive 403. Own-account IDs and internal administrator review references are intentional existing contracts, not public user-directory disclosure.

Browse, personalization, chat and offer/deal lists are bounded and use signed/scoped keysets. Public catalog returns the intentionally small catalog. Favorites and history serialize per-user limits (500 favorites, 100 recent views); reads do not silently record viewing. Message and offer client identifiers are scoped for idempotency, not globally reusable authority. Identical authorized replay returns existing results; conflicting reuse fails. Offer acceptance creates one agreement, archives its product and cancels competitors atomically. Expiration is effective/lazy; no background scheduler was invented.

Identity JSON now has a 16 KiB actual-byte bound, 5-second input deadline and a bounded peer budget before parsing. Existing stricter operation/account budgets remain. Product/catalog/media/chat/offer boundaries retain their domain-specific sizes and budgets. Duplicate identity JSON fields and non-finite constants are rejected. Duplicate-field policy is not uniform across every legacy catalog/listing parser; typed final values remain validated and this is recorded as LOW consistency debt, not a demonstrated authorization bypass.

**Test-family key:** AUTH: authentication/login/refresh/password/phone/email routes, token/CSRF/rate-limit/security tests. PROFILE: profile routes, models, snapshot/concurrency, public handles and validators. SELLER: verification, challenge/public privacy, evidence access, storage and concurrency. CATALOG: catalog API/concurrency/authorization. PRODUCT: listing, route, adversarial and concurrency tests. MEDIA: images, decoder/path/privacy/compensation and race tests. SEARCH: browse/cursor/index tests. PERSONAL: favorites/history services/routes/cursor tests. CHAT/WECHAT: chat routes/domain/security/socket/concurrency and live scripts. OFFERS: offer routes/contracts/security/concurrency and live workflow. DEV: fake-delivery registration/loopback/production-disable tests. HEALTH: fresh real Uvicorn GETs and outage contract test. Exact files and collected case counts are in section H's inventory.

## E. Database and transaction audit

The live local server is MySQL **9.4.0** using SQLAlchemy/PyMySQL, `pool_pre_ping=True`, bounded pool sizing and one reusable session dependency. Alembic and application settings share the validated database URL. No credentials were printed or edited.

`alembic current` and `heads`: **e14f5a6b7c8d**, sole head. History is linear through 16 revisions. `alembic check`: **No new upgrade operations detected**. No new migration was required; no applied migration was rewritten and the development database was never downgraded.

| Persistence area | Verified invariants and representative constraints |
| --- | --- |
| Users/roles/profiles | Unique login identifiers, per-user role uniqueness, one profile/user, bounded Unicode fields, unique public handle and city FK. Internal user IDs remain necessary private joins. |
| Verification/reset/refresh | Hashed codes/tokens, attempt/expiry bounds, family/replacement linkage, credential changes revoke existing sessions inside the service transaction. User locks now precede refresh locks consistently. |
| Catalog | Unique slugs, country/sort bounds, two-level category parent composite FK and NULL-completeness check, singleton mutation lock, administrator audit rows. |
| Listings | Immutable seller/slug, exact numeric price, currency/status/condition/publication checks; seller/city/category FKs and browse/owner composite indexes. |
| Product media | Unique public reference/storage key/listing-position, FK to listing, dimensions/pixel/size/MIME constraints. Compensation on failed metadata commit; failed physical cleanup never restores public metadata. |
| Seller evidence | One evidence type/attempt, unique private storage reference, size/MIME constraints, active-attempt uniqueness and review/audit linkage. Evidence access commits its audit before returning bytes. |
| Favorites/history | User/listing composite primary keys, FKs and user/time keyset indexes; current visibility before page selection, row-level user serialization for limits/pruning. |
| Chat | Distinct buyer/seller, unique participant-product conversation, activity indexes; message client-id uniqueness per conversation/sender, bounded content and history index. |
| WeChat | One consent record/conversation; constrained terminal states and timestamps; ciphertext present only in the approved state. Revocation removes stored contact bytes. |
| Offers/deals | Composite parent/conversation and offer/product FKs; one pending slot/conversation, one child/parent, unique replay identity, decimal money/date/closure checks, unique agreement/product and accepted offer. |

The inventory provides exact column types, nullability, constraint names and indexes for all 23 registered ORM tables; `alembic_version` makes 24 live tables. Unimplemented model stubs are not reported as live schema.

**Concurrency correction:** refresh previously locked a token before its user while password reset/change locked the user first. That allowed deadlock-induced credential-operation failure; existing tests tolerated it. All affected refresh/logout writers now lock User → RefreshToken and re-read current state. Active-family counting uses a locking current read rather than the pre-lock repeatable-read snapshot. Deterministic NOWAIT probes prove a blocked account writer does not already hold the refresh row. Race assertions require the password operation to succeed, not merely leave a recoverable database.

Offers preserve sorted participant User → product → catalog eligibility guard → conversation → offer ordering. The accepted agreement, archival and competing offer closure share one transaction. Limited InnoDB 1213 retries wrap whole rolled-back operations, not partial writes or external effects. Tests exercise commit/rollback failure and conflicting concurrent transitions.

The inherited browse migration test initially used a uniquely named disposable **table** inside the development database; the full suite ran that existing test. No pre-existing table was downgraded or changed, and exact data/schema hashes remained equal, but table-only isolation did not meet this brief's separate-database requirement. The test is now corrected to use the existing temporary native MySQL server harness, a fresh datadir and random non-development port. Only that isolated server receives metadata creation and index upgrade/downgrade/re-upgrade. The corrected probe plus architecture/foundation checks passed **7 tests**, followed by another exact development fingerprint check. Set `UNISHOP_TEST_MYSQLD` to the installed Windows server binary when automatic discovery is unavailable; absence fails explicitly rather than silently skipping. A fresh whole-history Alembic cycle was not run because no migration changed. Earlier phase MySQL 8 whole-history round-trips remain historical evidence.

All 24 pre-existing table counts, canonical row hashes and SHOW CREATE TABLE hashes match the initial baseline after tests/live cleanup. The report-only product-media audit returned **0 metadata rows, no issues**; this verifies current emptiness, not a populated production bucket. Synthetic fixtures exercise actual media compensation separately.

Pagination queries use existing indexes/joins and bounded projected cards; no new N+1 regression was identified in tested paths. Large-data benchmark scripts were inspected, not rerun as a production performance certification. Deep search/selectivity, catalog singleton lock contention and actual deployment volume remain load-test obligations.

## F. Security audit

### Fixed findings

Severity describes impact in the applicable environment; dependency advisory severity is distinguished from demonstrated application reachability. The following are closed by the listed changes and verification.

| ID / severity | File and line / evidence | Impact, correction and verification | Final status |
| --- | --- | --- | --- |
| AUD-DEP-01 **HIGH** | `backend/requirements.txt:8`; installed dnspython 2.8.0 reported CVE-2026-114605 / GHSA-45c3-73f7-pv4m | Malicious DNS processing resource-exhaustion advisory in the email-validation dependency chain. Pin/install 2.9.0; full backend tests, pip check and fresh pip-audit pass. Current request validators do not establish arbitrary DNS reachability; advisory removal is defense in depth. | FIXED |
| AUD-DEP-02 **HIGH** | `backend/requirements-dev.txt:9`; msgpack 1.2.1, CVE-2026-114613 / GHSA-j586-36cw-2gc2 | Dependency advisory in the pip-audit/CacheControl development-tool chain, not a claimed user-controlled app deserialization endpoint. Pin/install 1.2.3; full backend compatibility and audit pass. | FIXED |
| AUD-DEP-03 **MEDIUM** | `frontend/package.json:46`; minimatch 10.2.5, CVE-2026-118764 / GHSA-g3hv-75wg-m249 | Build-tool matching resource-exhaustion advisory, ten affected audit nodes from one root advisory. Override 11.0.1, clean npm ci, installed-tree check, 405 tests/TS/ESLint/build and both audits pass. Tailwind unchanged. | FIXED |
| AUD-IN-01 **MEDIUM** | `backend/app/core/auth_request_security.py:28`; malformed identity JSON bypassed dependency limits/actual-byte controls | Pre-parser bounded bytes/deadline/peer rate; duplicates/non-finite constants rejected; profile/development/non-upload seller JSON included. Multipart remains separately bounded. Seller limit order preserved. 25 initial negative tests, eight added cases and 305 follow-up cases pass. | FIXED |
| AUD-TX-01 **MEDIUM** | `backend/app/services/refresh_session_service.py:236`, `repositories/token_repository.py:56` | Reversed locks and stale family-count snapshot could fail credential changes or miscount sessions. User-first locking/current reads; 108 focused auth tests, deterministic four-case probe and three 32-case race rounds pass. | FIXED |
| AUD-UI-01 **MEDIUM** | `frontend/src/features/auth/session.ts:51`, `services/apiClient.ts:41`, `backend/app/main.py` CORS configuration | Expired access bearer prevented logout-all although a refresh session remained valid; cross-origin JS could not read WWW-Authenticate. One bounded recovery solely to revoke, no auth restoration, session-version guards; expose only challenge/backoff headers. Six new negative/recovery tests, focused 61 frontend and 111 backend tests, full frontend suite and live CORS check pass. | FIXED |
| AUD-ORM-01 **LOW** / P14-AUDIT-LOW-01 | `backend/app/models/offer.py:69`, `models/deal.py:36` | Expired/deferred ORM fields bypassed the prior in-dict immutable guard. Persisted unloaded assignments now rejected. Seventeen new loaded/expired/deferred/detached/same-value regressions; 144 focused tests pass. No API previously exposed these assignments; raw SQL/bulk ORM escape hatch remains documented. | FIXED |
| AUD-UI-02 **LOW** | `frontend/src/features/profiles/schemas.ts:18`, `components/profiles/ProfileForm.tsx:60` | UTF-16 client limits disagreed with Unicode codepoints/NFC on server; controls/surrogates mismatch. Normalize/count codepoints, reject unsafe controls and align bio counter. Nine new tests; 27 focused profile tests and full frontend suite pass. | FIXED |
| P12-ARCH-LOW-01 **LOW** | `backend/app/common/pagination.py:8`; favorites/recent/browse repository imports | Reverse service-type coupling moved to common layer, compatible re-exports retained; AST layering regression plus 212 tests pass. | FIXED |
| P12-AUDIT-OPENAPI-01 **LOW** / AUD-API-01 | `backend/app/api/v1/me/dependencies.py`, `app/main.py:122`, `api/v1/router.py`, seller evidence route | Missing errors/default validation model and binary/health metadata. Shared safe schema, explicit existing health 503 and evidence success types. 163 initial tests and 215 metadata follow-ups pass; no request/success-payload changes. | FIXED |
| P13-AUDIT-LOW-01 **LOW** | `backend/tests/integration/test_chat_routes.py:33` | Global counts/updates could fail with unrelated data or conceal isolation problems. Scoped queries and per-test unrelated synthetic sentinel; 135 focused tests and full suite pass. | FIXED |
| AUD-DOC-01 **LOW** | `README.md:3`, `documentation/CURRENT_PROJECT_STATUS.md` | Stale phase/migration/dependency claims made actual capabilities unclear. Current summary and evidence links updated; dated historical reports retained. Foundation tests and link/inventory checks verify documentation. | FIXED |
| AUD-TEST-01 **LOW** | `backend/tests/integration/test_product_browse_migration.py:24` | Existing test isolated its table but not its server/database. Reused native disposable-server harness; isolated index round-trip plus six related cases pass; development hashes unchanged. | FIXED |

### Unresolved vulnerabilities versus documented limitations

No unresolved CRITICAL/HIGH vulnerability was identified in the completed local application review. Zero audit findings does **not** assert absence of unknown dependency vulnerabilities or authorize production deployment.

- **LOW consistency debt:** catalog/listing parsers do not all enforce the same duplicate-JSON-key rejection policy as auth/chat/offers. Typed values remain bounded and validated. No authorization bypass was demonstrated; standardize deliberately with contract tests in a later hardening batch.
- **LOW specification depth:** many legacy errors now use a truthful safe OpenAPI fallback rather than enumerating every possible HTTP status per operation. Cookie/CSRF auth is documented in the API material and table, but richer generated client metadata could improve it.
- **Documented security boundaries, not newly fixed vulnerabilities:** logout revokes refresh authority, not every previously issued access JWT instantly; current account/password checks and access TTL still apply. Contact revocation cannot retract information already read. ORM immutability does not defend against an administrator issuing raw SQL.
- **Production blockers:** development Compose, local media, disabled/fake delivery, single-process limits/delivery, unverified TLS/WSS/proxy/container/browser/rotation/operational behavior. These are explicitly excluded from a production-ready claim.

### Security control assessment

The review is aligned to the [OWASP API Security Top 10 2023](https://api-security.owasp.org/editions/2023/en/0x00-header/) and relevant authentication, session, validation, authorization and data-protection themes in [ASVS 5.0](https://asvs.owasp.org/downloads/). This is not a complete requirement-by-requirement ASVS certification.

| Risk area | Evidence and residual boundary |
| --- | --- |
| API1/API3/API5: object/property/function authorization | Cross-user and wrong-role route/service tests; owner/participant filters; strict input schemas; explicit safe projections; administrator routes enforce role. Public seller badge exposes intended verification indicator, not evidence/contacts/storage keys. |
| API2: authentication | Fixed algorithms/claims/expiry validation, recommended password hashing, hashed rotating refresh/code secrets, CSRF/Origin checks, replay-family revocation, current-account enforcement and corrected lock ordering. UI memory-only token and stale-session guards pass. |
| API4/API6: resources/business flows | Actual-byte/time limits, bounded per-peer/account stores, capped pages, message queues and upload concurrency, anti-replay uniqueness, state-machine checks. Process-local controls are not distributed DDoS protection. |
| API7: SSRF | No user-supplied URL-fetch endpoint identified in registered features. Uploads accept bytes, not arbitrary remote URLs. Vendor endpoints are configuration controlled. No external SSRF scanner or production egress test was performed. |
| API8/API9: configuration/inventory | Runtime secret/provider/environment validation, explicit trusted CORS, private cache controls, exhaustive route inventory and corrected metadata. Development docs remain public by design. Deployment hardening is still a release gate. |
| API10 / cryptography / external dependencies | WeChat uses AES-256-GCM, random 12-byte nonce and conversation/version AAD; malformed/tampered/cross-conversation ciphertext and missing keys fail closed. No custom cipher introduced. Tencent integration remains bounded/exception-mapped; real vendor credentials/delivery were not exercised. |
| Injection, unsafe deserialization and traversal | ORM bound parameters and allowlisted sort/query structure; no request-derived shell execution identified. Media keys and paths are server controlled with traversal/symlink tests. No pickle-like request decoding. Tests cover malicious search/cursors and invalid images. |
| XSS / browser state | No application dangerouslySetInnerHTML/eval sink found in source search; text rendering, contract validation, safe redirects and no token localStorage. Only language preference is persisted. jsdom tests do not replace deployed CSP/browser acceptance. |
| WebSocket privacy/availability | URL/subprotocol tokens rejected, Origin checked before accept, pending sockets occupy capacity, authenticate-first deadline, bounded queues/frame rates, authorization before persistence and outbound bytes, expiry/disconnect/shutdown cleanup. Real multi-device/offline/revocation checks pass. |
| Evidence privacy and audit | Tickets sent in header, never URL; no seller evidence public route or key projection. Evidence reads are audited transactionally before bytes; audit failure denies bytes. Separate product/evidence storage and sanitized image metadata retained. |

Private SQL exception details, request secrets and contacts are not emitted by safe error handlers. Diff inspection found no real credential added; synthetic test literals are not production secrets. No passwords, codes, tokens or private documents were copied into this report.

## G. Functional verification

All modules below ran in the full backend cycle; counts identify representative test files, not disjoint totals and not exhaustive branch coverage.

| Module | Important behaviors exercised | Exact representative evidence / limits |
| --- | --- | --- |
| Authentication | Registration uniqueness/hash safety, login failure masking, claims, active status, phone/email codes, reset/change atomicity, refresh rotation/replay/CSRF/logout | Full suite; route files: register 27, login 33, refresh 22, forgot 22, reset 31, change 35, phone 20, email 29; integrated auth 11 and lock probes 4. Real login included in live chat checks. Vendor delivery not live-tested. |
| Profiles/onboarding | Own/public projections, Unicode limits, public handles, city references, snapshot/auth races | Profile routes 38, models 9, concurrency 5, snapshot 8, public-handle routes 20; Unicode frontend regression 9. |
| Seller verification | Draft/upload/submit/review, immutable submissions, challenge expiry/renewal, badge privacy, audited ticket reads | Verification 37, challenge/privacy 15, evidence security 16, concurrency 8; 305 identity follow-up tests include actual multipart behavior. Production evidence storage not provisioned. |
| Catalog/admin | Active public catalogs, role checks, child-parent integrity, audit/rollback, concurrent updates | Catalog API 92 and concurrency 8. No new admin screen implemented. |
| Products | Ownership/current eligibility, allowed transitions, validation, current visibility and race safety | Listings 137, adversarial 15, concurrency 19; preserved Phase 9 API contracts. |
| Images/storage | Re-encoding, actual size limits, metadata privacy, owner/public access, ordering/cover/deletion, compensating cleanup | Images 80, image adversarial 20, concurrency 13 + adversarial concurrency 8; decoder/path/security unit files; local report-only consistency clean. |
| Browse/search | Normalized query/filter/sort, private-data exclusion, signed cursor tamper checks, bounded SQL/index compatibility | Browse integration 44, unit 25, disposable index probe 1. Historical production-sized benchmarks were not rerun. |
| Favorites/recent | Idempotency, current visibility, cross-user denial, signed pagination, quotas/pruning/clear | Personalization integration 93, unit 38 + services 10, OpenAPI 2; preserves existing 500/100 limits. |
| Chat/messages | Unique conversation, durable idempotent messages, ownership, bounded history, authorized socket fan-out and cleanup | Chat routes 66, concurrency 6, domain 56, security 31, sockets 63; real HTTP/WS 175 checks. Single-process fan-out only. |
| WeChat | Explicit seller consent, role denial, ciphertext integrity, no list/event contact leak, terminal denial/revocation | Included in chat route/security/live counts; revocation cannot erase already copied contact. |
| Offers/deals | Proposer/recipient roles, exact CNY arithmetic, counter chain, expiration, idempotent retries, race-safe acceptance/archival/competing cancellation and private agreement projection | Offer routes 69, contracts 43, security 21, concurrency 11; real offers HTTP workflow passed with exact cleanup/no automatic messages. |
| Frontend | Auth bootstrap/refresh/logout/cache/version, guards, profile/onboarding, catalog/product/media/evidence pages, four-language/RTL contracts | 405 tests / 24 files; TS, ESLint and build pass. No deferred chat/offers/favorites/search screens implemented; real browser not rerun. |
| Health/configuration | Safe root/health/database responses, DB availability failure, development-only inboxes and runtime fail-closed settings | Fresh Uvicorn GET /, /health, /api/v1/health, /api/v1/health/database all 200; connected true; outage 503 and live CORS challenge checks pass. |

## H. Test coverage report

| Gate | Result |
| --- | --- |
| Consolidated full backend | **2,003 passed**, zero failed/skipped, 180.69 seconds; one inherited Starlette TestClient deprecation warning |
| Final collected backend inventory | **2,015 cases** across 77 test files: **1,225 integration**, **790 unit**; twelve new follow-up cases verified in targeted runs |
| OpenAPI/profile/media follow-up | **215 passed**, one inherited warning |
| Identity/seller/profile follow-up | **305 passed**, one inherited warning; includes the eight additional ingress cases |
| Final migration-isolation/foundation follow-up | **7 passed** on the corrected disposable native MySQL probe; no development DDL in the corrected test |
| Full frontend | **405 passed / 24 files**, 22.90 seconds |
| Additional concurrency | Three rounds, **32 passed each** (10.03 / 8.52 / 7.39 seconds); offers, chat, refresh lock probes and integrated auth |
| Live HTTP + WebSocket | **175 chat checks**; separate offer/deal workflow and four health URLs plus CORS challenge check: PASS |
| Backend static/dependency consistency | Ruff **--no-cache** PASS; compile **384 Python files** without writing bytecode; pip check PASS |
| Frontend static/build | TypeScript, ESLint, Vite production build PASS (429 transformed modules; no build warning reported) |
| Vulnerability databases | pip-audit: **74 packages, zero known vulnerabilities**; npm all: **zero**; npm omit-dev: **zero** |
| Database/storage | Current=head e14f5a6b7c8d, no drift; 24 baseline data/schema hashes equal; product media report-only audit 0 rows/0 issues |
| Git | Whitespace checks and explicit staged manifests passed for every source batch; normal pushes and remote SHAs verified |

Focused security is not a separate additive test count: the full suite includes negative authentication, BOLA, role, replay, cursor, malformed/oversize input, evidence audit failure, state-machine and concurrency cases. The 305-case follow-up is an explicit post-fix security regression gate. Do not sum overlapping focused/full/live counts as unique test coverage.

### Measured function entry, not branch coverage

A CPython 3.13 `sys.monitoring.PY_START` callback recorded the first test observed entering each AST-defined function during setup/call/teardown. **782 / 837 = 93.43%** definitions were entered. The denominator deliberately includes nested definitions, abstract protocol stubs and import-time decorators, but excludes lambdas and generated framework code. Import-time calls before the test context do not count; asynchronous/thread attribution can inherit the current test label. A hit does not prove return values, all conditions, exception paths, transaction outcomes or assertion adequacy.

The inventory preserves every function → first observed test mapping and the measurement revision. Follow-up edits shifted some source lines; `line_at_measurement` is tied to that revision. No line/branch coverage tool was configured; no 100% claim is made. Frontend function/branch coverage was not instrumented; 450 AST declarations/callbacks are inventory only.

The following 55 definitions had **no observed entry in that full run**:

| Module : line at measurement | Function | Interpretation / remaining scenario |
| --- | --- | --- |
| `app/api/v1/auth/dependencies.py:234` | `get_refresh_ip_rate_limiter` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/api/v1/auth/dependencies.py:238` | `get_refresh_session_rate_limiter` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/api/v1/auth/dependencies.py:242` | `get_logout_ip_rate_limiter` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/api/v1/auth/dependencies.py:246` | `get_logout_all_user_rate_limiter` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/api/v1/auth/dependencies.py:250` | `get_email_verification_resend_ip_rate_limiter` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/api/v1/auth/dependencies.py:254` | `get_email_verification_resend_user_rate_limiter` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/api/v1/catalog/dependencies.py:24` | `_raise_rate_limit` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/api/v1/chat/websocket.py:28` | `_authorize` | Real WebSocket workflow subsequently exercised authorization outside instrumented pytest. |
| `app/api/v1/me/dependencies.py:39` | `_reject` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/api/v1/products/dependencies.py:23` | `_reject` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/api/v1/profiles/routes.py:121` | `_unavailable_error` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/api/v1/router.py:42` | `health` | Fresh live Uvicorn health checks subsequently exercised this path outside the measurement. |
| `app/api/v1/router.py:47` | `database_health` | Fresh live Uvicorn health checks subsequently exercised this path outside the measurement. |
| `app/api/v1/seller_verification/dependencies.py:21` | `limited` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/api/v1/seller_verification/dependencies.py:49` | `local_storage` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/core/config.py:393` | `_is_placeholder_password` | Import-time/configuration/decorator entry excluded or not directly observed; not proof of dead code. |
| `app/core/config.py:404` | `build_database_url` | Import-time/configuration/decorator entry excluded or not directly observed; not proof of dead code. |
| `app/core/config.py:448` | `get_settings` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/core/database.py:21` | `get_database_url` | Dependency provider may be overridden by tests; real wiring needs separate integration evidence. |
| `app/core/database.py:47` | `check_database_connection` | Fresh live Uvicorn health checks subsequently exercised this path outside the measurement. |
| `app/core/transactions.py:41` | `retry_deadlock` | Import-time/configuration/decorator entry excluded or not directly observed; not proof of dead code. |
| `app/integrations/development_fake_sms.py:84` | `DevelopmentFakeSmsStore.consume_message` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/integrations/development_fake_sms.py:112` | `DevelopmentFakeSmsStore.clear` | Fixture/store cleanup can run outside the recorded test context. |
| `app/integrations/email_verification_delivery.py:29` | `EmailVerificationDeliveryProvider.deliver_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/email_verification_delivery.py:38` | `EmailVerificationDeliveryProvider.consume_verification_code` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/integrations/email_verification_delivery.py:45` | `DisabledEmailVerificationDeliveryProvider.deliver_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/email_verification_delivery.py:173` | `DevelopmentFakeEmailVerificationStore.clear` | Fixture/store cleanup can run outside the recorded test context. |
| `app/integrations/email_verification_delivery.py:215` | `DevelopmentFakeEmailVerificationProvider.consume_verification_code` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/integrations/password_reset_delivery.py:31` | `PasswordResetDeliveryProvider.deliver_reset_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/password_reset_delivery.py:45` | `DisabledPasswordResetDeliveryProvider.deliver_reset_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/password_reset_delivery.py:154` | `DevelopmentFakePasswordResetStore.clear` | Fixture/store cleanup can run outside the recorded test context. |
| `app/integrations/sms_client.py:42` | `SmsSender.send_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/sms_client.py:50` | `SmsSender.consume_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/sms_client.py:83` | `DisabledSmsSender.send_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/sms_client.py:92` | `DisabledSmsSender.consume_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/sms_client.py:100` | `UnavailableSmsSender.send_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/sms_client.py:109` | `UnavailableSmsSender.consume_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/integrations/sms_client.py:197` | `TencentSmsSender.consume_verification_code` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/main.py:188` | `create_app.root` | Fresh live Uvicorn health checks subsequently exercised this path outside the measurement. |
| `app/services/chat_service.py:35` | `ConversationService.authorize` | Real WebSocket workflow subsequently exercised authorization outside instrumented pytest. |
| `app/services/offer_service.py:21` | `conflict_guard` | Import-time/configuration/decorator entry excluded or not directly observed; not proof of dead code. |
| `app/services/phone_verification_service.py:204` | `PhoneVerificationService._provider_unavailable` | Direct error/provider/adapter branch not measured; add a focused test when changing it. |
| `app/services/product_image_storage.py:16` | `ProductImageStorage.save` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/product_image_storage.py:18` | `ProductImageStorage.read` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/product_image_storage.py:20` | `ProductImageStorage.delete` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/product_image_storage.py:22` | `ProductImageStorage.keys` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/product_image_storage.py:105` | `DisabledProductImageStorage.save` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/product_image_storage.py:107` | `DisabledProductImageStorage.read` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/product_image_storage.py:109` | `DisabledProductImageStorage.delete` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/product_image_storage.py:111` | `DisabledProductImageStorage.keys` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/storage_service.py:69` | `StorageProvider.upload` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/storage_service.py:71` | `StorageProvider.delete` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/storage_service.py:73` | `StorageProvider.read` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/storage_service.py:75` | `StorageProvider.issue_download_ticket` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |
| `app/services/storage_service.py:78` | `StorageProvider.redeem` | Protocol/no-op/disabled-provider definition; review concrete implementer coverage separately. |

Remaining unmeasured scenarios include arbitrary production timing/scheduling, prolonged queue pressure, real vendor delivery, deployed cross-origin cookie policies, populated remote object-storage failures, actual key rotation, backup/restore and production database load. Core authorization/persistence is covered using real MySQL, but frontend HTTP tests and many unit error branches use mocks; the live scripts close only the specifically reported backend transport gaps.

### Failures and interruptions retained in the evidence

- Initial new immutable-field test assertions compared buyer-role and seller-role projections: **16 failed / 128 passed**. Corrected the test actor, not production authorization; rerun **144 passed**.
- First frontend logout recovery implementation failed TypeScript because Axios raw/header-object types differ. Used the existing typed header-discrimination approach; focused tests/TS/ESLint and full frontend run passed.
- Initial nested npm override layout installed the target package but `npm ls` reported invalid override edges. Replaced it with the single audited minimatch override, clean-installed, and verified all consumers at 11.0.1.
- First pip-audit remediation retry hit a network read timeout. Normal TLS validation remained enabled; subsequent audits with a 30-second timeout passed.
- Ruff encountered a corrupted cache/wrong-package panic. Re-running with `--no-cache` passed; no source rule was disabled and no unrelated file was cleaned.
- An initial function-monitoring run was stopped because it instrumented library code too aggressively. Database/schema fingerprints were checked equal before restarting with application-only monitoring. It is not counted as a completed suite pass.
- The identity-ingress extension initially caused **2 failed / 303 passed**: malformed seller JSON skipped the stricter seller budget. Moved the existing seller boundary outside generic identity parsing. The identical selection then passed **305/305** before commit.
- The inherited migration probe ran on a copied development table before its isolation gap was identified. No legitimate data/schema changed. It was corrected and rerun on a separate disposable MySQL instance; this distinction is retained rather than describing the original run as database-isolated.
- No remaining test failure or ignored mandatory local check is hidden by this report. The single inherited TestClient deprecation warning remains LOW maintenance debt.

### Reproduction commands

Run from `backend` using its existing virtual environment (PowerShell examples):

```powershell
.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider -q --tb=short
.venv\Scripts\python.exe -B -m ruff check --no-cache app alembic tests scripts
.venv\Scripts\python.exe -B -m pip check
.venv\Scripts\python.exe -B -m pip_audit --progress-spinner off --timeout 30
.venv\Scripts\python.exe -B -m alembic current
.venv\Scripts\python.exe -B -m alembic heads
.venv\Scripts\python.exe -B -m alembic history
.venv\Scripts\python.exe -B -m alembic check
.venv\Scripts\python.exe -B -m scripts.audit_product_media
```

Live synthetic checks require explicit local-development consent and clean up only their own fixtures; do not run them concurrently with other database suites:

```powershell
.venv\Scripts\python.exe -B -m scripts.chat_http_checks --allow-development-synthetic-writes
.venv\Scripts\python.exe -B -m scripts.offers_http_checks --allow-development-synthetic-writes
```

From `frontend`:

```powershell
$env:NODE_USE_SYSTEM_CA='1'
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd run test -- --run
npx.cmd tsc -b --pretty false
npm.cmd run lint
npm.cmd run build
npm.cmd audit
npm.cmd audit --omit=dev
npm.cmd ls minimatch tailwindcss --all
```

The normal full pytest command is provided for future reproducibility; this audit used its equivalent in-process invocation with the monitoring callback. Compilation used Python's `compile()` on each source file, avoiding generated bytecode. No backend static type checker is configured; none is claimed to have run.

## I. Dependency and infrastructure security

The security-only changes were verified against both installed environments and manifests. Python adds explicit transitive pins for dnspython 2.9.0 and msgpack 1.2.3. npm locks minimatch 11.0.1 (with its required nonrecursive matcher) through the existing override mechanism. The clean install produced 331 installed packages; npm's lock/audit graph reports 364 dependency nodes, a different metric. Tailwind remains **3.4.19**. Existing CSS fixture compatibility tests are part of the passing frontend suite.

Advisory evidence: [dnspython upstream](https://github.com/rthalley/dnspython/security/advisories/GHSA-45c3-73f7-pv4m), [msgpack upstream](https://github.com/msgpack/msgpack-python/security/advisories/GHSA-j586-36cw-2gc2), [minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249), and [minimatch patched release](https://github.com/isaacs/minimatch/releases/tag/v11.0.1). These identify the package-level fixes; application exploitability was assessed separately in section F. Current audits replace—not retroactively rewrite—the older phase reports' historical Tailwind/braces findings.

npm used the machine trusted certificate store through Node's normal system-CA setting, normal HTTPS registry and `strict-ssl=true`. No certificate bypass, insecure registry, forced audit fix or Tailwind migration was used. Python installs/audits also kept normal TLS verification.

Infrastructure observations:

- Compose is **development configuration**, with local bind mounts, exposed MySQL/API ports, development password fallbacks and Vite's dev server. It is not a hardened production deployment.
- Existing containers do not establish a verified non-root production identity or hardened read-only runtime. Root/build contexts and ignored secrets were source/test reviewed; no deployment was performed.
- `docker compose config --quiet` passed. Docker client **29.8.2** is installed, but `docker version` could not reach the Linux engine named pipe. Docker/NGINX runtime validation is **environment-blocked**. No native NGINX executable was found.
- NGINX has query-free access logging, special private-evidence/WebSocket log handling, upload caps and upgrade forwarding, but listens on port 80 and is not wired into the current Compose services. Deployed TLS/WSS, proxy trust and security headers require a real deployment gate.
- Local private product/evidence storage is not production object storage. Production credentials, secret/key rotation, retention/deletion/backup operations and bucket permissions were not provisioned or asserted.
- Fake/disabled reset and email providers are intentional local foundations. Real outbound delivery remains unimplemented/unconfigured; Tencent transport was not contacted with live credentials.
- Rate budgets and WebSocket subscriptions are process-local. Multiple workers would not provide shared fan-out or a shared quota. Stay single-process for the documented portfolio architecture until requirements justify a separately designed scaling change.
- The lockfile makes npm ci reproducible, but several package manifest ranges still say latest. Python pins top-level/security transitive packages without a complete hash-locked environment. Future resolution should remain review-gated.
- No CI workflow was introduced. No browser, production host, external penetration test or fresh MySQL 8 server run was performed in this audit. Historical checks remain historical.
- Postman files were reused as contract references without initializing/publishing a workspace or modifying the unrelated README. Pytest and guarded local HTTP scripts supplied the reported execution evidence; no Postman collection-run result is claimed.
- The installed Postman executable rejected `postman status` with `unknown command 'status'`. This optional skill setup check is unavailable in that CLI version, not a passing API verification. No workspace initialization, upgrade, publication or cloud request was attempted.

## J. Complete change log and Git verification

Each batch used an explicit individual-path whitelist, checked the staged manifest and whitespace, committed once, pushed normally to `origin/feature/authentication`, fetched, and verified remote SHA = local SHA. No force push or history rewrite was used. All batches below have **push PASS / remote SHA verified**. Tests are focused unless explicitly marked full; detailed findings and resolved intermediate failures are above.

### Batch 1: fix: preserve immutable offer terms across ORM expiration

Commit: [`7316f9f13366cc841fd679069e863b6da02b80e0`](https://github.com/ilyasmustaphahatime/unishop-china/commit/7316f9f13366cc841fd679069e863b6da02b80e0). Push: PASS. Remote SHA matched.

Reason: Close the persisted unloaded-field immutability bypass without changing schema or proposal terms.

Verification: 144 passed; Ruff passed; database fingerprints unchanged

Exact files (3):

- `backend/app/models/offer.py`
- `backend/app/models/deal.py`
- `backend/tests/integration/test_offer_routes.py`

### Batch 2: fix: bound authentication requests before JSON parsing

Commit: [`18355465f11e6c51b62cf5e108e6070437b23146`](https://github.com/ilyasmustaphahatime/unishop-china/commit/18355465f11e6c51b62cf5e108e6070437b23146). Push: PASS. Remote SHA matched.

Reason: Bound malformed authentication requests before parsing/dependencies; document safe error shapes.

Verification: 207 auth/security tests; 106 contract regressions; Ruff PASS

Exact files (6):

- `backend/app/core/auth_request_security.py`
- `backend/app/main.py`
- `backend/app/api/v1/auth/routes.py`
- `backend/app/schemas/errors.py`
- `backend/tests/conftest.py`
- `backend/tests/unit/test_auth_request_security.py`

### Batch 3: refactor: decouple pagination types from service implementations

Commit: [`7c1b9e9a10f153ee6290ecfa16a49fc15c661624`](https://github.com/ilyasmustaphahatime/unishop-china/commit/7c1b9e9a10f153ee6290ecfa16a49fc15c661624). Push: PASS. Remote SHA matched.

Reason: Resolve the Phase 12 reverse-layer dependency and equivalent browse coupling without breaking callers.

Verification: Focused browse/personalization tests and Ruff; see terminal results

Exact files (7):

- `backend/app/common/pagination.py`
- `backend/app/services/product_browse_cursor.py`
- `backend/app/services/personalization_cursor.py`
- `backend/app/repositories/favorites_repository.py`
- `backend/app/repositories/recently_viewed_repository.py`
- `backend/app/repositories/product_browse_repository.py`
- `backend/tests/unit/test_repository_boundaries.py`

### Batch 4: fix: document personal listing API error contracts

Commit: [`48a17df9ce789e72cdd387fb3bde62edcb8f2937`](https://github.com/ilyasmustaphahatime/unishop-china/commit/48a17df9ce789e72cdd387fb3bde62edcb8f2937). Push: PASS. Remote SHA matched.

Reason: Resolve the Phase 12 missing documented private-list error contracts.

Verification: Personalization OpenAPI, public handle and real MySQL regressions; Ruff PASS

Exact files (4):

- `backend/app/api/v1/me/dependencies.py`
- `backend/app/api/v1/me/favorites_routes.py`
- `backend/app/api/v1/me/recently_viewed_routes.py`
- `backend/tests/unit/test_personalization_openapi.py`

### Batch 5: test: isolate chat regressions from unrelated conversation data

Commit: [`a2011902c0b4892f9480fb8e56a6793942582f11`](https://github.com/ilyasmustaphahatime/unishop-china/commit/a2011902c0b4892f9480fb8e56a6793942582f11). Push: PASS. Remote SHA matched.

Reason: Resolve the Phase 13 unscoped-test observation and prove unrelated rows remain unchanged.

Verification: Chat HTTP, concurrency and WebSocket focused suite; Ruff PASS

Exact files (1):

- `backend/tests/integration/test_chat_routes.py`

### Batch 6: fix: serialize refresh and credential writes with consistent locks

Commit: [`58077a13706159d15a95a0f67671f8b481e018af`](https://github.com/ilyasmustaphahatime/unishop-china/commit/58077a13706159d15a95a0f67671f8b481e018af). Push: PASS. Remote SHA matched.

Reason: Remove a concrete user/token lock inversion and stale-session-count snapshot; strengthen race assertions.

Verification: 108 auth/session tests passed; 4 deterministic MySQL lock tests rerun after dependency updates; Ruff passed

Exact files (4):

- `backend/app/repositories/token_repository.py`
- `backend/app/services/refresh_session_service.py`
- `backend/tests/integration/test_phase_5e_integrated_auth_security.py`
- `backend/tests/integration/test_refresh_lock_order.py`

### Batch 7: fix: align profile form Unicode validation with server limits

Commit: [`8ecde69013339d4abf835cb776c85c661c3f5f5b`](https://github.com/ilyasmustaphahatime/unishop-china/commit/8ecde69013339d4abf835cb776c85c661c3f5f5b). Push: PASS. Remote SHA matched.

Reason: Align client Unicode validation with existing server rules; no UI redesign.

Verification: 61 frontend focused tests passed including 27 profile tests; TypeScript and ESLint passed

Exact files (3):

- `frontend/src/features/profiles/schemas.ts`
- `frontend/src/components/profiles/ProfileForm.tsx`
- `frontend/tests/unit/profile-form-unicode.test.ts`

### Batch 8: fix: recover expired browser authority for logout all

Commit: [`39461f9553045355a4eef00864a5874d55c21856`](https://github.com/ilyasmustaphahatime/unishop-china/commit/39461f9553045355a4eef00864a5874d55c21856). Push: PASS. Remote SHA matched.

Reason: Restore logout-all after access expiry without restoring local auth; make browser auth headers readable.

Verification: 61 focused frontend tests, TypeScript and ESLint passed; 111 backend CORS/security tests and Ruff passed

Exact files (5):

- `frontend/src/features/auth/session.ts`
- `frontend/src/services/apiClient.ts`
- `frontend/tests/unit/auth-session.test.ts`
- `backend/app/main.py`
- `backend/tests/unit/test_browser_auth_headers.py`

### Batch 9: fix: update vulnerable DNS and build tooling dependencies

Commit: [`e2616335b56ecb60c0e583c1aa318defbcf4ff60`](https://github.com/ilyasmustaphahatime/unishop-china/commit/e2616335b56ecb60c0e583c1aa318defbcf4ff60). Push: PASS. Remote SHA matched.

Reason: Remove reported DNS, development-cache and build-chain advisories using narrowly scoped pins.

Verification: Full backend 2003 passed; frontend 405 passed; TypeScript, ESLint, build, Ruff --no-cache, compile, pip check, pip-audit and both npm audits PASS; clean npm ci verified installed minimatch11.0.1/Tailwind3.4.19

Exact files (4):

- `backend/requirements.txt`
- `backend/requirements-dev.txt`
- `frontend/package.json`
- `frontend/package-lock.json`

### Batch 10: fix: complete safe error and binary OpenAPI contracts

Commit: [`a670b18f260f00f3c818586fdda6d56dca9804cc`](https://github.com/ilyasmustaphahatime/unishop-china/commit/a670b18f260f00f3c818586fdda6d56dca9804cc). Push: PASS. Remote SHA matched.

Reason: Describe existing fallback errors, safe validation, health outage and binary evidence accurately.

Verification: 215 targeted OpenAPI, foundation, profile and image/evidence tests passed; Ruff passed. Documentation-only route metadata, no runtime payload changes.

Exact files (4):

- `backend/app/main.py`
- `backend/app/api/v1/router.py`
- `backend/app/api/v1/seller_verification/routes.py`
- `backend/tests/unit/test_api_error_inventory.py`

### Batch 11: fix: bound identity JSON without bypassing seller rate limits

Commit: [`cc9f08043b9f35dbc1070681fbf4f9df98730870`](https://github.com/ilyasmustaphahatime/unishop-china/commit/cc9f08043b9f35dbc1070681fbf4f9df98730870). Push: PASS. Remote SHA matched.

Reason: Extend bounded identity input while retaining stricter seller peer budgets and multipart limits.

Verification: 305 focused identity, profile, seller, security and concurrency tests passed after fixing middleware-order regression (initial 303 passed, 2 failed); live Uvicorn health/CORS PASS; Ruff PASS.

Exact files (3):

- `backend/app/core/auth_request_security.py`
- `backend/app/main.py`
- `backend/tests/unit/test_auth_request_security.py`

### Batch 12: test: isolate browse migration probes from development database

Commit: [`e4df89008c4fb6994cf5d0a1595e4bf98c63fded`](https://github.com/ilyasmustaphahatime/unishop-china/commit/e4df89008c4fb6994cf5d0a1595e4bf98c63fded). Push: PASS. Remote SHA matched.

Reason: the existing copied-table migration probe did not meet the separate disposable-database boundary. The existing native harness now owns all DDL on its temporary datadir/port. No production/application migration changed.

Verification: 7 focused migration, repository-boundary and foundation tests passed; Ruff passed; all 24 development data/schema fingerprints matched.

Exact file: `backend/tests/integration/test_product_browse_migration.py`.

### Documentation closure

Task-owned documentation paths only:

- `README.md`
- `documentation/CURRENT_PROJECT_STATUS.md`
- `documentation/audits/FULL_CODEBASE_ARCHITECTURE_API_SECURITY_AUDIT.md`
- `documentation/audits/FULL_CODEBASE_AUDIT_INVENTORY.json`

These align current capabilities and preserve the complete endpoint/function/model/test/finding/commit evidence. Documentation verification checks JSON parsing, inventory counts, all A–L sections, relative links, exact path manifest, whitespace, protected hashes and foundation tests. The enclosing documentation commit is identifiable with `git log -1 -- documentation/audits/FULL_CODEBASE_ARCHITECTURE_API_SECURITY_AUDIT.md`; its final SHA and remote verification are returned at handoff, avoiding a self-referential commit hash in this file.

The unrelated LICENSE and Postman README were excluded throughout. The 13 protected artifacts (one PDF, one rendering script and eleven page PNGs) retain baseline SHA-256 hashes and remain untracked. Audit inventory hashes are evidence only; none of those protected files was staged. Every source change belongs to the exact manifests above. No environment secret, generated build directory, cache or temporary test fixture is included.

The audit owns 40 unique committed source/test/dependency paths plus these four documentation paths (44 total). Credential-pattern inspection reported zero high-risk candidates in the source/test/dependency diff; this is a bounded diff check, not a complete repository-history secret scan. Contract-first API skills guided reuse of existing schemas/tests instead of new endpoints or Postman scaffolding; the React review guided focused session/validation fixes without UI redesign.

## K. Remaining technical debt

| Priority / severity | Item and impact | Effort / recommended follow-up |
| --- | --- | --- |
| Release gate / **MEDIUM** operational | Private production storage, permissions, retention, backup/restore and cleanup monitoring unconfigured | Medium–large; dedicated deployment/storage acceptance before exposure |
| Release gate / **MEDIUM** operational | Production HTTPS/WSS, reverse-proxy trust, non-root/container isolation and secret provisioning not verified; development defaults must not be deployed | Medium; deployment-hardening work with runtime tests |
| Release gate / **MEDIUM** operational | Real reset/email delivery, vendor failure handling and production key rotation not verified end to end | Medium; explicitly approved delivery/operations phase |
| Release gate / **MEDIUM** assurance | Fresh real-browser cookie/expired-logout flow, target MySQL 8/runtime acceptance, prolonged load and recovery testing absent | Medium; release qualification, not an assertion that jsdom/local MySQL 9.4 replaces it |
| **LOW** architecture | Single-process socket fan-out/rate budgets; large auth dependency/route modules | Preserve documented deployment scope; refactor/scale only for measured requirements |
| **LOW** API consistency | Legacy duplicate-key policy differs; per-status error/cookie security metadata could be richer than fallback models | Small–medium; contract-focused hardening with compatibility tests |
| **LOW** test assurance | 55 unobserved function definitions, no branch/line coverage gate; TestClient deprecation; some documentation assertions encode historical prose | Medium; targeted meaningful branches, coverage tooling/CI, planned HTTP client compatibility update |
| **LOW** supply chain | Manifest latest ranges, Python environment not fully hash locked, security overrides need periodic review | Small–medium; reproducible-resolution/CI maintenance, no unverified bulk upgrades |
| **LOW** data-performance | Catalog singleton lock and search selectivity not measured at deployment scale; no new EXPLAIN/load benchmark | Medium; profile with representative disposable data before optimization |
| **LOW** scaffolding/docs | Future-phase placeholders remain; historical reports are intentionally dated | Keep clearly labeled; implement only by separately approved feature requests |

Historical findings are not dropped: **P12-ARCH-LOW-01 resolved**, **P12-AUDIT-OPENAPI-01 resolved**, **P13-AUDIT-LOW-01 resolved**, and **P14-AUDIT-LOW-01 resolved for normal persisted ORM assignments**. The documented raw-SQL administrative escape hatch remains.

## L. Final verdict

**AUDIT PASSED — CODEBASE VERIFIED WITH DOCUMENTED LIMITATIONS**

The required local consolidated and post-fix targeted checks pass. No unresolved CRITICAL/HIGH application vulnerability was identified in this scope. The route/function/module inventory and explicit measurement gaps are part of this verdict; passing tests are not proof that all functions or branches are correct.

**Production readiness: NO.** Deployment/storage/delivery/browser/target-runtime/load/rotation gates above remain. Docker/NGINX runtime is specifically environment-blocked. No Phase 15 work was started.
