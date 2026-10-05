# Phase 7 Seller Verification Threat Model

Date: 2026-09-25. Engineering review, not OWASP ASVS certification.

## Assets and trust boundaries

Private identity evidence, review decisions, authenticated accounts and reviewer authority.
Client forms/filenames/MIME/IDs are hostile. API schemas and current DB roles are authoritative.
The storage provider is private infrastructure, never a public content host.
Review references are random routing identifiers, not authorization credentials.
Signed retrieval grants are secrets even though their contents reveal no internal identifier.

## Threats and controls

| Threat | Control and verification |
|---|---|
| BOLA / IDOR | Own lookup derives user from bearer auth; access lookup returns generic 404 for another user's evidence; admin role is queried from DB |
| Self-approval / privilege escalation | Admin-only review, no self-review, strict bodies, no role/status/user_id/reviewed_by assignment |
| Stale review authority | Locked active account and current role checked again inside transaction and on download |
| Duplicate requests / race | User locks plus UNIQUE(user_id, generated active_slot); deterministic reviewer locking; terminal-state checks |
| Evidence replacement during review | Upload only PENDING; submit and upload serialize; issued grants must match current evidence key |
| Invalid state / missing evidence | All three types required; DB state/date/reason checks; duplicate type DB constraint |
| Malicious uploads / polyglots | JPEG/PNG-only decoding, actual format/MIME/extension checks, fresh-pixel re-encoding, sanitized stored metadata |
| Decompression / size abuse | 5 MiB input/output cap, dimensions/pixel bound, four ingress slots, rate limits, timeout, bounded multipart counts |
| Path traversal / private-file overwrite | No user filenames in storage, random keys, strict key format, exclusive create, symlink/junction checks; collision does not delete existing object |
| Replay / credential leakage | HMAC ticket in X-Evidence-Ticket only, 60-second lifetime, one-use, actor binding, current authorization; no credential in URL |
| Unaudited evidence access | Current authorization, hash check and EVIDENCE_READ commit before bytes; storage/audit/commit failure releases no image |
| Expired/stale handwritten proof | Server deadline, body challenge binding, draft-only atomic renewal removes old handwritten evidence; reviewer compares pixels manually |
| Invalid JSON rate-limit bypass | Actual-peer ASGI limit before parser, plus authenticated user budgets; forwarded headers ignored |
| Public seller privacy | Only DB-derived seller_verified boolean; private attempt/evidence/review data excluded |
| Document execution / browser leakage | Attachment, nosniff, sandbox CSP, no-store/no-referrer; no public links or static mount |
| Log leakage | Metadata-only audit rows, fixed event labels, download access-log suppression, query-free proxy logging |
| Partial transaction | DB changes/audit commit together; file rollback compensation; exact replacement cleanup and fixed alert on failure |
| Cross-account frontend state | User-specific private query keys, session-version checks, logout purge and form remount |
| Misconfigured production storage | Local adapter refuses non-development; repository web/source paths rejected; Git/Docker exclusions |
| Error/validation reflection | Generic errors; existing sanitized validation handler; no document/password/token value logging |

Regression coverage includes API ownership/roles/eligibility, MIME spoofing, executable/oversized
uploads, unsafe filenames, model constraints, audit failure rollback, revoked reviewer access,
one-use/expired/tampered tickets, replacement invalidation, cache/session isolation and real-MySQL races.

## Explicit limitations and required production work

- Local adapter/tickets/limits are single-process development infrastructure.
- Production adapter must retain private bucket ACLs, authenticated retrieval and shared one-use
  grant semantics. This phase does not install S3/KYC credentials or integrate a provider.
- External proxies, CDNs, APM and HTTP-client debug logging must never capture ticket headers or grant bodies.
  Supplied Uvicorn/NGINX controls do not prove third-party observability is configured safely.
- OS administrators can access local files; Windows ACL/encryption and operational access controls
  remain deployment responsibilities.
- Define data minimization, consent, retention/deletion, backup protection and reviewer conduct.
- Filesystem/DB crash reconciliation, malware scanning policy and human fraud detection are not
  replaced by upload type validation.
- The handwritten challenge expires for draft submission and can be renewed; it is not a login OTP. Reviewer comparison is manual.
- Backend current-state checks are the authorization boundary; UI prerequisites are only UX controls.
- Fresh browser and Docker/NGINX runtime checks are environment-blocked.
- Tailwind 3's build dependency braces@3.0.3 has an unresolved High recursion/stack-exhaustion
  advisory (GHSA-vfj7-8cjw-p6xm). The 2026-10-05 full npm audit reports five affected graph nodes
  sharing this root; the production-only audit is clean. This remains a production/security
  blocker for a separate dependency-migration task, not risk acceptance. Tailwind 3 is retained.

## Primary references

Controls were informed by the
[OWASP file upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
and [Pillow security guidance](https://pillow.readthedocs.io/en/stable/handbook/security.html).
These recommend bounded validation and image rewriting; neither makes arbitrary uploads risk-free.
The active-slot constraint respects
[MySQL generated-column foreign-key restrictions](https://dev.mysql.com/doc/refman/8.4/en/create-table-generated-columns.html).
