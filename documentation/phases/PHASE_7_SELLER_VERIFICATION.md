# Phase 7 — Secure Seller Verification

Implemented 2026-09-25 on feature/authentication, baseline
`5f068e8bf8fc54eaa8f4ed917a69e0d1baeccdd3`. No Phase 8 work, staging, commit or push.
The user explicitly confirmed the draft → upload → submit workflow.

## Scope and state machine

Only seller verification infrastructure and its authenticated user page are implemented.
No products/listings, payments, chat, orders, admin dashboard UI or KYC provider integration.
Approval records VERIFIED but does not grant SELLER/ADMIN roles or selling permissions.
Future marketplace authorization must independently check verification and account state.

- POST action=start creates PENDING (a private draft, submitted_at is null).
- Three evidence types are required: SELFIE, WECHAT_PROOF, HANDWRITTEN_CODE.
- POST action=submit requires all three and moves PENDING → UNDER_REVIEW.
- Admin approval/rejection moves UNDER_REVIEW → VERIFIED/REJECTED.
- Rejected users may create a new independent draft. Old evidence/audit history remains private.
- Duplicate active attempts and repeated decisions return 409; no silent overwrite.
- Evidence can be replaced only during PENDING.
- ACTIVE + email_verified + phone_verified are checked from locked database rows for
  starting/uploading/submitting and again for the applicant during review.
- An administrator may not review their own application.

The per-attempt random handwritten challenge is shown only in authenticated JSON/UI text.
The reviewer must compare the handwritten image with that challenge and assess identity/proof.
There is no OCR, automated identity match, biometric/liveness claim or challenge-expiry promise.
These images are sensitive personal evidence; do not use real personal documents in development.

## Database and migration

New head: `b7c1d2e3f4a5`, parent `a61b2c3d4e5f`.
Adds seller_verifications, seller_evidence and seller_verification_audit.
Existing authentication/profile tables are not rewritten.

Verification uses internal UUID keys and a separate random 128-bit review_reference.
Normal response schemas omit internal id/user_id/reviewed_by, storage keys, hashes and URLs.
The admin path parameter called id contains the opaque review_reference, never a database ID.

A stored generated active_slot is 1 except for rejected attempts, where it is NULL.
UNIQUE(user_id, active_slot) enforces one active draft/review/verified request while retaining
rejected history. The generated expression depends only on status, avoiding MySQL's restriction
on cascading foreign keys involving base columns of stored generated values.
Evidence has a unique verification/type pair, metadata constraints and a random storage key.

User-row serialization, current locking reads, transactions and unique constraints protect
creation/upload/submit/review. Review locks users in deterministic order.
Audit rows for START, SUBMISSION, UPLOAD, APPROVAL and REJECTION commit atomically with changes.
Operational logs contain event labels only, not IDs, reasons, files, credentials or challenge values.
Database/storage atomicity is best-effort across two systems: rollback compensates new file writes;
post-commit replacement deletes the old file. Cleanup failure emits a fixed safe alert.

## API

All endpoints require bearer authentication. Cookie-only requests do not authorize actions.

| Method | Path | Body / result |
|---|---|---|
| POST | /api/v1/seller-verification | Strict JSON action=start or action=submit; returns current safe state |
| GET | /api/v1/seller-verification/me | Own latest attempt or null |
| POST | /api/v1/seller-verification/evidence | Multipart: exactly file + evidence_type |
| POST | /api/v1/seller-verification/evidence/access | JSON review_reference + evidence_type; owner/admin only |
| GET | /api/v1/seller-verification/evidence/content | Signed ticket query + same actor's bearer token; one-use attachment |
| GET | /api/v1/admin/seller-verifications | Admin queue, 50 per page; bounded offset |
| POST | /api/v1/admin/seller-verifications/{id}/approve | Admin; strict empty JSON object |
| POST | /api/v1/admin/seller-verifications/{id}/reject | Admin; strict rejection_reason, 3–500 sanitized characters |

Success: 200. Authentication: 401. Eligibility/admin: 403. Unknown/foreign evidence: 404.
Invalid state: 409. Invalid payload/image or expired/replayed grant: 422.
Ingress body cap: 413. Rate limit: 429 + Retry-After. Storage/operation failure: safe 503.
Private responses, including root POST and error responses, use no-store, no-cache and no-referrer.
The upload OpenAPI contract documents multipart explicitly without triggering unbounded automatic parsing.

Per minute limits use the existing process-local architecture:
submission 5/user and 15/peer; uploads 12/user and 36/peer; admin 30/user and 90/peer;
reads/download grants 60/user and 180/peer. Upload ingress has a separate 36/peer limit,
four concurrent slots and a 30-second body timeout.

## Evidence and storage boundaries

Only JPEG/PNG, maximum 5 MiB, maximum 12 million pixels and 6000 pixels on either axis.
Single-frame only. Extension, filename and declared MIME must agree with decoded format.
Original filenames never become storage paths or metadata. Simple ASCII filenames only.
Pillow decodes only the two allowed formats; a fresh pixel image strips EXIF, text, comments,
ICC metadata and trailing injected content. Stored hash and size refer to sanitized bytes.
Decoded output is also size-bounded.

Ingress is bounded to 5 MiB + 64 KiB multipart overhead before parser execution, including
chunked requests. Extra/duplicate fields or file parts are rejected. Filesystem keys are
random; traversal, symlinks and junctions are rejected. Repository-local storage overrides
must stay under backend/private_uploads, never frontend/public or application source.

StorageProvider defines upload, delete, read, generate_signed_url and redeem.
LocalPrivateStorage is development-only; default path:
`backend/private_uploads/seller-evidence`.
Optional environment override: SELLER_PRIVATE_STORAGE_DIR (private absolute path).
Git/Docker contexts exclude private_uploads. No static mount or public evidence URL exists.
Unix creation permissions are restrictive; Windows deployments require appropriate OS ACLs.

Production fails closed with 503: no production local-disk fallback exists.
A private S3/object-store adapter can implement this contract and be supplied through dependency
injection, with durable shared grant storage. No cloud integration/credentials were added.
Do not expose object-store keys or raw vendor presigned URLs containing those keys.

## Explicit URL-privacy exception for authorized private retrieval

Ordinary verification responses have no evidence URLs. Only the access endpoint issues a
60-second signed temporary API URL after authorization. Its ticket contains random nonce + HMAC,
not user/document IDs, paths, keys or personal information. Grant metadata remains server-side.
The token is bound to the authenticated actor, one-use, and authorization is rechecked at retrieval.
Replacement invalidates an older grant by checking the current storage key; hash verification
detects unexpected on-disk changes. This capability is not a public link or navigation destination.

This is a narrow exception to Phase 6.1's no-sensitive-navigation policy, specifically required
for private signed evidence retrieval. Never render the URL as a share link, navigate to it,
store it in browser history/storage, or log/copy it. Use authenticated programmatic retrieval.
Uvicorn's access filter suppresses this route; NGINX omits query strings and suppresses this
location's access/error logs. External proxies/APM must apply equivalent redaction before deployment.
Downloads are attachments with nosniff, sandbox CSP, no-store and no-referrer.

## Frontend

Authenticated `/seller/verification`, nested under the existing profile/onboarding gate.
Profile page links to it. Draft/start/upload/submit/status/rejection/resubmission states included.
Required-image and size/extension/MIME checks run client-side for usability; server validation
remains authoritative. Phone/email prerequisites disable controls.
No admin UI and no evidence URL is put into the page or navigation.

Query keys are account-specific and private. Session epochs reject stale actions/results.
Session changes remount the form and clear selected-file state. Logout removes seller query
entries even if created by a mutation before a query observer existed.
No new localStorage/sessionStorage persistence or token handling architecture.

## Verification evidence

- Full backend suite: 843 passed, 0 failed, 0 skipped.
- Targeted Phase 7 backend regressions: 52 cases.
- Frontend: 179 passed (16 new Phase 7 cases).
- Repeated MySQL concurrency: 4 cases × 3 runs passed.
- Live Uvicorn/MySQL: 58 checks passed; synthetic cleanup, server stop and preservation confirmed.
- Isolated migration: upgrade/downgrade/upgrade passed, including a synthetic seller draft;
  existing users/profiles preserved. Development database was never downgraded/reset.
- Alembic current=head=b7c1d2e3f4a5, no drift.
- Ruff, compileall, pip check, TypeScript, ESLint and production build passed.
- pip-audit and both npm audits: no known vulnerabilities at verification time.
- Browser: ENVIRONMENT BLOCKED. Browser skill connection fails before a tab is available.
- Docker/NGINX runtime: unavailable; source configuration checked, no runtime PASS claimed.

All seven pre-existing table fingerprints remain unchanged: users 4, roles 4,
phone challenges 3, refresh sessions 7, reset/email challenges 0, profiles 0.
New seller tables contain no synthetic leftovers after verification.
The prior Starlette TestClient deprecation warning remains unrelated.

Reproduce from backend:
```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m compileall -q app tests scripts alembic
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip_audit
.\.venv\Scripts\python.exe scripts/audit_security_http.py
.\.venv\Scripts\python.exe scripts/audit_public_handle_migration.py --seller-verification
```

From frontend: npm test -- --run; npx tsc -b; npm run lint; npm run build;
npm audit; npm audit --omit=dev.
Run app locally with backend `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
and frontend `npm run dev`.

## Remaining risks / release conditions

This is locally verified implementation, not production or KYC certification.
Production object-storage adapter, encryption/ACLs, shared one-use grant store and distributed
limits must be configured and verified. Define consent, retention, evidence erasure, reviewer
procedures and operational access auditing before real personal evidence is accepted.
Local filesystem and MySQL cannot commit atomically: crash/ambiguous-commit reconciliation and
orphan cleanup need an operational policy; current compensation handles ordinary failures.
Retained rejected evidence is not automatically erased. Never delete files merely by user-supplied
path; reconcile exact private keys against DB references. Backups must protect both DB and objects.

Manual reviewers, not this software, determine whether images establish identity or genuine
WeChat ownership. Documents can still be fraudulent even when technically valid images.
No antivirus/KYC provider is claimed; decode/re-encode and type limits are defense in depth.
Browser and container/proxy runtime verification remain open. Do not infer production readiness.

## Changed files

See the final implementation manifest appended below. No existing local .env was changed.


| File | Reason |
|---|---|
| `.gitignore` | Exclude private evidence directories. |
| `backend/.env.example` | Document private storage override and clarify unused legacy expiry option. |
| `backend/alembic/versions/b7c1d2e3f4a5_seller_verification.py` | Add verification/evidence/audit tables, constraints and reversible isolated downgrade. |
| `backend/app/api/v1/admin/seller_verification_routes.py` | Bounded admin queue and strict approve/reject endpoints. |
| `backend/app/api/v1/router.py` | Register only the Phase 7 seller and review routes. |
| `backend/app/api/v1/seller_verification/dependencies.py` | Current admin authorization, existing rate-limit integration and fail-closed storage selection. |
| `backend/app/api/v1/seller_verification/routes.py` | Own lifecycle, bounded multipart ingestion and authorized signed retrieval. |
| `backend/app/core/config.py` | Private development storage setting. |
| `backend/app/core/evidence_security.py` | Bound upload ingress and prevent capability URL access logging. |
| `backend/app/main.py` | Attach upload boundary and private headers for seller/admin responses. |
| `backend/app/models/__init__.py` | Register new metadata with SQLAlchemy/Alembic. |
| `backend/app/models/seller_verification.py` | Verification/evidence/audit domain and database invariants. |
| `backend/app/repositories/seller_verification_repository.py` | Current locked reads and owner/reference/evidence queries. |
| `backend/app/schemas/seller_verification.py` | Strict input allowlists and minimal response contracts. |
| `backend/app/services/seller_verification_service.py` | Transactional workflow, eligibility/role checks, audit events and storage compensation. |
| `backend/app/services/storage_service.py` | Private provider interface, local implementation, image rewriting and signed actor-bound grants. |
| `backend/requirements.txt` | Pin Pillow 12.3.0 for bounded image validation and re-encoding. |
| `backend/scripts/audit_public_handle_migration.py` | Extend isolated migration verifier with a Phase 7 cycle without dev downgrade. |
| `backend/scripts/audit_security_http.py` | Exercise live seller lifecycle and preserve all ten tables with temporary private storage. |
| `backend/tests/conftest.py` | Include seller tables in isolation/preservation checks. |
| `backend/tests/integration/test_seller_verification.py` | API, model, ownership, admin, file, privacy, rollback and deployment-boundary security tests. |
| `backend/tests/integration/test_seller_verification_concurrency.py` | Real-MySQL duplicate-start, upload, submission and review races. |
| `backend/tests/unit/test_public_handles.py` | Keep Phase 6 handle assertions scoped; Phase 7 has its own explicit route-contract tests. |
| `backend/tests/unit/test_seller_storage_security.py` | Malicious filenames, image metadata, dimensions, path/collision safety and ticket security. |
| `documentation/CURRENT_PROJECT_STATUS.md` | Record Phase 7 results and production/runtime limitations. |
| `documentation/README.md` | Index implementation and threat model. |
| `documentation/phases/PHASE_7_SELLER_VERIFICATION.md` | Implementation report, operating instructions, results, limitations and this manifest. |
| `documentation/security/PHASE_7_SELLER_VERIFICATION_THREAT_MODEL.md` | Threats, controls, negative tests and remaining release conditions. |
| `documentation/security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md` | Label historic counts and explain the narrow signed-private-retrieval exception. |
| `frontend/src/app/queryClient.ts` | Purge seller cache entries on session clear, including mutation-created entries. |
| `frontend/src/app/router.tsx` | Add protected seller-verification page under existing onboarding gate. |
| `frontend/src/features/sellerVerification/api.ts` | Safe JSON/multipart API calls, no ownership/status assignment. |
| `frontend/src/features/sellerVerification/hooks.ts` | Account-specific private queries and session-bound mutations. |
| `frontend/src/features/sellerVerification/schemas.ts` | Strict response parsing and client file validation. |
| `frontend/src/features/sellerVerification/types.ts` | Typed seller workflow and evidence categories. |
| `frontend/src/pages/seller/SellerVerificationPage.tsx` | Draft/upload/submit/review feedback and resubmission UI. |
| `frontend/src/pages/shared/ProfilePage.tsx` | Link to seller verification. |
| `frontend/src/routes/routePaths.ts` | Allow the new fixed internal navigation destination. |
| `frontend/tests/unit/development-route.test.tsx` | Update future-phase route boundary for authorized Phase 7. |
| `frontend/tests/unit/seller-verification.test.tsx` | Page/form/route, contract, file and session/cache regressions. |
| `infrastructure/nginx/nginx.conf` | Upload body ceiling and query/capability-safe proxy logging. |

Final Git state: 41 modified/new paths, 0 staged files, no deletions; HEAD remains
`5f068e8bf8fc54eaa8f4ed917a69e0d1baeccdd3`. Diff whitespace check passed.
No real local .env, secret file, private image, database dump or generated build output was added.
OpenAPI: 31 local / 35 all-development / 29 production-safe operations, 8 Phase 7 operations,
zero duplicate operation IDs. Production routes fail closed without the storage adapter.
