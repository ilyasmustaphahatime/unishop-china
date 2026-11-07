# Phase 13 dependency security remediation

Date: 2026-10-26 (Asia/Shanghai). Scope: dependency remediation only, preserving the
existing Phase 13 implementation. Branch `feature/authentication`; committed HEAD
`24b1bcd68720874a6379451d3e69a5d305652d6c`. No staging/commit/push/Phase 14.

## Baseline and investigation

Preflight read the Phase 13 evidence, current status, both Python requirements files,
frontend manifest/lockfile, Docker install commands and existing test/audit tooling.
Recorded SHA-256 for all 794 existing tracked/untracked files (including all 13 protected
artifacts and the unrelated BOM-only `postman/README.md`), every database table's data
and schema, and canonical OpenAPI before editing. No application source or migration
change was needed.

Actual environments: Windows Python 3.13.14; Node 24.12.0; npm 11.6.2. Existing Docker
targets remain Python 3.12 and Node 22. Metadata permits both; Docker images were not
rebuilt in this pass. Python production installation consumes `requirements.txt`;
the new certifi constraint therefore applies to Docker as well. filelock is constrained
only in `requirements-dev.txt`, because its path is the audit tool, not the application.
Frontend Docker currently uses `npm install` and the lockfile; local verification used
a clean `npm ci` to enforce manifest/lock consistency.

Fresh before-remediation audits reproduced **41 Python advisories**. Full npm had
**10 affected nodes: 4 High / 6 Moderate**, not the previously reported 9: `jsdom`
was now additionally flagged through `undici`. These are 14 distinct npm advisory
records, not 10 distinct CVEs. Production-only npm had **2 High affected nodes**.

## Remediation matrix

All versions below were checked in registry metadata, the lockfile where applicable,
and the actual installed environment. Current ranges/severities and every resolved ID
are recorded in the appendices; a scanner match is not a claim of exploitability.

| Package | Before | Advisory | Dependency path | Exposure | Smallest fixed / selected fix | Status |
| --- | --- | --- | --- | --- | --- | --- |
| certifi | 2026.6.17 | PYSEC-2026-4320 | cloudinary; Tencent SDK -> requests; httpx/audit tooling | Runtime outbound TLS and tooling CA bundle | 2026.10.19 / exact runtime constraint | Audit clear |
| filelock | 3.32.0 | 3 CVEs below | pip-audit -> CacheControl[filecache] -> filelock | Development/audit filesystem locking | 4.2.1 / exact dev constraint | Audit clear |
| Pillow | 12.3.0 | 37 advisories below | Direct runtime requirement | Untrusted product and seller-evidence images | 13.0.0 / exact runtime pin | Audit clear |
| follow-redirects | 1.16.0 | 2 GHSAs below | axios 1.20.0 -> follow-redirects ^1.16.0 | Production dependency tree; Node HTTP adapter, not browser redirect handling | 1.16.1 / 1.16.2 selected by normal compatible patch update | Audit clear |
| zod | 4.4.3 | GHSA-mrhx-c7xc-m3w5 | Direct; also eslint-plugin-react-hooks | Browser validation and lint tooling | 4.6.6 / pinned 4.6.6 | Audit clear |
| vite | 8.1.5 | 5 GHSAs below | Direct; plugin-react/vitest | Development server/editor/build; not shipped static server | 8.1.6 / pinned 8.1.6 | Audit clear |
| vitest / @vitest/mocker | 4.1.11 | 2 GHSAs below | Direct vitest -> mocker | Test/browser-mock server | 4.1.12 / pinned 4.1.12 family | Audit clear |
| undici / affected jsdom ancestor | 7.29.1 / jsdom 29.1.1 | 3 GHSAs below | jsdom -> undici | Development/test HTTP client | 7.30.1 / existing override advanced; jsdom unchanged | Audit clear |
| postcss-selector-parser / affected ancestors | 6.1.4 | GHSA-rj75-hqrm-r3gf | Tailwind 3.4.19 directly and through postcss-nested 6.2.0 | CSS build/dev parsing | 7.1.6 / override scoped under tailwindcss | Audit clear; CSS compatibility passed |

### Why these changes are minimal and compatible

- No fixed release in the existing Pillow 12 or filelock 3 lines was identified in
  the advisory/registry evidence. The required major upgrades are confined to those
  packages, not frameworks. [Pillow 13 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)
  require Python >=3.11, satisfied by local 3.13 and Docker 3.12. Existing sanitizers
  use supported PNG/JPEG/WebP decode, EXIF transpose, RGB/RGBA conversion and re-encoding.
  They do not use the removed private APIs. Existing hostile-image tests remain active.
- Many Pillow findings involve formats or operations the application rejects. That
  limits reachability but does not justify retaining the vulnerable library: allowed
  image parsing and bundled native codecs remain security-sensitive.
- [filelock 4's breaking protocol change](https://github.com/tox-dev/filelock/releases/tag/4.0.0)
  concerns reader/writer soft-lock coordination. Inspection confirms CacheControl uses
  ordinary `FileLock`; no application use of reader/writer locks exists. New tests cover
  cache round-trip and independent-holder exclusion. No active audit process was
  upgraded mid-operation.
- Tailwind remains **3.4.19** with its existing ^3.4.17 declaration. The only new override
  is `tailwindcss -> postcss-selector-parser = 7.1.6`, including the nested dependency.
  [Parser 7's major change](https://github.com/postcss/postcss-selector-parser/releases/tag/v7.0.0)
  concerns insertion during iteration; this is deliberately outside the parent's
  declared v6 range and needs explicit compatibility evidence. Before updating, two
  CSS fixture hashes were captured using parser 6.1.4. Both remain byte-identical on
  7.1.6, covering RTL, responsive/dark/group/peer variants, arbitrary selectors/values,
  attribute variants, @apply and postcss-nested behavior. Keep these tests with the
  override; this does not claim every possible third-party Tailwind plugin is verified.
- Vite 8.1.6 fixes the matched ranges without selecting latest 8.3.x. Vitest remains
  on 4.1.x, not version 5. Zod remains on major 4; its new negative test verifies that
  an oversized constrained array produces one bounded error instead of per-item errors.
- npm also resolved Vitest's matching internal packages to 4.1.12, chai 6.2.2 -> 6.3.0
  and tinyrainbow 3.1.1 -> 3.2.0 within declared ranges. `use-sync-external-store`
  remains 1.7.0; npm recalculated only its peer classification. All other installed
  package versions remain unchanged. No new package was added to the dependency graph.
- TLS validation remained enabled: npm registry is HTTPS, strict-ssl is true, and
  Node's `--use-system-ca` was used for package installation. No insecure registry,
  trusted-host bypass, certificate suppression or audit-ignore list was used.
- Dependency lifecycle scripts were disabled for the controlled npm install.
  The platform optional binaries installed successfully and tests/build passed.
  A clean npm ci installed 330 platform-applicable packages with zero installed/locked
  version mismatches. Optional dependencies for other platforms remain optional.
- No Tailwind 4 migration, npm audit fix --force, framework rewrite, security-feature
  removal, new migration, or change to API/WebSocket contracts.

## Commands and verification

Backend commands run from `backend` using `.\.venv\Scripts\python.exe`
(abbreviated `python` below); frontend commands run from `frontend`.

| Gate / command | Result |
| --- | --- |
| Before `python -m pip_audit --progress-spinner off -f json` | Exit 1; 41 advisories / 3 packages |
| Before `npm audit --json` | Exit 1; 10 nodes (4 High / 6 Moderate), 14 distinct advisories |
| Before `npm audit --omit=dev --json` | Exit 1; 2 High nodes |
| `python -m pip install --disable-pip-version-check -r requirements-dev.txt` | PASS; only Pillow, certifi and filelock changed |
| `node --use-system-ca <npm-cli.js> update follow-redirects --package-lock-only --ignore-scripts --no-audit` | PASS; package-manager-generated lockfile |
| `node --use-system-ca <npm-cli.js> ci --ignore-scripts --no-audit` | PASS; clean install; lock preserved |
| After `python -m pip_audit --progress-spinner off` | PASS; no known vulnerabilities |
| After `npm audit --json` | PASS; zero findings |
| After `npm audit --omit=dev --json` | PASS; zero findings |
| `python -m pip check` | PASS |
| `python -m compileall -q app alembic scripts tests` | PASS |
| `python -m ruff check --no-cache app alembic scripts tests` | PASS |
| Targeted Python command below | 317 passed, zero failed/skipped, 1 inherited TestClient warning |
| `npm run test -- --run tests/unit/dependency-compatibility.test.ts` | 3 passed |
| `python -m pytest -q --tb=short` | 1,824 passed; zero failed/skipped; 1 inherited warning; 132.38 seconds |
| `npm run test -- --run` | 390 passed / 23 files; zero failed/skipped |
| `npx tsc --noEmit`, `npm run lint`, `npm run build` | PASS; production build also runs tsc -b |
| `python -m scripts.audit_security_http` | 161 live checks passed on MySQL 9.4/Uvicorn; synthetic/media cleanup, data preservation and server shutdown confirmed |
| Read-only `python -m alembic current`, `check` | d13e4f5a6b7c; no new upgrade operations |
| `git diff --check`, file/data/schema/contract preservation | PASS; final comparison described below |

Targeted command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_dependency_compatibility.py tests/unit/test_product_image_security.py tests/unit/test_product_image_adversarial_audit.py tests/unit/test_seller_storage_security.py tests/unit/test_chat_domain.py tests/unit/test_chat_security.py tests/unit/test_chat_websocket.py tests/integration/test_chat_routes.py tests/integration/test_chat_concurrency.py -q --tb=short
```

The two full regression suites are each run once in this remediation pass. Additional
live verification is limited to the existing media/security HTTP workflow because
Pillow directly processes uploaded product and private seller images. The earlier
chat HTTP/WebSocket, three-round race and disposable migration acceptance results
are historical evidence, not rerun or claimed as new results. No migration command
that changes schema/data is needed for this task.

## Exact advisory inventory

Metadata below was retrieved from npm's audit service and OSV's GHSA-backed records.
Severity labels are their current classifications (which may differ from release-note
groupings); they are not assertions that every listed exploit is reachable here.
Every listed advisory is absent from the post-remediation audits.

### Python: 41 records

| Package | Advisory / source | Severity | Affected range |
| --- | --- | --- | --- |
| certifi | [PYSEC-2026-4320](https://osv.dev/vulnerability/GHSA-6q48-6c7w-9gw2) | CRITICAL | >= 2019.03.09, < 2026.10.19 |
| filelock | [CVE-2026-112940](https://osv.dev/vulnerability/GHSA-v4x8-3wr5-3wq8) | HIGH | >= 3.20.4, < 4.2.1 |
| filelock | [CVE-2026-112913](https://osv.dev/vulnerability/GHSA-9vhv-jxww-xfm5) | LOW | >= 3.20.4, < 4.2.1 |
| filelock | [CVE-2026-112907](https://osv.dev/vulnerability/GHSA-567q-5qvw-pf92) | LOW | >= 3.22.0, < 4.2.1 |
| pillow | [CVE-2026-112895](https://osv.dev/vulnerability/GHSA-p4wg-p73j-c528) | HIGH | >= 5.1.0, < 13.0.0 |
| pillow | [CVE-2026-112400](https://osv.dev/vulnerability/GHSA-65qm-jvmh-6pqg) | HIGH | >= 9.2.0, < 13.0.0 |
| pillow | [CVE-2026-112397](https://osv.dev/vulnerability/GHSA-58r4-6rv3-gfh8) | HIGH | < 13.0.0 |
| pillow | [CVE-2026-112896](https://osv.dev/vulnerability/GHSA-pchr-8j38-3x4p) | HIGH | < 13.0.0 |
| pillow | [CVE-2026-112897](https://osv.dev/vulnerability/GHSA-q45j-58j2-45rg) | HIGH | >= 5.3.0, < 13.0.0 |
| pillow | [CVE-2026-112395](https://osv.dev/vulnerability/GHSA-462x-pgg6-55fp) | MODERATE | >= 8.2.0, < 13.0.0 |
| pillow | [CVE-2026-112404](https://osv.dev/vulnerability/GHSA-c6hw-5grf-ff96) | HIGH | >= 8.1.0, < 13.0.0 |
| pillow | [CVE-2026-112899](https://osv.dev/vulnerability/GHSA-vx6w-vv9f-6gvg) | MODERATE | >= 2.3.0, < 13.0.0 |
| pillow | [CVE-2026-112402](https://osv.dev/vulnerability/GHSA-7mwm-ghpf-9vrm) | HIGH | < 13.0.0 |
| pillow | [CVE-2026-112900](https://osv.dev/vulnerability/GHSA-w889-685w-c8fh) | CRITICAL | >= 2.6.0, < 13.0.0 |
| pillow | [CVE-2026-112893](https://osv.dev/vulnerability/GHSA-j4m9-6w36-pw47) | HIGH | >= 10.0.0, < 13.0.0 |
| pillow | [CVE-2026-112392](https://osv.dev/vulnerability/GHSA-27h8-gf7j-v5hc) | HIGH | < 13.0.0 |
| pillow | [CVE-2026-112891](https://osv.dev/vulnerability/GHSA-fc9g-5qg7-mf45) | MODERATE | >= 9.2.0, < 13.0.0 |
| pillow | [CVE-2026-112405](https://osv.dev/vulnerability/GHSA-cp9v-662q-vvx9) | HIGH | >= 12.0.0, < 13.0.0 |
| pillow | [CVE-2026-112390](https://osv.dev/vulnerability/GHSA-22hg-r758-rrw9) | HIGH | >= 7.2.0, < 13.0.0 |
| pillow | [CVE-2026-112401](https://osv.dev/vulnerability/GHSA-74r2-7ff9-mjj2) | MODERATE | >= 5.4.0, < 13.0.0 |
| pillow | [CVE-2026-112901](https://osv.dev/vulnerability/GHSA-xgh8-jp6q-p5x8) | MODERATE | < 13.0.0 |
| pillow | [CVE-2026-112391](https://osv.dev/vulnerability/GHSA-254f-3936-288h) | MODERATE | >= 5.1.0, < 13.0.0 |
| pillow | [CVE-2026-112894](https://osv.dev/vulnerability/GHSA-jg86-v3jv-hrpm) | HIGH | >= 5.1.0, < 13.0.0 |
| pillow | [CVE-2026-112406](https://osv.dev/vulnerability/GHSA-f2g6-542v-9j58) | HIGH | >= 5.1.0, < 13.0.0 |
| pillow | [CVE-2026-112399](https://osv.dev/vulnerability/GHSA-5xm2-6676-qcp9) | HIGH | >= 8.1.0, < 13.0.0 |
| pillow | [CVE-2026-112892](https://osv.dev/vulnerability/GHSA-gg2r-wvfm-q9rx) | HIGH | >= 4.1.0, < 13.0.0 |
| pillow | [CVE-2026-112393](https://osv.dev/vulnerability/GHSA-332p-7hrc-92wf) | CRITICAL | >= 2.0.0, < 13.0.0 |
| pillow | [CVE-2026-112396](https://osv.dev/vulnerability/GHSA-4rr5-89j8-mwwm) | MODERATE | >= 11.3.0, < 13.0.0 |
| pillow | [CVE-2026-96638](https://osv.dev/vulnerability/GHSA-24rc-8hj2-v98c) | MODERATE | >= 9.1.0, < 13.0.0 |
| pillow | [CVE-2026-96641](https://osv.dev/vulnerability/GHSA-4rm8-3hmm-39fg) | MODERATE | < 13.0.0 |
| pillow | [CVE-2026-96640](https://osv.dev/vulnerability/GHSA-mrfp-p49p-3hf2) | HIGH | >= 5.1.0, < 13.0.0 |
| pillow | [CVE-2026-96642](https://osv.dev/vulnerability/GHSA-3j72-p6qg-6xp7) | HIGH | < 13.0.0 |
| pillow | [CVE-2026-96639](https://osv.dev/vulnerability/GHSA-v9pv-5gc8-w2m6) | CRITICAL | >= 11.0.0, < 13.0.0 |
| pillow | [CVE-2026-96643](https://osv.dev/vulnerability/GHSA-g4qv-2jxx-769h) | HIGH | >= 11.0.0, < 13.0.0 |
| pillow | [CVE-2026-96637](https://osv.dev/vulnerability/GHSA-g842-9rc4-69pw) | HIGH | < 13.0.0 |
| pillow | [CVE-2026-96644](https://osv.dev/vulnerability/GHSA-9v9v-9qvf-h2hj) | HIGH | < 13.0.0 |
| pillow | [CVE-2026-96778](https://osv.dev/vulnerability/GHSA-g7cr-3p24-7wf7) | HIGH | >= 9.4.0, < 13.0.0 |
| pillow | [CVE-2026-96636](https://osv.dev/vulnerability/GHSA-p8hx-v2p6-rp84) | MODERATE | < 13.0.0 |
| pillow | [GHSA-78g4-xqwv-q3g8](https://osv.dev/vulnerability/GHSA-78g4-xqwv-q3g8) | HIGH | >= 11.1.0, < 13.0.0 |
| pillow | [CVE-2026-114501](https://osv.dev/vulnerability/GHSA-654x-cwwv-5j9c) | MODERATE | >= 11.2.1, < 13.0.0 |
| pillow | [CVE-2026-112398](https://osv.dev/vulnerability/GHSA-5x8w-8jj5-q52h) | CRITICAL | < 13.0.0 |

### npm: 14 distinct records, formerly affecting 10 nodes

| Package | Advisory / source | Severity | Affected range |
| --- | --- | --- | --- |
| @vitest/mocker | [GHSA-qxg6-89mg-rqv8](https://github.com/advisories/GHSA-qxg6-89mg-rqv8) | moderate | `>=2.1.0-beta.7 <4.1.12` |
| @vitest/mocker | [GHSA-xp26-3454-mjgp](https://github.com/advisories/GHSA-xp26-3454-mjgp) | moderate | `>=4.1.11 <4.1.12` |
| follow-redirects | [GHSA-q3jh-wrc6-jgq8](https://github.com/advisories/GHSA-q3jh-wrc6-jgq8) | high | `>=1.16.0 <1.16.1` |
| follow-redirects | [GHSA-8r9p-f939-6h3c](https://github.com/advisories/GHSA-8r9p-f939-6h3c) | high | `>=1.16.0 <1.16.1` |
| postcss-selector-parser | [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf) | moderate | `<7.1.6` |
| undici | [GHSA-4qv8-2p9j-2685](https://github.com/advisories/GHSA-4qv8-2p9j-2685) | moderate | `>=7.0.0 <7.30.1` |
| undici | [GHSA-f72v-6w45-q472](https://github.com/advisories/GHSA-f72v-6w45-q472) | moderate | `>=7.15.0 <7.30.1` |
| undici | [GHSA-xjj6-f33q-929c](https://github.com/advisories/GHSA-xjj6-f33q-929c) | high | `>=7.18.0 <7.30.1` |
| vite | [GHSA-698v-4r3x-3vcv](https://github.com/advisories/GHSA-698v-4r3x-3vcv) | moderate | `>=8.0.0 <=8.1.5` |
| vite | [GHSA-r825-w8mm-5pxw](https://github.com/advisories/GHSA-r825-w8mm-5pxw) | moderate | `>=8.0.0 <=8.1.5` |
| vite | [GHSA-587h-7wmj-h5pm](https://github.com/advisories/GHSA-587h-7wmj-h5pm) | high | `>=8.0.0 <=8.1.5` |
| vite | [GHSA-9jrq-w75r-8gcw](https://github.com/advisories/GHSA-9jrq-w75r-8gcw) | low | `>=8.0.0 <=8.1.5` |
| vite | [GHSA-rq7h-c2jc-7f22](https://github.com/advisories/GHSA-rq7h-c2jc-7f22) | moderate | `>=8.0.0 <=8.1.5` |
| zod | [GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5) | high | `<4.6.6` |

The `jsdom`, `postcss-nested`, `tailwindcss` and `vitest` findings propagate
from the vulnerable children above; they do not represent additional unique advisory
IDs. The installed braces 3.0.3 is unchanged and not reported in either current npm
audit. Historical Tailwind/braces findings are not treated as a current passing
claim without the fresh audits; the complete current dependency tree is now clean.

## Changed-file scope

Only these nine repository files are changed by this remediation, relative to the
already-implemented Phase 13 working tree:

1. `backend/requirements.txt`
2. `backend/requirements-dev.txt`
3. `frontend/package.json`
4. `frontend/package-lock.json`
5. `backend/tests/unit/test_dependency_compatibility.py` (new)
6. `frontend/tests/unit/dependency-compatibility.test.ts` (new)
7. `documentation/phases/PHASE_13_DEPENDENCY_REMEDIATION.md` (this new report)
8. `documentation/phases/PHASE_13_SECURE_CHAT.md`
9. `documentation/CURRENT_PROJECT_STATUS.md`

Existing Phase 13 implementation files, HTTP/WebSocket contracts and migration are
preserved. The unrelated `postman/README.md` BOM-only edit remains untouched.
Protected output/tmp artifacts remain outside every intended review/staging manifest.

## Not verified / remaining operational limitations

No actual Docker image rebuild/runtime deployment, browser visual acceptance,
production WSS/TLS endpoint, external SMS/email/Cloudinary delivery, sustained load or
online key rotation was exercised. The audit tests use local/synthetic fixtures, not
external provider credentials. Registry metadata supports the Docker Python version;
that is not a Docker-runtime test. Scanner results do not prove the absence of all
unknown vulnerabilities. Production private storage/secret provisioning and prior
Phase 12 LOW architecture/OpenAPI observations remain separate acceptance items.

## Final preservation and outcome

All required local dependency and regression gates passed. The backend total is
1,824 (the 1,821 baseline plus three compatibility tests); frontend is 390 (the
387 baseline plus three compatibility tests). The inherited TestClient warning is
not a new failure. No dependency advisory remains in any of the three fresh audits.

All 22 development-table data fingerprints and all 22 schema hashes match the
pre-remediation baseline after the full suites and live synthetic cleanup. The
canonical OpenAPI SHA-256 is unchanged:
`56be05ca3b49c4a842fef83441c537125a5bb04aad82055775b6325a965558f6`.
Existing application/HTTP/WebSocket source, API documentation, migration and prior
test files are byte-identical to their pre-remediation versions. Only the nine
listed files changed. All 13 protected artifacts and the unrelated Postman README
remain byte-identical to the baseline and outside the intended Phase 13 manifest.

Combined working-tree inventory: 35 unstaged tracked modifications (34 Phase 13
plus the unrelated README), 35 untracked paths (22 Phase 13 plus 13 protected),
zero staged paths and zero deletions. The updated Phase 13 manifest contains
exactly 56 implementation/remediation paths. Branch and committed HEAD are unchanged.

**READY FOR INDEPENDENT FINAL AUDIT.** This is not production readiness or Phase 13
closure. Independent security review and the operational acceptance items above
remain. No staging, commit, push or Phase 14 work was performed.
