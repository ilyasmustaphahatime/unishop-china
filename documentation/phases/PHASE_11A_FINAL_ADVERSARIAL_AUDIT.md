# UniShop China — Phase 11A final adversarial audit

Date: 2026-10-14. Scope: the uncommitted Phase 11A i18n implementation at
`feature/authentication`, HEAD `00be821eeb956d19e460e33732bf608f1802d73d`.
This is an independent local verification, not a production release certificate.
The original [implementation report](PHASE_11A_INTERNATIONALIZATION.md)
contains the complete 104-path implementation manifest. Earlier test numbers in
that report are historical; the results below were rerun after the audit fixes.

## 1. Executive Verdict

Audit complete: YES. Local Phase 11A gate: PASS, with the explicit external
temporary-profile exception in §22. Ready for human-reviewed Git staging/commit:
YES; nothing has been staged or committed by this audit. Backend Phase 11B may
begin only after human Git closure and a separate instruction. Production ready:
NO. Confirmed Phase 11A findings: 0 Critical, 0 High, 1 Medium (test-harness
cleanup), 3 Low (two misleading-copy groups and stale switch failure UI).
Informational limitations: inherited build advisories, unverified native-speaker
quality, non-certified assistive-technology/browser matrix, target MySQL 8 and
deployment infrastructure, and one residual synthetic Chrome temp directory.

## 2. Git Baseline

The expected branch/HEAD matched. Start: 57 modified tracked + 47 new Phase
11A files = 104 original paths, zero staged/deleted; 13 unrelated untracked
PDF/build/render artifacts. `git status`, `--short`, `-sb`, log-6, diff
stat/name-status/check and full untracked inventory were inspected. No surprise
source file or migration preceded audit changes.

## 3. Confirmed Findings

| Severity | Source/root cause and reproduction | Narrow fix and regression | Residual |
|---|---|---|---|
| Medium | `backend/scripts/audit_security_http.py`: a locked Chrome profile made `TemporaryDirectory.cleanup()` raise before owned server and synthetic DB/media cleanup. Reproduced by the first adversarial Chrome attempt; two synthetic accounts and linked rows remained until exact scoped cleanup. | Stop owned servers and clear synthetic DB/media before retrying temp-profile cleanup; bounded Windows retry, checked temp parent, explicit `browser_temp_cleanup` and check count. Rerun: 130/130 checks, DB/media/owned-server cleanup true; 1,388 backend tests and Ruff green. | First failed attempt left one outside-repo temp profile; see §22. |
| Low | `LanguageSwitcher`: an older failed locale request could display an alert while a newer choice was pending. | A failing held-promise unit test reproduced it. A latest-request counter fences stale completion; targeted and full frontend tests green. | No asynchronous network locale loader exists today; guard also covers future failure. |
| Low | Four `catalog.json` and four `verification.json` resources described listings/selling as unavailable even though Phase 9 listings exist. | Four-locale failing copy assertions, corrected text, passing parity and browser screens. | No marketplace feature or authorization changed. |
| Low | Four `auth.json` resources promised chat/payment/delivery and saved-product/deal access absent from the app. | Four-locale failing assertions, accurate login/access copy, full 387 tests and final Chrome rerun green. | Legal/commercial native-speaker review still needed. |

## 4. Architecture

Exactly one imported i18next instance and one supported-locale registry drive
the `LanguageSwitcher`, resources, safe preference and formatting helpers.
There is no locale-keyed app/router/provider remount, second language store,
remote translation service, dynamic path import or translation-controlled
authorization. Auth, products, verification, private caches, storage and DB
remain behind existing feature/service boundaries.

## 5. Supported Locales

`en`, `zh-CN`, `ar`, `fr` are the only accepted values. Unsupported,
empty, path-like, `__proto__`, `constructor`, aliases/casing, invalid Unicode,
very long strings and non-string objects fall back to English without a remote
request or crash. Blocked preference reads also select English.

## 6. Translation Integrity

Seven namespaces × four languages = 28 valid UTF-8 JSON files; 295 semantic
keys per locale. Duplicate-key, non-empty value, required-key/interpolation
parity and Arabic plural checks pass. Arabic 0, 1, 2, 3, 5, 10, 11, 21, 100,
101 were tested. Compile-only negative key/namespace/defaultValue fixtures and
strict application TypeScript pass. Key parity is not a native-language review.

## 7. Translation Coverage

Reachable shared shells, authentication/password/phone pages, profiles, seller
verification, catalog/public placeholders, listings, product creation/editing,
images, validation/errors and accessible labels use the bundled resources.
The AST-based route inventory and documented exceptions were reviewed.
Placeholder translations are not claims of a completed browse/search, chat,
payments, favorites, deals or admin UI; no Phase 11B screen was built.

## 8. Translation Quality

Chinese resources use Simplified Chinese; Arabic uses RTL Modern Standard
Arabic; French/English controls and action polarity were reviewed on actual
screens, including removal and verification states. The two false feature
promises above were corrected in all locales. Server catalog name fallbacks
remain English where Arabic/French server labels do not exist. Professional
native-speaker and legal/commercial copy certification remains outstanding.

## 9. Language Switching

Cold load and refresh for all four stored languages use the chosen language
before visible content; invalid and blocked preference states fall back safely.
Rapid `en→ar→zh-CN→fr→ar→en` settles on the last choice, with matching
`lang`, `dir`, selector and persisted value. Stale failure is fenced. Switching
does not reload, change route, or invoke auth requests. LocalStorage write
failure does not trigger a retry loop.

## 10. RTL and Bidi

Arabic sets `html[lang=ar][dir=rtl]`; the other three restore LTR. Real Chrome
checked desktop 1280px/mobile 390px, forms, public/owner pages, images and
overflow. Current screenshots show legible Arabic/French login layouts and
visible essential controls. User content uses directional isolation where
needed, while technical identifiers, password, price, OTP/challenge and URLs
retain readable LTR semantics. RTL image reordering changed server order as
labeled, not by CSS mirroring.

## 11. Authentication Isolation

Locale preference is the only new persisted key. Access token remains
memory-only; refresh cookie/CSRF/session generation and existing auth provider
stay independent. Unit and live browser checks observed no login/refresh/logout
request solely from a locale change. Logout still revokes private previews,
clears auth/private cache and retains only the nonsensitive locale.

## 12. Account Switching

Seller A's authenticated image response was held at the real Chrome DevTools
response stage (HTTP 200), while another owner preview stayed visible. After
Arabic/French switching, A logout and B login, the held bytes were released.
No A Blob URL, preview or private query returned; no credential appeared in
image URLs. A second account remained authenticated and Arabic preference
persisted. Matching unit test fences a delayed A Blob result.

## 13. Form Preservation

Focused tests cover unsaved login identifier/password and relocalized error,
profile display name/bio/city, product create title/description/exact decimal/
city/category/enum, product edit with only the changed field PATCHed, seller
challenge and selected proof, and selected image file. Switches cause no
mutation, upload, reorder or deletion. Real Chrome checks login/product forms,
file selection and private preview across the four languages.

## 14. Security

Strict locale allowlist prevents path/resource injection. React interpolation
escapes markup-shaped names and product text; no introduced dynamic HTML sink.
SQL/path/storage-key/token/stack/HTML-shaped and unknown server errors map to
safe localizable fallbacks, without raw detail leaks or account enumeration.
Only `unishop.locale` is in LocalStorage; no auth/profile/private-media data
was persisted. Backend ownership and seller authorization rules were unchanged.

## 15. Dates and Currency

All four locales format display-only CNY via `Intl`; no conversion or API
decimal mutation occurs. Zero, fractional, large, invalid/missing and exact
decimal cases are covered. The existing owner-list clock remains explicitly
UTC in browser checks for all locales; machine-readable `datetime` and API
timestamps remain unchanged. Profile/challenge date presentation remains in
its existing boundary and no expiry arithmetic was moved to translations.

## 16. Accessibility

Switcher has a native select, accessible language name/options, keyboard/focus
support and correct root language metadata. Form labels, validation
associations, live alerts and focus survival were checked; desktop/mobile RTL
did not hide controls or overflow. Automated/visual checks are not native
screen-reader, WCAG certification or a full assistive-technology matrix.

## 17. Performance

Fresh production build: 39 JS chunks, 673,366 raw/220,304 individually gzipped
bytes in total; initial HTML static graph four chunks, 582,014 raw/183,062
gzip. Pre-Phase-11A baseline archive measured 37 chunks,
548,889 raw/181,957 gzip total and 459,858 raw/144,769 gzip initial:
initial +122,156 raw/+38,293 gzip. Twenty-eight locale JSON resources are
bundled (~68,939 source bytes), with no runtime translation fetch. Final Chrome
switch round-trip min 12.93/max 68.26 ms on this local run; cold first-render
state passed but a standardized first-paint timing benchmark was not performed.
Form/router/auth/query-client instances and active private preview were not
recreated on switch. No scale claim is inferred from these local timings.

## 18. Frontend Regression

Original implementation baseline: 367/22 files (304 pre-11A + 63 i18n).
Final: **387 passed, 22 files**, no failed/skipped cases; 20 added adversarial
cases, none removed or weakened. Focused core/UI run: 80 passed, two files;
inventory tests and negative TypeScript fixtures also pass. `npx tsc -b`,
`npx tsc -p tsconfig.i18n-tests.json --noEmit`, `npm run lint` and
`npm run build` pass (Vite 8.1.5, 413 transformed modules).

## 19. Backend Compatibility

Full backend: **1,388 passed**, no failures/skips, one existing Starlette/
httpx TestClient deprecation warning. App/API/auth/product/storage logic and
schema unchanged; only the synthetic HTTP audit harness was amended.
Compileall, Ruff `--no-cache`, pip check/audit pass. Alembic
`current=heads=a10b2c3d4e5f`; `alembic check` reports no upgrade operations.
No migration or development DB downgrade occurred.

## 20. Real Browser

Two final clean runs passed in real headless Chrome against owned loopback
Vite/Uvicorn/MySQL: **130 checks each** (50 HTTP/setup + 80 i18n/browser).
These include cold/reload, keyboard, RTL 1280/390, form preservation,
catalog/product/image workflow, UTC dates, CNY, public privacy, private Blob
cleanup and the held-response cross-account attack. Last eight visual files
are in `C:\Users\ASUS\AppData\Local\Temp\unishop-i18n-visual-oa2s7pwe`;
Arabic/French mobile screenshots were inspected. Last run reports
`preservation`, `synthetic_cleanup`, `media_cleanup`,
`browser_temp_cleanup`, `server_stopped`, `frontend_stopped` all true.
Not a multi-browser or screen-reader certificate.

## 21. Dependencies

Installed i18next **26.4.4**, react-i18next **17.0.16**, React 19.2.7,
Tailwind 3.4.19. Root manifest and lock match; four added packages only
(`i18next`, `react-i18next`, `html-parse-stringify`,
`use-sync-external-store`), no old lock version changed. Of 363 lock entries,
330 installed entries match; 33 optional other-platform packages are absent.
Trusted-system-CA HTTPS `npm ci --dry-run --ignore-scripts --no-audit` passed;
no TLS bypass or forced update. `npm audit --omit=dev`: **0**. Full
`npm audit`: **7 affected build nodes: 5 High/2 Moderate** through
[braces ≤3.0.3](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) and
[postcss-selector-parser <7.1.6](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)
under Tailwind 3's build dependency graph. These are inherited, not introduced
by i18n; do not represent seven distinct vulnerabilities. Separate
dependency-migration/release decision required; no Tailwind 4 migration here.
Fresh pip audit: no known installed Python-package findings.

## 22. Data Preservation

Before/after ordered row-count+SHA-256 fingerprints are identical for **all
16 development tables**, including 4 legitimate users, 4 roles, 9 refresh
tokens, 6 cities, and zero products/images/evidence after cleanup. Report-only
media audit: `image_rows=0, issues=[]`. No private seller evidence was changed.
The first failed browser run revealed the harness cleanup defect; exact
synthetic ORM cleanup restored all 16 fingerprints and subsequent two runs
cleaned DB/media/owned servers automatically. One disposable outside-repository
Chrome directory from that failed attempt still exists:
`C:\Users\ASUS\AppData\Local\Temp\unishop-browser-http-dm5tkr9a`
(profile + 83-byte synthetic image). Automated recursive removal was denied
by local tool policy, so it was not bypassed. It contains no development
database or repository media and should be removed manually by the workstation
owner when convenient. This exception is not hidden as a clean temp sweep.

## 23. Unrelated Artifact Preservation

All 13 original untracked items remain unstaged and unmodified:
`output/pdf/unishop-full-architecture-flow.pdf`,
`tmp/pdfs/build_unishop_architecture.py`, and
`tmp/pdfs/rendered/page-01.png` through `page-11.png`. All 13 SHA-256
hashes match the recorded implementation baseline; zero deleted/modified.

## 24. Clean Architecture Review

Resource/formatter/persistence dependencies point toward presentation, not
backend security/business rules. No second locale state, repeated global
listeners, locale-specific product/auth fork or broad refactor was introduced.
The switcher request counter is a small UI race guard. The harness cleanup
change is isolated from the app. Client-side names remain server-backed with
approved English fallback; no hardcoded alternate catalog.

## 25. Documentation

Created this final 30-section audit. Updated the original implementation
report with a dated final-audit pointer/counts and the current-status summary;
previous implementation evidence remains historical. Limitations and release
blockers are explicit here: inherited build advisories, native linguistic and
screen-reader review, private production storage, distributed controls,
target MySQL 8, Docker/NGINX runtime, operations/recovery.

## 26. Audit File Changes

| Path(s) | Reason/change | Verification |
|---|---|---|
| `frontend/src/components/layout/LanguageSwitcher.tsx` | Fence stale failure UI via latest request id. | Failing-then-passing race test; Chrome rapid switch. |
| `frontend/src/i18n/locales/en/catalog.json` | Correct listing availability copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/zh-CN/catalog.json` | Correct listing availability copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/ar/catalog.json` | Correct listing availability copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/fr/catalog.json` | Correct listing availability copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/en/verification.json` | Correct approved-seller copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/zh-CN/verification.json` | Correct approved-seller copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/ar/verification.json` | Correct approved-seller copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/fr/verification.json` | Correct approved-seller copy. | Four-locale regression and key parity. |
| `frontend/src/i18n/locales/en/auth.json` | Remove chat/payment/delivery and saved-item claims. | Four-locale regression, Chrome. |
| `frontend/src/i18n/locales/zh-CN/auth.json` | Remove chat/payment/delivery and saved-item claims. | Four-locale regression, Chrome. |
| `frontend/src/i18n/locales/ar/auth.json` | Remove chat/payment/delivery and saved-item claims. | Four-locale regression, Chrome. |
| `frontend/src/i18n/locales/fr/auth.json` | Remove chat/payment/delivery and saved-item claims. | Four-locale regression, Chrome. |
| `frontend/tests/unit/i18n-core.test.ts` | Invalid locale/error/plural/copy adversaries. | Focused 80 and full 387. |
| `frontend/tests/unit/i18n-ui.test.tsx` | Race, profile/edit-form, late private-image cases. | Focused 80 and full 387. |
| `frontend/scripts/verify-i18n-browser.py` | Four stored-locale cold starts and real delayed private response. | 130/130 Chrome ×2; exact cleanup. |
| `backend/scripts/audit_security_http.py` | Complete DB/media cleanup before bounded profile cleanup; check count. | Chrome ×2, full pytest, Ruff/compile. |
| `documentation/phases/PHASE_11A_INTERNATIONALIZATION.md` | Mark implementation figures historical, link final audit. | Relative-link and Git diff review. |
| `documentation/CURRENT_PROJECT_STATUS.md` | Record final results and production blockers. | Relative-link and Git diff review. |
| `documentation/phases/PHASE_11A_FINAL_ADVERSARIAL_AUDIT.md` | Durable evidence/verdict. | Markdown/manifest/whitespace review. |

No new audit test file was needed; strengthened cases reside in the original
untracked Phase 11A test files.

## 27. Original Implementation Files

The original report's 104 paths (57 tracked modifications + 47 additions)
all remain in the worktree, with no missing path or replacement. This audit
adds one tracked harness modification and this new report path, for **106
Phase 11A/audit paths** total. `output/` and `tmp/` are 13 separate
unrelated artifacts, not part of that count. No unexpected source file,
generated media, .env secret, migration or Phase 11B code was added.

## 28. Git State

HEAD unchanged `00be821eeb956d19e460e33732bf608f1802d73d`;
branch `feature/authentication`. Final expected state: 58 modified tracked,
48 new Phase 11A/audit files, 13 unrelated untracked, zero staged/deleted.
`git diff --check` has zero whitespace errors. Commit created: **NO**.
Push performed: **NO**. This section records the final status verified after
writing documentation; see the final command results below before staging.

## 29. Security and Regression Gate

Translation injection/parity/plurals, auth isolation, account switching,
private media, UTC/CNY, four-language/RTL/browser, form state, keyboard,
frontend 387/387, backend 1,388/1,388, compile/Ruff/pip, Alembic no-drift,
16 fingerprints, media audit, 13 hashes and architecture: **PASS locally**.
Production-only dependency audit is zero; full build audit remains nonzero
and is a **production security blocker**, not silently waived. The prior
failed-run disposable temp profile is explicitly disclosed in §22. No
Phase 11B implementation or release claim.

## 30. Final Verdict

Security sound for audited local scope: YES. Architecture: YES. Translation
integrity: YES. RTL: YES within Chrome-tested layouts. Authentication
unaffected: YES. Product/media privacy preserved: YES. Regression intact:
YES. Existing data and 13 artifacts preserved: YES. Phase 11B absent: YES.
Ready for human-reviewed Phase 11A staging/commit: **YES**. Backend Phase
11B may begin **after Git closure and separate authorization**, not in this
audit. **PRODUCTION READY: NO** because inherited build advisories and
deployment/security infrastructure remain unresolved.

UniShop China Phase 11A Internationalization and Multilingual Foundation passed its final adversarial audit across four-language translation, RTL, accessibility, authentication isolation, private media security, data preservation, clean architecture, and regression. Phase 11A is ready to commit. Production readiness is not claimed.
