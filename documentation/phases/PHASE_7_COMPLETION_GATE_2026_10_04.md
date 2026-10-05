# Phase 7 seller verification — implementation and security gate
Initial implementation audit: 2026-10-04. Final regression rerun: **2026-10-05 (Asia/Shanghai)**.
Repository: UniShop China. Engineering evidence, not ASVS certification.

## 1. EXECUTIVE RESULT

**LOCAL PHASE 7 PASSED: YES** — local automated functional, application-security, integration,
migration and data-preservation regression checks pass on the verified installed dependencies.
**PRODUCTION READY: NO.** Full dependency/security closure: **NO**, because the unpatched
Tailwind 3 / braces advisory remains an explicit production/security blocker.
Browser and Docker/NGINX runtime gates remain **ENVIRONMENT BLOCKED**, not passed.
Phase 8: **NOT STARTED; not authorized by this task**.

The user explicitly excluded a Tailwind 4 migration and deferred it to a separate dependency task.
This is not risk acceptance or a claim that every security gate is green.
Open finding groups: Critical 0; High 1 (unpatched braces build dependency);
Medium 0; Low 0. Resolved application findings: four Medium gaps and one Low documentation gap.
Informational limitations: browser, container runtime, remote lookup, local lint cache/test warning.
Counts are finding groups, not individual advisories or affected transitive packages.

## 2. GIT BASELINE

Branch: feature/authentication. HEAD: f7710d8728ff88a2f0cf9769fb7ea3f7282af00d.
Local origin/feature/authentication points to the same commit.
Fresh remote verification could not complete: connection resets/timeouts.
The worktree was clean at the start of the preceding audit; the new Phase 7 request arrived
with this session's 11 modified files and one new regression-test file. Those fixes were retained.
No unrelated user edits were overwritten. git fsck found no corruption; one pre-existing
unreachable/dangling commit was left untouched.

## 3. ARCHITECTURE

Preserved seller_verifications, seller_evidence, seller_verification_audit and the existing
storage abstraction. Internal UUIDs stay private; review_reference is an opaque random routing
reference, not authority. The exact state machine is PENDING (mutable draft) -> UNDER_REVIEW ->
VERIFIED or REJECTED. Rejection permits a separate new attempt, not mutation of the old one.
A unique generated active-slot constraint enforces one active attempt per user.

## 4. ELIGIBILITY

The backend requires current ACTIVE status plus verified email and phone for start/upload/submit
and rechecks applicant eligibility at review. Own reads require ACTIVE authentication.
The frontend route retains its profile/onboarding gate; onboarding is not an additional backend
seller-eligibility rule in the preserved design. A public profile must be complete and ACTIVE.
UI checks never authorize a request.

## 5. EVIDENCE SECURITY

Exactly SELFIE, WECHAT_PROOF, HANDWRITTEN_CODE. JPEG/PNG only; extension, declared MIME, decoded
format and valid image structure must agree. Input/output limit 5 MiB; each axis <=6000,
total <=12 million pixels; single-frame only. Decode/re-encode strips EXIF, comments, ICC/text
metadata and trailing payload. Stored SHA-256 checks sanitized bytes at retrieval.
Random 256-bit file keys, exclusive creation, strict key syntax, traversal/symlink/junction
rejection; no user filename becomes a filesystem path. Dimensions are validated during decode,
not stored as additional columns in the preserved evidence model.

## 6. STORAGE

Development-only private local adapter; no static mount, public evidence path or frontend asset.
Git and both Docker contexts exclude private_uploads. Production fails closed pending an
object-storage adapter. File-write/DB-failure compensation and storage-failure rollback are tested.
Replacement and renewal delete only the exact superseded file after commit. Cleanup failures
emit a fixed alert; cross-system crash/ambiguous-commit reconciliation remains operational work.

## 7. WORKFLOW

Start draft, upload three required images, submit once, admin inspect then approve/reject.
Approval does not assign a role or enable marketplace functions. Submitted/terminal evidence
and challenges are immutable. Rejected history remains private and unchanged.

Handwritten code: 48 random bits, default 10-minute validity, configurable 5–60 minutes using
SELLER_CODE_EXPIRY_MINUTES. Server rejects expired upload/submission. Draft-only
renew_challenge rotates the code, removes prior handwritten proof atomically and preserves
other evidence. The multipart challenge field rejects stale in-flight uploads after renewal.
Submission before expiry remains reviewable afterward. The code is readable privately because
the applicant and human reviewer must see it; it is not a login secret. No OCR/biometrics or
automated fraud detection is claimed.

## 8. PRIVATE ACCESS

Owner or current DB ADMIN only; foreign users get generic denial. The grant response contains a
fixed URL and separate ticket. Retrieval requires bearer auth plus X-Evidence-Ticket.
No query credential is accepted. Ticket lifetime 60 seconds, signed, actor-bound and one-use,
with replay/tamper/expiry/replaced-file checks and bounded process-local grant storage.
Authorization and file hash are checked under DB locks. EVIDENCE_READ must commit before
bytes are returned. Audit insert/commit, storage or hash failure releases no image.

## 9. RATE LIMITING

Per-minute user/peer budgets: start/submit/renew 5/15; upload 12/36; admin 30/90;
read/grant/download 60/180. Peer ingress runs before parsing, so invalid JSON cannot bypass it.
Missing fields and content-type failures also remain bounded. Forwarded headers do not choose
the connection-peer key. Upload ingress caps bytes, uses four slots and a 30-second timeout.
All limits/grants remain process-local; no Redis was added.

## 10. AUTHORIZATION

Current DB role and account-state checks, owner-derived targets, self-review denial, strict
bodies and opaque reference validation are covered. No client status, user_id, reviewed_by,
audit actor or storage key can be assigned. Cookie-only requests cannot authorize seller actions.
Bearer requests are not ambient-cookie CSRF operations; CORS remains exact-origin scoped.
Existing authentication/refresh/reset/profile boundaries remain intact.

## 11. PUBLIC PRIVACY

Public profiles add only seller_verified: boolean. It derives from a VERIFIED DB attempt and
current verified email/phone, not JWT roles or client input. Pending/rejected/no-attempt users
are false; inactive/incomplete profiles remain hidden. Evidence, challenges, reviewer identity,
review reference, rejection history and private timestamps never appear publicly.
The React badge appears only when the boolean is true.

## 12. DATABASE

Original b7c1d2e3f4a5 preserved; additive c7d8e9f0a1b2 is current and sole head.
It adds/backfills challenge_expires_at without deleting existing rows. alembic check: no drift.
Isolated MySQL upgrades, challenge-column downgrade/upgrade, Phase 7 table round-trip and
Phase 6/6.1 round-trips passed. No development downgrade/reset/truncate was run.
Named unique/check constraints and explicit FK CASCADE/SET NULL semantics remain.
Orphans, duplicate constrained data and invalid refresh replacement user/family links: zero.
MySQL tested here is 9.4.0, not a claim of MySQL 8 production certification.

Alembic current, heads, history and check were all rerun successfully on 2026-10-05.
All ten development-table full-row fingerprints match both the 2026-10-04 baseline and
the before/after 2026-10-05 regression snapshots: users 4, roles 4,
phone challenges 3, refresh rows 7; reset/email challenges, profiles and all seller tables 0.
Private evidence baseline/final file count 0. Synthetic rows/files were cleaned exactly.

## 13. CONCURRENCY

16 selected race/rollback cases passed in each of three consecutive fresh runs on 2026-10-05.
Includes draft/draft, upload/submit, submit/submit, approve/reject, approve/approve,
same-type replacement, one-use replay, challenge renewal/old upload, renewal/submission,
audit/commit failure and storage rollback. Authentication/profile/public-handle regressions
also pass in the full suite. All workers used isolated synthetic ownership and cleanup.

## 14. BACKEND TESTS

Full suite rerun on 2026-10-05 with the retained Python security updates: 883 passed, zero failed/skipped.
Targeted seller/storage/challenge/privacy suite: 92 passed.
Python compile/import, database health, pip check and Ruff --no-cache: PASS.
One pre-existing Starlette TestClient/httpx deprecation warning.
Ordinary cached Ruff hit a corrupt local-cache panic during the preceding audit; the complete
2026-10-05 no-cache check passes.
No source suppression or broad dependency upgrade was used to hide it.

## 15. FRONTEND TESTS

Fresh 2026-10-05 run after the successful trusted-CA installation: 187 tests across 14 files passed.
Separate TypeScript check, ESLint and production build passed.
New coverage includes challenge-bound uploads, expiry/renewal, complete submission, safe errors,
fresh mount restoration, timezone-aware deadlines and the public boolean badge.
Actual installed package.json files now report Axios 1.20.0, brace-expansion 5.0.12 and Undici 7.29.1.
Both root dependency maps match package-lock.json; every installed lockfile package version
matches, with zero missing non-optional packages. npm ls --depth=0 also succeeds.
The targeted version pins are retained because installation and regression verification succeeded.
Tailwind remains 3.4.19; no Tailwind 4 migration or force upgrade was performed.

## 16. LIVE HTTP / MYSQL

64 fresh checks passed on 2026-10-05 through real loopback Uvicorn/MySQL: health, registration, phone/email verification,
login/profile/onboarding/public privacy, seller draft/uploads/submit, owner/admin evidence access,
committed read audit, approval/public badge, password reset/change, logout/logout-all.
Only synthetic images/users and fake delivery were used. Server stopped; cleanup and exact
pre-existing-table preservation passed. No real SMS/email/KYC provider was contacted.

## 17. OPENAPI

Local 31 operations; all-development-inboxes 35; production-safe configuration 29.
Operation IDs unique; eight seller/admin operations; bearer security documented.
No Phase 8 routes, legacy profile UUID route, sensitive query parameter or storage URL.
Only safe admin pagination uses a query parameter. Dev inbox routes absent in production.

## 18. BROWSER

ENVIRONMENT BLOCKED. The browser skill was read and its connection retried on 2026-10-05; initialization
failed before a tab was available. No fresh real-browser PASS is claimed. Unit DOM tests are
not substituted for browser address-bar, cookie, history, back/forward or account-switch testing.

## 19. DOCKER / NGINX

ENVIRONMENT BLOCKED: Docker/NGINX executables unavailable, rechecked on 2026-10-05.
Source checks and Docker-ignore regression tests pass. NGINX has no private static mount,
omits query strings from access logs and retains download-route log suppression.
Container build/start, nginx -t, production proxy behavior and deployment exposure remain unverified.

## 20. DEPENDENCIES

Installed Python: PyJWT 2.15.1 and urllib3 2.8.0; pip check and pip-audit PASS, no known findings.
Required minimums recorded in requirements.txt.

Frontend pins/lock and actual installed files now agree: Axios 1.20.0, brace-expansion 5.0.12,
Undici 7.29.1. Installation succeeded using Node 24.12.0 with --use-system-ca, normal HTTPS,
strict-ssl=true and https://registry.npmjs.org/. No certificate-validation bypass, insecure
registry setting or TLS relaxation was used. No persistent npm settings were changed.
The first combined shell command was refused by execution policy without running. A normal
npm invocation, without its metadata-deletion step, succeeded and changed nine installed packages;
it did not expand the targeted manifest/lock diff. Earlier certificate/reset failures are historical,
not an outstanding installation blocker after this successful retry. Lifecycle scripts were disabled
for this dependency patch install; the installed tooling passed the full build and test gate.

Verified commands (run from frontend; npm-cli.js is the normal installed npm entry point):
```powershell
node --use-system-ca "C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js" install --ignore-scripts --no-audit --no-fund --strict-ssl=true --registry=https://registry.npmjs.org/ --fetch-retries=1 --fetch-timeout=20000
node --use-system-ca "C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js" audit --json --strict-ssl=true --registry=https://registry.npmjs.org/ --fetch-retries=1 --fetch-timeout=20000
node --use-system-ca "C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js" audit --omit=dev --json --strict-ssl=true --registry=https://registry.npmjs.org/ --fetch-retries=1 --fetch-timeout=20000
```

Full npm audit: **exit 1, five High affected graph nodes, one root advisory**.
npm audit --omit=dev: **exit 0, zero known vulnerabilities**. A clean production-only dependency
audit does not erase a vulnerable build toolchain or establish production readiness.

braces 3.0.3 remains in the Tailwind 3 build graph. **GHSA-vfj7-8cjw-p6xm / CVE-2026-93687**:
recursive pattern processing can exhaust the stack and terminate the process (CWE-674),
affected versions <=3.0.3, no upstream patched version listed as checked on 2026-10-05.
npm reports High, CVSS 3.1 7.5; GitHub also reports CVSS 4.0 8.7. These are distinct scoring versions.
Installed paths include tailwindcss@3.4.19 -> chokidar@3.6.0 -> braces@3.0.3 and
tailwindcss@3.4.19 -> micromatch@4.0.8 -> braces@3.0.3. Five affected graph nodes share this
root (braces/chokidar/micromatch/fast-glob/tailwindcss); they are not five independently
exploitable application bugs. The separately patched brace-expansion package is not braces.
No application-controlled input reaching this build-only pattern parser was demonstrated.
It remains a HIGH dependency finding, not a clean audit or accepted risk.
Per the user's explicit instruction, keep Tailwind 3 and resolve this in a **separate dependency-
migration task** with compatibility and visual regression verification. Do not force-update,
suppress the advisory, interpret the deferral as risk acceptance, or migrate Tailwind in Phase 7.

Sources:
- [braces advisory, no patch](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
- [PyJWT options-mutation advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-gvp8-978c-rx2q)
- [Axios advisory](https://github.com/advisories/GHSA-vh66-26gq-q6x8)

## 21. SECURITY FINDINGS

| Severity / status | Root cause and impact | Fix / regression |
|---|---|---|
| Medium, fixed | Download credential was in query string, exposing it to URL/history/log capture despite actor binding. | Header-only transport; legacy-query denial, CORS and OpenAPI tests. |
| Medium, fixed | Successful evidence reads had no committed audit record. | Locked authorization/hash/read plus commit-before-bytes; audit/commit/storage/hash failure tests. |
| Medium, fixed | FastAPI parsed invalid JSON before dependency peer budgets. | Pre-parse ASGI guard; failing-then-passing malformed JSON and forwarded-peer tests. |
| Medium, fixed requirement gap | Handwritten challenge had no expiry or renewal invalidation. | Deadline migration, strict body binding, atomic renewal and repeated renewal races. |
| Low, fixed | Current README/status implied future features or stale privacy contracts. | Current scope, contracts, limitations and historical-count labeling corrected. |
| High, resolved Python group | Older PyJWT/urllib3 versions had published advisories. | Compatible installed updates, full backend rerun, clean pip-audit. |
| High, resolved frontend group | Older Axios/brace-expansion/Undici had dependency advisories. | Trusted-CA install, actual-version/lock consistency checks and full frontend rerun pass; production-only audit clean. |
| High, OPEN build dependency | Unpatched braces recursion vulnerability in Tailwind 3 tooling. | Explicit production/security blocker assigned to a separate dependency-migration task; Tailwind 3 retained. |

No passwords, OTPs, JWTs, evidence content or download credentials were added to operational logs.
Tracked/untracked/diff and bounded eight-commit scans found no configured-secret/private-key/provider-
token/literal-JWT matches or sensitive tracked/unignored artifacts. Pattern scans are not proof
that every possible unknown secret is absent.

Controls reviewed against OWASP-style authentication, access control, input validation, file upload,
logging and API resource-consumption boundaries; no ASVS certification claim.
[OWASP REST security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
and [logging guidance](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
support keeping credentials out of URLs and recording sensitive-data access without secret values.

## 22. PRODUCTION BLOCKERS

Mandatory production readiness blockers, regardless of the local regression PASS:

1. Unresolved Tailwind 3 / braces advisory; separate dependency-migration task required.
2. Private production object storage is not configured.
3. Real-browser verification remains environment-blocked (browser skill initialization fails).
4. Docker/NGINX runtime verification remains environment-blocked (executables unavailable).

The frontend installation/version-consistency blocker is resolved, but the four blockers above
are not. Deploy private object storage with encryption/ACLs, shared atomic
one-use grants and distributed limiting; define consent, retention/erasure, reviewer access review,
crash/orphan reconciliation, protected backups and recovery tests. Configure TLS/security headers,
trusted proxy boundaries, managed secrets/rotation, safe observability/alerting, approved SMS/email
providers and production database/version certification. Keep development fake inboxes disabled.
Existing short-lived access-token residual validity and per-tab refresh coordination remain documented.

## 23. FILES CHANGED

All paths are repository-relative. 42 tracked files modified and 4 new files; no files deleted.

| File | Reason |
|---|---|
| `README.md` | Correct implemented/future scope; link current Phase 7 contract and migration. |
| `backend/.env.example` | Document the now-enforced handwritten challenge lifetime. |
| `backend/app/api/v1/seller_verification/dependencies.py` | Inject configured challenge lifetime. |
| `backend/app/api/v1/seller_verification/routes.py` | Header-only retrieval; strict challenge-bound multipart upload. |
| `backend/app/core/config.py` | Bounded seller challenge expiry setting. |
| `backend/app/core/evidence_security.py` | Pre-parse seller/admin peer throttling, including invalid JSON. |
| `backend/app/main.py` | Allow the evidence header only through configured CORS origins. |
| `backend/app/models/seller_verification.py` | Persist challenge expiry without replacing existing models. |
| `backend/app/schemas/profile.py` | Expose only the public seller_verified boolean. |
| `backend/app/schemas/seller_verification.py` | Strict renewal, deadline and separate ticket response contracts. |
| `backend/app/services/profile_service.py` | Derive public badge from DB verification and current eligibility. |
| `backend/app/services/seller_verification_service.py` | Atomic renewal/expiry checks and audited, commit-before-bytes reads. |
| `backend/app/services/storage_service.py` | Issue private tickets separately from URLs. |
| `backend/requirements.txt` | Require patched PyJWT/urllib3 versions. |
| `backend/scripts/audit_public_handle_migration.py` | Isolated challenge/Phase 7/Phase 6 migration preservation cycles. |
| `backend/scripts/audit_security_http.py` | Header retrieval, admin read-audit check, challenge binding and public badge lifecycle. |
| `backend/tests/integration/test_public_handles.py` | Maintain exact public-response allowlist with the boolean badge. |
| `backend/tests/integration/test_seller_verification.py` | Update private transport/challenge contract; extend malicious-file cases. |
| `backend/tests/integration/test_seller_verification_concurrency.py` | Add submit/approve/renewal races and current challenge binding. |
| `backend/tests/unit/test_profile_openapi.py` | Assert exact safe public badge schema. |
| `backend/tests/unit/test_seller_storage_security.py` | Header-independent ticket contract and concurrent replay test. |
| `documentation/CURRENT_PROJECT_STATUS.md` | Current evidence and explicit open gate; retain historical records. |
| `documentation/api/profile-api.md` | Document the public boolean-only seller field. |
| `documentation/phases/PHASE_7_SELLER_VERIFICATION.md` | Update expiry, renewal, private access, throttling and migration contracts. |
| `documentation/security/PHASE_7_SELLER_VERIFICATION_THREAT_MODEL.md` | Document new controls and remaining operational limitations. |
| `documentation/security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md` | Remove the old sensitive-query exception. |
| `frontend/package-lock.json` | Targeted patched frontend resolutions, now installed and lock-consistency verified. |
| `frontend/package.json` | Verified Axios pin and brace-expansion/Undici overrides; retain Tailwind 3. |
| `frontend/src/features/profiles/api.ts` | Map the public seller boolean. |
| `frontend/src/features/profiles/contracts.ts` | Require strict boolean public seller state. |
| `frontend/src/features/profiles/types.ts` | Type the public seller indicator. |
| `frontend/src/features/sellerVerification/api.ts` | Renewal action and challenge-bound handwritten form data. |
| `frontend/src/features/sellerVerification/hooks.ts` | Preserve session boundary while passing challenge/renewal actions. |
| `frontend/src/features/sellerVerification/schemas.ts` | Require timezone-aware challenge expiry. |
| `frontend/src/pages/public/PublicProfilePage.tsx` | Render only the safe verified-seller badge. |
| `frontend/src/pages/seller/SellerVerificationPage.tsx` | Expiry/renewal UX, disabled expired submission and stale input reset. |
| `frontend/tests/unit/profile-contracts.test.ts` | Positive/negative boolean and private-field leakage tests. |
| `frontend/tests/unit/profile-pages.test.tsx` | Test badge visibility for true/false values. |
| `frontend/tests/unit/seller-verification.test.tsx` | Expiry, renewal, challenge upload, submit, restoration and safe-error coverage. |
| `frontend/tests/unit/url-privacy.test.tsx` | Update exact safe public contract without changing handle navigation. |
| `infrastructure/nginx/nginx.conf` | Correct comments for header-only credentials; preserve defensive log policy. |
| `postman/README.md` | Replace broken placeholder text with safe current API/tooling instructions. |
| `backend/alembic/versions/c7d8e9f0a1b2_seller_challenge_expiry.py` | NEW: additive challenge expiry and legacy-row backfill. |
| `backend/tests/integration/test_seller_challenge_and_public_privacy.py` | NEW: expiry boundaries, renewal rollback/stale uploads and public-state privacy. |
| `backend/tests/integration/test_seller_evidence_access_security.py` | NEW: header/privacy, read-audit failures, state matrix and malformed-JSON regression. |
| `documentation/phases/PHASE_7_COMPLETION_GATE_2026_10_04.md` | NEW: full 25-section report, 2026-10-05 final rerun, production blockers and file manifest. |

## 24. FINAL GIT STATE

HEAD unchanged at f7710d8728ff88a2f0cf9769fb7ea3f7282af00d.
All changes are unstaged; staged changes: none. New migration, two regression files and this report
are untracked pending review. git diff --check passes.
Commit created: NO. Push performed: NO. Remote synchronization could not be freshly verified.

## 25. FINAL VERDICT

Seller verification functional: YES. Evidence private: YES in tested application boundaries.
Authorization sound: YES in covered current-DB tests. URL privacy intact: YES.
Audit integrity sound: YES in tested insert/commit/storage failure paths. Data preserved: YES.
No Phase 8 code introduced: YES. Phase 8 has not started and is outside this task.

**LOCAL PHASE 7 PASSED: YES. PRODUCTION READY: NO.**
The local result covers the automated application and data-preservation gate, not production
deployment or a clean all-dependency audit. The braces blocker remains open, and browser/container
verification is not relabeled as passing. No unconditional all-green security completion is claimed.

### Final required-check ledger (2026-10-05)

| Check | Result |
|---|---|
| Full backend pytest | PASS: 883, zero failures/skips |
| Targeted seller/security/storage/challenge/public privacy | PASS: 92 |
| Expiry, stale challenge and renewal rollback | PASS: targeted and full suites |
| Renewal/upload and renewal/submit races | PASS: full/targeted plus three concurrency runs |
| No credential in URL; no evidence/storage-key response exposure | PASS: private contract and public allowlist regressions |
| Transactional read audit; audit/commit failure releases no image | PASS: success and four failure-mode tests plus live read-audit check |
| Malformed JSON throttling before parsing | PASS: seller and admin paths |
| Submitted/terminal attempts immutable | PASS: renewal/upload/review and live tests |
| Public seller state only intended boolean | PASS: all five verification states and exact response allowlist |
| Python compile; Ruff --no-cache; pip check; pip-audit | PASS; no known Python advisories |
| Full frontend tests | PASS: 187 across 14 files, on installed patch versions |
| TypeScript; ESLint; production build | PASS |
| npm audit | OPEN: exit 1; one braces advisory, five High graph nodes |
| npm audit --omit=dev | PASS: zero known vulnerabilities |
| Manifest/lock and actual installed versions | PASS: no installed-version mismatches or missing required packages |
| Alembic current / heads / history / check | PASS: sole head c7d8e9f0a1b2, no drift |
| Isolated migration upgrade/downgrade/upgrade | PASS: challenge, seller and earlier profile preservation cycles |
| Development fingerprints | PASS: all ten tables unchanged |
| Real MySQL + Uvicorn workflow and synthetic cleanup | PASS: 64; cleanup true; server stopped |
| Concurrency/rollback subset repeated three times | PASS: 16 / 16 / 16 |
| Browser | ENVIRONMENT BLOCKED |
| Docker/NGINX runtime | ENVIRONMENT BLOCKED |
| Git diff --check; unstaged-only changes | PASS; no stage/commit/push |

Backend reproduction commands (from backend/):
```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_seller_verification.py tests/integration/test_seller_verification_concurrency.py tests/integration/test_seller_evidence_access_security.py tests/integration/test_seller_challenge_and_public_privacy.py tests/unit/test_seller_storage_security.py tests/unit/test_seller_verification_service.py
# Repeat this selection three times, sequentially:
.\.venv\Scripts\python.exe -m pytest -q tests/integration/test_seller_verification_concurrency.py tests/integration/test_seller_verification.py tests/integration/test_seller_evidence_access_security.py tests/unit/test_seller_storage_security.py -k 'concurrent or racing or failed_private_read or storage_write_failure or rolls_back'
.\.venv\Scripts\python.exe -m compileall -q app tests scripts alembic
.\.venv\Scripts\python.exe -m ruff check --no-cache app tests scripts alembic
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit --progress-spinner off
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic heads
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py --seller-verification
.\.venv\Scripts\python.exe scripts/audit_security_http.py
```
Frontend reproduction (from frontend/, on the verified installed tree):
```powershell
npm test -- --run
.\node_modules\.bin\tsc.cmd -b --pretty false
npm run lint
npm run build
```
Use the trusted-system-CA commands in section 20 for both npm audits. Do not run database
test groups concurrently against the same development DB; their preservation fixtures are sequential.

Run backend from backend/:
```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Run frontend from frontend/: `npm run dev`.
For a fresh dependency install, use the normal HTTPS registry and trusted certificates, then verify
actual versions and repeat the gate. Never disable TLS or certificate verification.
