# Phase 11A — Internationalization implementation report

> Historical implementation baseline. The independent
> [final adversarial audit](PHASE_11A_FINAL_ADVERSARIAL_AUDIT.md) found and
> corrected four issues; its final results are 387 frontend tests, 1,388
> backend tests and 130 real-Chrome checks. The original 104-file manifest
> below remains intact; the audit adds two scoped paths. Production readiness
> is not claimed.

Started 2026-10-13; final review 2026-10-14, Asia/Shanghai.
Implementation is locally verified, not final adversarial closure or production certification.

## 1. Executive Result

Phase 11A implementation complete: YES. Local implementation gate: PASS.
Ready for final adversarial audit: YES. Ready for Phase 11B after a successful
independent final audit and human Git closure: YES, conditionally; not authorized now.
Production ready: NO. No new unresolved Critical/High/Medium/Low implementation
findings. One Low display finding (owner-list UTC clock preservation) was fixed
with four targeted regressions and the final Chrome UTC checks. Inherited dependency findings remain: one High advisory affecting five
build nodes and one Moderate advisory affecting two. Informational limitations:
catalog language data, legacy copy, all-browser/assistive-tech and native-speaker QA.
No Phase 11B/11C/11D, staging, commit or push.

## 2. Git Baseline

Branch: `feature/authentication`. Starting and final HEAD:
`00be821eeb956d19e460e33732bf608f1802d73d`, tracking
`origin/feature/authentication` with no ahead/behind divergence.
Initial index and tracked tree were clean. The 13 unrelated untracked PDF/script/
render artifacts under `output/` and `tmp/` were fingerprinted and protected.
No reset, restore, clean, historical migration change or Phase 10 report rewrite.

## 3. Repository Audit

Actual code, not older phase claims, governed coverage. Inspected entry point,
route objects/lazy loading, all three layouts, common controls, login/auth/session/
query logic, profiles/onboarding, catalog selects/directory, private verification,
development fake SMS, products and owner/public galleries. The initial AST review
aid found 92 reachable modules, 21 screen modules and 309 candidate string records
(including CSS/internal diagnostics; not 309 proven UI labels). Manual review
included single-word labels, dynamic messages, accessibility attributes and helpers.

Nine admin page files are unrouted heading scaffolds, not implemented admin UI.
Chat/deals/favorites/reviews/notifications and unused placeholder controls were not
converted into new features. Password/email workflows in backend do not imply
existent frontend forms. Remaining source English is brand/diagnostic text,
application-owned safe helper/schema categories, CSS or identifiers, not visible
untranslated UI. The JSX AST test and semantic-key checks supplement manual review;
neither is described as a perfect untranslated-text detector.

## 4. Architecture

One `languages.ts` registry drives allowlist, direction, Intl locale, catalog name
selection and the native selector. One `i18n/index.ts` instance uses
`initReactI18next` and locally bundled resources with `initAsync:false`.
The entry point imports it before visible React render. Existing auth/query
providers stay unchanged; the narrow translation hook explicitly uses the instance.
A serialized latest-request controller owns presentation transitions only.
Preference access is centralized/caught. Root lang/dir/title/description synchronize
on engine changes. Formatting and safe-message/enum adapters are reusable modules.

No runtime translation provider, detector, remote service, account locale, auth
store ownership, query-cache ownership or language-dependent API transport.
The React review skill guided one-time initialization, minimal preference storage
and stable component identity; the verification skill separated DOM/API/data gates.

## 5. Supported Languages

| Locale | UI name | Direction | Intl locale | Catalog display |
| --- | --- | --- | --- | --- |
| en | English | LTR | en-US | Approved English |
| zh-CN | 简体中文 | LTR | zh-CN | Approved Chinese, else English |
| ar | العربية | RTL | ar-MA | Approved English fallback |
| fr | Français | LTR | fr-FR | Approved English fallback |

English is deterministic default and fallback, not navigator/IP detection.
Only these exact four values are accepted. Unsupported, differently cased, path-
shaped, prototype or HTML-shaped preferences cannot select/import resources.

## 6. Language Switcher

One reusable native select is present in MainLayout, AuthLayout and
AuthenticatedLayout. Native language names have lang/dir annotations; label
association, focus-visible outline, selected value and keyboard semantics remain.
Public/auth/account headers wrap on mobile; French expansion is not clipped.
Chrome Home/ArrowDown selection and retained focus passed. Switching keeps the
document, route/query/hash and input nodes; it does not reload or navigate.
Serialized pending requests skip obsolete choices and persist only the latest
successful one. Delayed transitions and rollback are unit tested.

## 7. Persistence

Key: `unishop.locale`; only a supported language string is written. Reads and
writes may fail without crashing presentation. If writes are blocked, the active
choice works but cannot be retained reliably for a future reload. Missing/invalid storage defaults
to English, without writing a default on first visit. Unrelated keys are retained.
Chinese/Arabic refresh passed with the saved locale applied before the first
visible React content. A real browser with deliberately blocked preference reads/
writes still defaults and switches correctly. Logout/session/account transitions
do not touch the preference. Private credentials, profiles, evidence or Blobs are
not persisted with it.

## 8. Translation Resource Structure

Seven namespaces: common, auth, profile, verification, products, catalog,
validation. Exactly 28 JSON files, four complete locale sets.
295 semantic keys per locale; physical counts differ legitimately with plurals:
English 297, Chinese 295, Arabic 305, French 299. Six Arabic categories and the
French many category are present. Tests validate semantic parity, namespace
availability, nonempty string values, UTF-8, duplicate keys, placeholders and
valid locale plural categories. No English-filled alternate resource sets.
English fallback is separately tested for resilience, not counted as coverage.
Normal i18next CustomTypeOptions plus strictKeyChecks type keys. Compile-only
negative fixtures reject misspellings, nonexistent namespaces and defaultValue
bypasses. No custom code-generation/type framework.

## 9. Translation Coverage

The coverage plan was recorded before extensive UI changes.

| Area | Actual coverage and limits | Namespace / verification |
| --- | --- | --- |
| Shared shell | Navigation, auth actions, loading, avatar, progress, fields, generic metadata | common; AST + component/Chrome |
| Login | Existing credentials, show/hide, errors, links, logout warning | auth/validation; preserved-state tests |
| Signup/phone/forgot/reset | Existing page headings only; no invented forms | auth; TS/parity/AST |
| Password change/email UI | No reachable form; backend retained | Not implemented frontend |
| Development phone test | Existing fake register/poll/resend/OTP/status/count/errors | verification/validation; original + new tests |
| Profiles | Own/edit/public, onboarding steps, full email/phone phrases, dates | profile; original + i18n tests |
| Seller verification | Private instructions, challenge/time, evidence fields, statuses, renewal/immutable/rejection/success/error | verification; original + preservation tests |
| Catalog | Directory, city/category labels/loading/retry/retired choices; names from API only | catalog; original + formatting tests |
| Product core | Create/edit/list/detail, status/actions, conditions, dates and CNY | products; original + Chrome/payload tests |
| Product images | Constraints, upload/order/cover/delete, selection, private/public preview/a11y/errors/counts | products; original + Blob/Chrome tests |
| Admin | Unrouted scaffolds, no actual frontend dashboard/review/catalog workflow | Not implemented; not falsely certified |
| Validation/errors | Owned schema/helper categories mapped on render; unknown values safely localized | validation; negative tests |
| Toast/dialog/confirmation | Existing inline alerts/status/success text; no implemented modal/toast workflow | Covered inline; scaffold dialogs not invented |
| Empty/loading/a11y | All reachable application-owned JSX and human attributes reviewed | AST, TS, parity, component tests |
| User/catalog content | Original names, bios, descriptions, rejection feedback and approved catalog names | Not automatically translated |

Reachable screen files: auth Login, SignUp, PhoneVerification, ForgotPassword,
ResetPassword; dev LocalPhoneVerification; public Home, PublicProfile,
ProductDetails, Categories, Safety, Terms, Privacy, NotFound; seller AddProduct,
EditProduct, SellerProducts, SellerVerification; shared Onboarding, Profile,
EditProfile. All are represented in the manifest below.

## 10. RTL Implementation

Root HTML lang/dir reflect the registry; non-Arabic returns to LTR. Directional
margin/inset utilities use ms/me/end; body text-align:start; Latin password input
uses direction-aware reserved reveal-control padding. Native flex/grid inherit
RTL, headers wrap, and image list data order is not reversed or mutated.
Back/next controls are text, not incorrectly mirrored icons. Arabic image labels
mean earlier/later while deltas/order remain unchanged. Legacy English left/right
labels retain existing semantics. Photos, brand glyphs and non-directional icons
are not transformed. UGC uses auto direction/bdi, identifiers/credentials/OTP/
challenge/price input stay LTR. There are no real sidebars/admin tables/modals to
claim verified. Chrome 1280 and 390-pixel views passed no horizontal overflow.

## 11. Localization Quality

English preserves existing copy and contract terminology. Simplified Chinese,
Modern Standard Arabic (not Darija) and standard French have real translations,
not runtime English substitution. Native font stacks render Chinese glyphs and
joined Arabic without downloaded assets. Eight empty-login screenshots (all four
languages, mobile/desktop) were visually inspected; French wrapping and Arabic
password-control placement are usable. Proper names, format identifiers, CNY/
JPEG/PNG/WebP/MiB, numeric progress notation and developer `phone_verified=true`
are intentional exceptions. Native file-control/dialog text belongs to the browser/OS,
not application translations; application file labels/instructions/actions are localized.
Catalog fallback/content are explicitly separate.
Independent native-speaker editorial and assistive-tech QA are still advisable;
this is not a linguistic certification. Original seller-approved/category copy
that predates listing availability is translated faithfully, not a new policy.

## 12. Formatting

Intl.NumberFormat formats display CNY and numbers. Decimal input/payload remains
an ASCII string, currency remains CNY, no exchange or business floating-point
calculation. Formatting rejects malformed display values safely. Intl.DateTimeFormat
uses the selected locale. Profile/challenge dates retain their existing browser-local
semantics. Owner-list timestamps retain the original UTC clock (including naive
MySQL UTC datetimes) and visibly label UTC, with four added boundary regressions.
No stored timestamp mutation or arbitrary business timezone conversion. Empty/invalid and day-boundary
cases pass. Machine-readable time dateTime remains the original ISO timestamp.
Counts/full sentences use interpolation/plural keys; Arabic 0/1/2/3/10/11/100/
101/102 are tested. Formatted mixed-direction values are isolated.

## 13. User Content Policy

Seller titles/descriptions, display names, biographies and admin-written feedback
stay original and React-escaped. They are not translation keys or sent elsewhere.
Catalog selection uses only returned approved name_zh/name_en; identifiers, slugs,
IDs/relationships and active-state rules remain unchanged. Arabic/French use
English until authorized catalog translations exist. The profile DTO supplies
only an English city name; that remains fallback rather than causing new requests.
No duplicate city list, translation table, new column or AI translation.

## 14. Validation and Error Localization

Thresholds, normalization, allowed enums, upload types/bytes/dimensions and API
schema validation are unchanged. Existing safe helper/schema English categories
map to semantic keys at presentation, so errors already shown change with locale.
Known API codes/statuses are normalized by existing safe API helpers first.
No brittle matching of arbitrary raw backend prose. Unknown error values use a
localized generic fallback; unknown validation categories use a generic field
message. SQL/errors/storage paths/JWT/evidence details never become raw visible
copy. Stable codes are not available for every endpoint; exact specificity for
future new categories requires updating the owned adapter or public-code mapping.
No backend error-contract rewrite.

## 15. Authentication Regression

Memory token/user/session version, refresh coordinator, cookies, CSRF/origin
rules, roles and guards are unchanged. Locale modules import no auth/client/cache
owner. Component tests verify zero login/logout/refresh/request side effects and
unchanged memory auth/private cache/cookies during switching. Chrome verifies
unchanged XHR request counts while typing login and authenticated forms/previews.
Actual logout revokes/removes private Blobs and preserves only the locale key;
account B retains Arabic but cannot access A's image view. Full legacy auth/session
tests and 1,388 backend cases pass, including late-response/session fences.
A full page refresh legitimately bootstraps/rotates a session; locale changes do not.

## 16. Product and Media Regression

Create/edit retain values, original reset dependencies, synchronous submit guard,
changed-only PATCH and unchanged enum/decimal/catalog payloads. Image mutations
keep their busy guard, complete-ref ordering, cover rules, archived cleanup,
authorization and compensation. Locale is not in private Blob effect/query keys.
Tests prove DOM/file/Blob identity, no image refetch/object-URL recreation or media
mutation on switching. Original Blob cleanup/account/late-result tests pass.
Chrome uploads two safe synthetic photos, reorders in RTL, publishes and reads
the public gallery while preserving escaped original UGC and exact CNY string.
Private evidence never becomes public; full HTTP and backend security suites retain
owner/admin/evidence-audit/visibility controls.

## 17. Security Tests

Negative locale/path/HTML/prototype preferences, blocked storage, unknown SQL/path/
token-shaped errors, malicious interpolation/a11y, HTML-shaped mixed-script product
content, LTR identifiers and bidi isolation pass. Only the locale is persisted;
private caches/auth are unchanged on switching and evicted on logout/account
change. No unsafe translation HTML, arbitrary resource import, credentials in
URLs, storage-key exposure or third-party content translation. Existing account/
CSRF/lifecycle/upload/privacy tests remain. This is regression evidence, not an
OWASP compliance certification or a production penetration test.

## 18. Frontend Tests

Historical baseline 304 tests/19 files. Fresh final: **367 passed in 22 files**,
**63 new targeted tests**, zero failures/skips. New files: i18n-core (41),
i18n-ui (19), i18n-inventory (3). All original 304 cases retained, not removed/
skipped/weakened. Four older files update only catalog/condition/date/bdi/type-label
presentation expectations; escaping, authorization, payload, busy-guard and
machine-readable-time assertions remain, with new bdi checks. Test setup resets
only locale and its preference, not unrelated auth/storage state.

## 19. Backend Compatibility

Fresh full suite **1,388 passed in 140.71s**, one inherited FastAPI/Starlette
httpx TestClient deprecation warning. Backend app/API/security, database/schema
and migrations have **zero changed files**. Real MySQL 9.4.0, database
`unishop_china`; target MySQL 8 is not certified. Live HTTP security/health/auth/
profile/seller/catalog/product/image/password workflow passed with exact cleanup.
Alembic current `a10b2c3d4e5f (head)`; check: no new upgrade operations.
No development upgrade/downgrade/reseed, no new migrations. Python compile,
Ruff --no-cache, pip check and pip-audit pass.

## 20. Static Quality

Application TypeScript and negative-key fixture compilation pass. ESLint passes.
Production Vite 8.1.5 build passes, no build warnings. JSON/UTF-8/duplicate/parity/
placeholder/plural and JSX inventory checks pass. Python helper compile/Ruff pass.
Cached Ruff initially panicked on corrupt package cache; --no-cache passed all
rules, no disabling or package upgrade.

An isolated committed-HEAD frontend build used the same installed versions;
no old lock version changed. Node gzip measurements, summed per chunk:

| Metric | Committed HEAD | Phase 11A | Change |
| --- | ---: | ---: | ---: |
| All JS raw bytes | 548889 | 672913 | +124024 |
| All JS gzip bytes | 181957 | 220294 | +38337 |
| Initial static graph raw bytes | 459858 | 581561 | +121703 |
| Initial static graph gzip bytes | 144769 | 183097 | +38328 |
| JS chunks | 37 | 39 | +2 |

Vite's gzip presentation differs slightly from Node gzip settings. Figures compare
equivalent builds, not approximate old artifact sizes. Four bundled locales trade
about 38 KB compressed startup cost for no remote translation runtime/race.
Engine-only fresh-instance initialization with the actual 28 resources and React
plugin (25 runs per locale, 100 total, warm Node 24 modules) measured min
0.0145 ms, median 0.0260 ms, max 2.1589 ms.
This excludes JSON/module loading, storage reads, DOM work and cold browser navigation;
Chrome separately verifies the saved locale is applied before first visible render.
Chrome switch protocol + two-animation-frame round trips measured 10.95–63.45 ms,
not pure handler timings, LCP/CLS or an exhaustive benchmark. DOM identities stay
stable; French mobile header wrapping is expected responsive expansion. No heavy
framework/font download or premature lazy-localization infrastructure.

## 21. Real Browser

Available: real Chrome headless with a fresh temporary profile. **74 i18n checks +
50 HTTP synthetic setup checks, 124 total** passed. English default, four desktop/
mobile login layouts, four public product layouts, lang/dir/title, query/hash/
document/input stability, native keyboard focus, rapid latest choice, Chinese/
Arabic refresh before first visible render, malicious preference and blocked
storage, typed login/product values, selected images, private Blob stability,
RTL reorder (actual server ref order), publish/public content/metadata, localized
owner-list UTC clocks, logout/revocation and account B
denial are covered. Screenshots captured only empty login screens and inspected
for all four languages; no credentials, personal evidence or private photos.
The harness stops owned Vite/Uvicorn/Chrome and cleans synthetic DB/temp media.

Four harness failures were fixed: two CDP by-value serialization failures for an
input node, same-document Page.navigate instead of a proven new-document reload,
and a test link absent from the public shell (corrected via the existing owner shell).
No app/security failure was concealed. Every failed run also verified cleanup/
16-table preservation. Screenshots and the temporary committed-HEAD bundle
comparison remain outside the repository, not staged or counted as user artifacts.
Chrome only: Safari/Firefox/mobile-device/native screen-reader and every contingent
UI state are not certified. jsdom tests are not presented as browser checks.

## 22. Dependencies

Installed exact production i18next 26.4.4 and react-i18next 17.0.16; transitive
html-parse-stringify 4.0.1 and use-sync-external-store 1.7.0. Compatible installed
React 19.2.7, TypeScript 6.0.3, Vite 8.1.5. Tailwind remains 3.4.19.
Manifest/root lock match; 330 present package entries match installed versions;
no existing lock version changed. ci dry-run --ignore-scripts passes; actual
installation/build verified separately, not a claim of a clean ci reinstall.
Normal HTTPS with Node --use-system-ca, registry https://registry.npmjs.org/,
strict-ssl=true; no NODE_TLS_REJECT_UNAUTHORIZED bypass or insecure registry.

Production npm audit: **0**. Full audit: **5 High / 2 Moderate affected build nodes**,
no new i18n findings. Two inherited root advisories:
- [braces GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm):
  installed 3.0.3, affected <=3.0.3, stack-exhaustion DoS, High/CVSS 7.5; affects
  braces/chokidar/micromatch/fast-glob/Tailwind build chain.
- [postcss-selector-parser GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf):
  installed 6.1.4, affected <7.1.6, quadratic CPU exhaustion, Moderate/CVSS 5.9;
  affects parser/postcss-nested build chain.

Full audit exit 1 is documented, not hidden as a clean audit. Tailwind migration/
uncontrolled overrides/force fixes are out of scope; a separate verified migration
task is needed before production. Python pip-audit: no known vulnerabilities.

## 23. Architecture Review

One instance/registry/controller, no duplicate locale Zustand/context stores, no
locale-keyed remounts, auth/provider/query changes or circular i18n imports.
Static imports bundle known four-resource sets. Typed enum/message adapters and
shared Intl helpers avoid page-specific locale branches. A helper-body comparison
found changes only to router page/developmentPage loading UI; imperative login/
product/seller helper function declarations stayed unchanged. The dev polling
timeout state now uses an owned semantic category at render, preserving timing/
abort/security logic. Existing effect/reset/version/busy dependencies were reviewed.
No unnecessary refactor, Tailwind migration, new backend localization, feed or
search. Remaining safe English adapters are intentional compatibility boundaries,
not untranslated screen copy.

## 24. Documentation

Created this 30-section report, coverage plan/matrix and exhaustive change manifest.
Updated current status, frontend architecture, frontend README, documentation index
and root README. Complete Phase 1–10 reports remain untouched. Commands below,
fallback/content/error/RTL/auth/data boundaries, exact gates and limitations are
documented. No final-adversarial closure or production-ready claim.

## 25. Production / Future Limitations

Production remains NO: inherited build advisories, unconfigured private production
object/evidence storage and operations, distributed controls/capacity, providers/
secrets/TLS/recovery, target MySQL 8 and Docker/NGINX runtime verification. These
are inherited release blockers, not work expanded into this presentation task.
Arabic/French catalog names need approved data; profile city has English-only DTO.
No server-message localization middleware or localized SEO routes. Native-speaker
editorial/assistive-tech and additional browsers/devices remain future QA. Some
legacy category/approved-seller marketing copy predates listing features; retained
faithfully, not a claim that its dated wording now defines business authorization.
No future browse/search/favorites/chat/payments implementation or policy invention.

## 26. Files Changed

Every Phase 11A file is listed individually below. Status M = tracked modified,
A = new untracked file (not staged). Reasons/verification are grouped by scope
but each file has its own row. The 13 unrelated artifacts are excluded.

### Source / presentation (56)

| Status | File | Why | Verification |
| --- | --- | --- | --- |
| M | [frontend/index.html](../../frontend/index.html) | Declare default dir/static description; runtime synchronizes localized metadata. | Chrome root/title/no-flash checks; TS/build |
| M | [frontend/src/app/router.tsx](../../frontend/src/app/router.tsx) | Translate Suspense fallback through Spinner, retain all route objects/lazy behavior. | router/auth tests; helper-body review; build |
| M | [frontend/src/components/auth/AuthActions.tsx](../../frontend/src/components/auth/AuthActions.tsx) | Translate existing auth/loading/credentials UI and safe validation; logical spacing/LTR input. | auth/session + i18n form-state/error tests; Chrome |
| M | [frontend/src/components/auth/AuthLoading.tsx](../../frontend/src/components/auth/AuthLoading.tsx) | Translate existing auth/loading/credentials UI and safe validation; logical spacing/LTR input. | auth/session + i18n form-state/error tests; Chrome |
| M | [frontend/src/components/auth/LoginForm.tsx](../../frontend/src/components/auth/LoginForm.tsx) | Translate existing auth/loading/credentials UI and safe validation; logical spacing/LTR input. | auth/session + i18n form-state/error tests; Chrome |
| M | [frontend/src/components/common/Avatar.tsx](../../frontend/src/components/common/Avatar.tsx) | Localized a11y/loading/progress/validation boundary or auto-direction input; no feature logic. | profile/auth/i18n unit/AST tests; TS/lint/build |
| M | [frontend/src/components/common/FormField.tsx](../../frontend/src/components/common/FormField.tsx) | Localized a11y/loading/progress/validation boundary or auto-direction input; no feature logic. | profile/auth/i18n unit/AST tests; TS/lint/build |
| M | [frontend/src/components/common/Input.tsx](../../frontend/src/components/common/Input.tsx) | Localized a11y/loading/progress/validation boundary or auto-direction input; no feature logic. | profile/auth/i18n unit/AST tests; TS/lint/build |
| M | [frontend/src/components/common/ProgressSteps.tsx](../../frontend/src/components/common/ProgressSteps.tsx) | Localized a11y/loading/progress/validation boundary or auto-direction input; no feature logic. | profile/auth/i18n unit/AST tests; TS/lint/build |
| M | [frontend/src/components/common/Spinner.tsx](../../frontend/src/components/common/Spinner.tsx) | Localized a11y/loading/progress/validation boundary or auto-direction input; no feature logic. | profile/auth/i18n unit/AST tests; TS/lint/build |
| M | [frontend/src/components/common/Textarea.tsx](../../frontend/src/components/common/Textarea.tsx) | Localized a11y/loading/progress/validation boundary or auto-direction input; no feature logic. | profile/auth/i18n unit/AST tests; TS/lint/build |
| M | [frontend/src/components/layout/AuthLayout.tsx](../../frontend/src/components/layout/AuthLayout.tsx) | Global selector, translated shell/nav/marketing labels and logical mobile/RTL layout. | i18n-ui + Chrome focus/route/layout; auth regression |
| M | [frontend/src/components/layout/AuthenticatedLayout.tsx](../../frontend/src/components/layout/AuthenticatedLayout.tsx) | Global selector, translated shell/nav/marketing labels and logical mobile/RTL layout. | i18n-ui + Chrome focus/route/layout; auth regression |
| M | [frontend/src/components/layout/MainLayout.tsx](../../frontend/src/components/layout/MainLayout.tsx) | Global selector, translated shell/nav/marketing labels and logical mobile/RTL layout. | i18n-ui + Chrome focus/route/layout; auth regression |
| M | [frontend/src/components/products/OwnerProductImage.tsx](../../frontend/src/components/products/OwnerProductImage.tsx) | Localize preview/alt text; preserve original Blob effect and dependencies. | original image tests, new Blob identity/account tests, Chrome |
| M | [frontend/src/components/products/ProductForm.tsx](../../frontend/src/components/products/ProductForm.tsx) | Localize product/media controls/errors/dynamic counts; preserve forms, queries and commands. | product/image + i18n state/payload/security tests; Chrome; TS/build |
| M | [frontend/src/components/products/ProductImageManager.tsx](../../frontend/src/components/products/ProductImageManager.tsx) | Localize product/media controls/errors/dynamic counts; preserve forms, queries and commands. | product/image + i18n state/payload/security tests; Chrome; TS/build |
| M | [frontend/src/components/products/ProductStatusBadge.tsx](../../frontend/src/components/products/ProductStatusBadge.tsx) | Localize product/media controls/errors/dynamic counts; preserve forms, queries and commands. | product/image + i18n state/payload/security tests; Chrome; TS/build |
| M | [frontend/src/components/products/PublicProductGallery.tsx](../../frontend/src/components/products/PublicProductGallery.tsx) | Localize product/media controls/errors/dynamic counts; preserve forms, queries and commands. | product/image + i18n state/payload/security tests; Chrome; TS/build |
| M | [frontend/src/components/profiles/CitySelect.tsx](../../frontend/src/components/profiles/CitySelect.tsx) | Localize profile/catalog/onboarding labels/errors/dates; original content auto-isolated, no state reset. | profile/catalog + i18n tests; AST/TS/lint/build |
| M | [frontend/src/components/profiles/ProfileForm.tsx](../../frontend/src/components/profiles/ProfileForm.tsx) | Localize profile/catalog/onboarding labels/errors/dates; original content auto-isolated, no state reset. | profile/catalog + i18n tests; AST/TS/lint/build |
| M | [frontend/src/components/profiles/ProfileGate.tsx](../../frontend/src/components/profiles/ProfileGate.tsx) | Localize profile/catalog/onboarding labels/errors/dates; original content auto-isolated, no state reset. | profile/catalog + i18n tests; AST/TS/lint/build |
| M | [frontend/src/main.tsx](../../frontend/src/main.tsx) | Initialize the singleton locale layer before visible React render. | Chrome saved-locale first-render checks; build |
| M | [frontend/src/pages/auth/ForgotPasswordPage.tsx](../../frontend/src/pages/auth/ForgotPasswordPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/auth/LoginPage.tsx](../../frontend/src/pages/auth/LoginPage.tsx) | Translate existing auth/loading/credentials UI and safe validation; logical spacing/LTR input. | auth/session + i18n form-state/error tests; Chrome |
| M | [frontend/src/pages/auth/PhoneVerificationPage.tsx](../../frontend/src/pages/auth/PhoneVerificationPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/auth/ResetPasswordPage.tsx](../../frontend/src/pages/auth/ResetPasswordPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/auth/SignUpPage.tsx](../../frontend/src/pages/auth/SignUpPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/dev/LocalPhoneVerificationPage.tsx](../../frontend/src/pages/dev/LocalPhoneVerificationPage.tsx) | Translate fake SMS workflow/status/plural errors; preserve validation/poll/abort/API behavior. | all original fake-phone cases + i18n core; TS/lint |
| M | [frontend/src/pages/public/CategoriesPage.tsx](../../frontend/src/pages/public/CategoriesPage.tsx) | Translate directory/detail labels; approved catalog/Intl CNY, escaped original content and safe errors. | catalog/product/profile + four-locale XSS tests; Chrome |
| M | [frontend/src/pages/public/HomePage.tsx](../../frontend/src/pages/public/HomePage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/public/NotFoundPage.tsx](../../frontend/src/pages/public/NotFoundPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/public/PrivacyPage.tsx](../../frontend/src/pages/public/PrivacyPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/public/ProductDetailsPage.tsx](../../frontend/src/pages/public/ProductDetailsPage.tsx) | Translate directory/detail labels; approved catalog/Intl CNY, escaped original content and safe errors. | catalog/product/profile + four-locale XSS tests; Chrome |
| M | [frontend/src/pages/public/PublicProfilePage.tsx](../../frontend/src/pages/public/PublicProfilePage.tsx) | Localize profile/catalog/onboarding labels/errors/dates; original content auto-isolated, no state reset. | profile/catalog + i18n tests; AST/TS/lint/build |
| M | [frontend/src/pages/public/SafetyPage.tsx](../../frontend/src/pages/public/SafetyPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/public/TermsPage.tsx](../../frontend/src/pages/public/TermsPage.tsx) | Translate existing reachable title-only screen; no new form/content/feature. | AST/semantic key parity; TS/lint/build |
| M | [frontend/src/pages/seller/AddProductPage.tsx](../../frontend/src/pages/seller/AddProductPage.tsx) | Localize existing listing copy/actions/errors/enum/date display without changing ownership or commands. | original product/security + i18n tests; Chrome; TS/lint/build |
| M | [frontend/src/pages/seller/EditProductPage.tsx](../../frontend/src/pages/seller/EditProductPage.tsx) | Localize existing listing copy/actions/errors/enum/date display without changing ownership or commands. | original product/security + i18n tests; Chrome; TS/lint/build |
| M | [frontend/src/pages/seller/SellerProductsPage.tsx](../../frontend/src/pages/seller/SellerProductsPage.tsx) | Localize existing listing copy/actions/errors/enum/date display without changing ownership or commands. | original product/security + i18n tests; Chrome; TS/lint/build |
| M | [frontend/src/pages/seller/SellerVerificationPage.tsx](../../frontend/src/pages/seller/SellerVerificationPage.tsx) | Full localized evidence/status/challenge messages; original file state and immutable actions retained. | seller verification tests + i18n evidence preservation; backend security |
| M | [frontend/src/pages/shared/EditProfilePage.tsx](../../frontend/src/pages/shared/EditProfilePage.tsx) | Localize profile/catalog/onboarding labels/errors/dates; original content auto-isolated, no state reset. | profile/catalog + i18n tests; AST/TS/lint/build |
| M | [frontend/src/pages/shared/OnboardingPage.tsx](../../frontend/src/pages/shared/OnboardingPage.tsx) | Localize profile/catalog/onboarding labels/errors/dates; original content auto-isolated, no state reset. | profile/catalog + i18n tests; AST/TS/lint/build |
| M | [frontend/src/pages/shared/ProfilePage.tsx](../../frontend/src/pages/shared/ProfilePage.tsx) | Localize profile/catalog/onboarding labels/errors/dates; original content auto-isolated, no state reset. | profile/catalog + i18n tests; AST/TS/lint/build |
| M | [frontend/src/styles/index.css](../../frontend/src/styles/index.css) | Logical alignment, Arabic/CJK system fallback and LTR-password reveal spacing. | Chrome desktop/mobile visual/no-overflow; lint/build |
| A | [frontend/src/components/layout/LanguageSwitcher.tsx](../../frontend/src/components/layout/LanguageSwitcher.tsx) | One accessible native global selector, latest-safe selection and visible failure message. | i18n-ui + Chrome focus/route/layout; auth regression |
| A | [frontend/src/i18n/controller.ts](../../frontend/src/i18n/controller.ts) | Serialized latest-choice transitions and rollback; no auth/cache effects. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/formatters.ts](../../frontend/src/i18n/formatters.ts) | Shared display-only CNY/date/number and approved catalog-name selection. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/index.ts](../../frontend/src/i18n/index.ts) | One synchronous engine and root lang/dir/static metadata synchronization. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/labels.ts](../../frontend/src/i18n/labels.ts) | Typed product condition/status and verification-status key mappings. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/languages.ts](../../frontend/src/i18n/languages.ts) | Single authoritative four-language/Intl/direction/catalog registry. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/messages.ts](../../frontend/src/i18n/messages.ts) | Map owned safe helper/schema categories; hide unknown/raw error values. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/persistence.ts](../../frontend/src/i18n/persistence.ts) | Centralized allowlisted unishop.locale reads/writes with failure tolerance. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/resources.ts](../../frontend/src/i18n/resources.ts) | Static local imports of exactly four complete seven-namespace sets. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/types.d.ts](../../frontend/src/i18n/types.d.ts) | i18next strict semantic key/type augmentation. | i18n-core/ui/inventory; app and negative-key TS; lint/build |
| A | [frontend/src/i18n/useAppTranslation.ts](../../frontend/src/i18n/useAppTranslation.ts) | Subscribe UI to the singleton engine without auth/provider ownership. | i18n-core/ui/inventory; app and negative-key TS; lint/build |

### Translations (28)

| Status | File | Why | Verification |
| --- | --- | --- | --- |
| A | [frontend/src/i18n/locales/ar/auth.json](../../frontend/src/i18n/locales/ar/auth.json) | Real ar auth translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/ar/catalog.json](../../frontend/src/i18n/locales/ar/catalog.json) | Real ar catalog translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/ar/common.json](../../frontend/src/i18n/locales/ar/common.json) | Real ar common translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/ar/products.json](../../frontend/src/i18n/locales/ar/products.json) | Real ar products translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/ar/profile.json](../../frontend/src/i18n/locales/ar/profile.json) | Real ar profile translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/ar/validation.json](../../frontend/src/i18n/locales/ar/validation.json) | Real ar validation translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/ar/verification.json](../../frontend/src/i18n/locales/ar/verification.json) | Real ar verification translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/en/auth.json](../../frontend/src/i18n/locales/en/auth.json) | Real en auth translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/en/catalog.json](../../frontend/src/i18n/locales/en/catalog.json) | Real en catalog translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/en/common.json](../../frontend/src/i18n/locales/en/common.json) | Real en common translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/en/products.json](../../frontend/src/i18n/locales/en/products.json) | Real en products translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/en/profile.json](../../frontend/src/i18n/locales/en/profile.json) | Real en profile translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/en/validation.json](../../frontend/src/i18n/locales/en/validation.json) | Real en validation translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/en/verification.json](../../frontend/src/i18n/locales/en/verification.json) | Real en verification translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/fr/auth.json](../../frontend/src/i18n/locales/fr/auth.json) | Real fr auth translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/fr/catalog.json](../../frontend/src/i18n/locales/fr/catalog.json) | Real fr catalog translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/fr/common.json](../../frontend/src/i18n/locales/fr/common.json) | Real fr common translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/fr/products.json](../../frontend/src/i18n/locales/fr/products.json) | Real fr products translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/fr/profile.json](../../frontend/src/i18n/locales/fr/profile.json) | Real fr profile translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/fr/validation.json](../../frontend/src/i18n/locales/fr/validation.json) | Real fr validation translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/fr/verification.json](../../frontend/src/i18n/locales/fr/verification.json) | Real fr verification translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/zh-CN/auth.json](../../frontend/src/i18n/locales/zh-CN/auth.json) | Real zh-CN auth translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/zh-CN/catalog.json](../../frontend/src/i18n/locales/zh-CN/catalog.json) | Real zh-CN catalog translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/zh-CN/common.json](../../frontend/src/i18n/locales/zh-CN/common.json) | Real zh-CN common translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/zh-CN/products.json](../../frontend/src/i18n/locales/zh-CN/products.json) | Real zh-CN products translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/zh-CN/profile.json](../../frontend/src/i18n/locales/zh-CN/profile.json) | Real zh-CN profile translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/zh-CN/validation.json](../../frontend/src/i18n/locales/zh-CN/validation.json) | Real zh-CN validation translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |
| A | [frontend/src/i18n/locales/zh-CN/verification.json](../../frontend/src/i18n/locales/zh-CN/verification.json) | Real zh-CN verification translations, complete semantic keys/placeholders/plurals. | i18n-core + inventory JSON/UTF-8/duplicate/parity tests; TS/Chrome |

### Tests / verification tools (12)

| Status | File | Why | Verification |
| --- | --- | --- | --- |
| M | [frontend/tests/setup.ts](../../frontend/tests/setup.ts) | Isolate locale tests, remove only locale preference, preserve unrelated state. | 367-test full regression |
| M | [frontend/tests/unit/catalog.test.tsx](../../frontend/tests/unit/catalog.test.tsx) | Update only changed display expectations, retaining payload/privacy/security assertions. | all 304 original tests retained; full 367; added bdi assertions |
| M | [frontend/tests/unit/local-phone-verification.test.tsx](../../frontend/tests/unit/local-phone-verification.test.tsx) | Update only changed display expectations, retaining payload/privacy/security assertions. | all 304 original tests retained; full 367; added bdi assertions |
| M | [frontend/tests/unit/product-pages.test.tsx](../../frontend/tests/unit/product-pages.test.tsx) | Update only changed display expectations, retaining payload/privacy/security assertions. | all 304 original tests retained; full 367; added bdi assertions |
| M | [frontend/tests/unit/seller-verification.test.tsx](../../frontend/tests/unit/seller-verification.test.tsx) | Update only changed display expectations, retaining payload/privacy/security assertions. | all 304 original tests retained; full 367; added bdi assertions |
| A | [frontend/scripts/inventory-i18n.mjs](../../frontend/scripts/inventory-i18n.mjs) | Read-only reachable-module AST review aid; documented exceptions, no coverage overclaim. | i18n-inventory AST test; ESLint |
| A | [frontend/scripts/verify-i18n-browser.py](../../frontend/scripts/verify-i18n-browser.py) | Real Chrome/locale scenarios reuse unchanged synthetic HTTP/MySQL cleanup harness. | 124 live checks incl. 74 i18n; Python compile/Ruff |
| A | [frontend/tests/typecheck/i18n-keys.ts](../../frontend/tests/typecheck/i18n-keys.ts) | Compile-only negative semantic-key/namespace/defaultValue fixtures. | tsconfig.i18n-tests.json compilation |
| A | [frontend/tests/unit/i18n-core.test.ts](../../frontend/tests/unit/i18n-core.test.ts) | Registry/storage/fallback/parity/plural/format/controller/error negative tests. | 63 targeted cases; full 367 tests; ESLint |
| A | [frontend/tests/unit/i18n-inventory.test.ts](../../frontend/tests/unit/i18n-inventory.test.ts) | UTF-8/duplicate resources, reviewed JSX exceptions and dependency-boundary tests. | 63 targeted cases; full 367 tests; ESLint |
| A | [frontend/tests/unit/i18n-ui.test.tsx](../../frontend/tests/unit/i18n-ui.test.tsx) | Four-language state/auth/media/interpolation/bidi/a11y component security tests. | 63 targeted cases; full 367 tests; ESLint |
| A | [frontend/tsconfig.i18n-tests.json](../../frontend/tsconfig.i18n-tests.json) | Reuse existing strict app compiler settings for compile-only negative key fixtures. | tsc -p tsconfig.i18n-tests.json --noEmit |

### Dependencies (2)

| Status | File | Why | Verification |
| --- | --- | --- | --- |
| M | [frontend/package-lock.json](../../frontend/package-lock.json) | Record four new packages only; preserve every existing locked version. | 330 installed entries match; full/prod audits; build |
| M | [frontend/package.json](../../frontend/package.json) | Pin only the two necessary compatible production i18n packages. | installed versions, manifest/lock consistency, ci dry-run, audits |

### Documentation (6)

| Status | File | Why | Verification |
| --- | --- | --- | --- |
| M | [README.md](../../README.md) | Add current Phase 11A scope, evidence, commands/boundaries or documentation link; retain history. | manifest/claim/relative-link review; Git whitespace |
| M | [documentation/CURRENT_PROJECT_STATUS.md](../../documentation/CURRENT_PROJECT_STATUS.md) | Add current Phase 11A scope, evidence, commands/boundaries or documentation link; retain history. | manifest/claim/relative-link review; Git whitespace |
| M | [documentation/README.md](../../documentation/README.md) | Add current Phase 11A scope, evidence, commands/boundaries or documentation link; retain history. | manifest/claim/relative-link review; Git whitespace |
| M | [documentation/architecture/frontend-architecture.md](../../documentation/architecture/frontend-architecture.md) | Add current Phase 11A scope, evidence, commands/boundaries or documentation link; retain history. | manifest/claim/relative-link review; Git whitespace |
| M | [frontend/README.md](../../frontend/README.md) | Add current Phase 11A scope, evidence, commands/boundaries or documentation link; retain history. | manifest/claim/relative-link review; Git whitespace |
| A | [documentation/phases/PHASE_11A_INTERNATIONALIZATION.md](../../documentation/phases/PHASE_11A_INTERNATIONALIZATION.md) | Complete 30-section implementation/coverage/gate/change report. | manifest/claim/relative-link review; Git whitespace |

## 27. Data and Artifact Preservation

No schema or legitimate-record change required. All 16 ordered table count/
SHA-256 fingerprints match the previously verified stable development baseline.
Each HTTP/browser attempt independently compared before/after fingerprints and
cleaned its exact random synthetic namespace, private evidence/media temp trees
and owned servers. Report-only media audit: 0 image rows, issues=[].
Fingerprints cover records, not internal auto-increment counters advanced by
normal synthetic inserts. No destructive migration/development downgrade.
All 13 expected PDF/script/render files have matching starting/final SHA-256 hashes.
Unrelated artifacts remain untracked and untouched. Build/visual review scratch
folders are outside the repo; no personal document or private-image screenshots.

## 28. Final Git State

HEAD `00be821eeb956d19e460e33732bf608f1802d73d`. Branch/tracking unchanged.
57 modified tracked + 47 new Phase 11A files = 104 intended changed files.
0 staged, 0 deleted. Exactly 13 unrelated untracked artifacts preserved.
git diff --check passes; new-file whitespace/UTF-8/source/JSON checks pass.
Windows Git reports its existing LF-to-CRLF conversion warnings, not whitespace
errors; no Git line-ending configuration was changed. No commit or push created.
No resets/restores/broad adds or user-work discard. Final report is implementation
evidence for the independent audit, not permission to stage or proceed.

## 29. Final Gate Checklist

| Gate | Result |
| --- | --- |
| Four languages/default/fallback/typed keys | PASS |
| Global selector/native keyboard/route preservation | PASS |
| Safe persistence/invalid and blocked storage/rapid selection | PASS |
| Arabic RTL/other LTR/mobile/bidi/identifiers | PASS |
| Existing reachable UI coverage/validation/errors | PASS within actual implementation inventory |
| Resource parity/UTF-8/duplicate/interpolation/plurals | PASS |
| Auth isolation/private caches/logout/account switch | PASS |
| Login/product/evidence/file state preservation | PASS |
| Product lifecycle/private/public images/Blob regression | PASS |
| Frontend 367/application TS/negative-key TS/ESLint/build | PASS |
| Backend 1,388/live MySQL/Uvicorn/health/Alembic no drift | PASS locally on MySQL 9.4 |
| 16-table legitimate-data/synthetic-media preservation | PASS |
| All 13 unrelated artifacts preserved | PASS |
| No backend/schema/Phase 11B/staging/commit/push | PASS |
| Production dependency/deployment/storage readiness | NO — inherited blockers |

Reproduce frontend gates from frontend/:

```powershell
npm.cmd test -- --run
npx.cmd tsc -b --pretty false
npx.cmd tsc -p tsconfig.i18n-tests.json --noEmit
npm.cmd run lint
npm.cmd run build
node.exe scripts/inventory-i18n.mjs
```

Use the trusted-CA npm commands in frontend/README.md for full/production audits.
From backend/:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe check
.\.venv\Scripts\python.exe scripts/audit_security_http.py
.\.venv\Scripts\python.exe ..\frontend\scripts\verify-i18n-browser.py
.\.venv\Scripts\python.exe -m compileall -q app alembic tests ..\frontend\scripts\verify-i18n-browser.py
.\.venv\Scripts\ruff.exe check --no-cache . ..\frontend\scripts\verify-i18n-browser.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --local
.\.venv\Scripts\python.exe scripts/audit_product_media.py
```

Development launch only (configure private .env locally, never publish secrets):

```powershell
# backend/
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
# frontend/, separate terminal
npm.cmd run dev -- --host 127.0.0.1
```

## 30. Final Verdict

Architecture, reviewed translation coverage, RTL, security/auth boundaries,
regression and existing-data preservation: sound and locally verified.
Ready for independent final adversarial audit: YES. Phase 11B is conditional on
that audit/human Git closure and a separate request. No final closure performed.

UniShop China Phase 11A Internationalization and Multilingual Foundation passed its local implementation, four-language translation, RTL, accessibility, authentication-isolation, data-integrity, security, and regression gates. Phase 11A is ready for its final adversarial audit. Production readiness is not claimed.
