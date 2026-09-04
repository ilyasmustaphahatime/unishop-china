# Phase 6 Profile Security Threat Model

## Protected assets and trust boundaries

Protected assets are profile ownership, immutable public identifiers, onboarding state, account verification state, auth roles/status, private contact data, and existing authentication/session records. Browser input and public UUIDs are untrusted. The validated bearer subject plus current ACTIVE database state is the ownership authority.

## Threats and controls

| Threat | Control | Verification |
|---|---|---|
| BOLA/IDOR | Self-service writes have no user/path identifier; `user_id` comes only from `get_current_user` | Cross-user integration test |
| Broken property authorization | Strict update schema accepts only display name, bio, and city | 16-field mass-assignment matrix |
| Public identifier enumeration | Random UUID public IDs; no authorization depends on obscurity | uniqueness/model/API tests |
| Contact/internal-data disclosure | Dedicated public response schema omits internal ID, user ID, email, phone, role, and status | public privacy test and OpenAPI review |
| Inactive identity exposure | Public query requires ACTIVE user and completed onboarding | suspended-profile test |
| Client-forged onboarding | Dedicated strict empty request; server validates committed profile | incomplete, success, idempotency, extra-field tests |
| Duplicate profiles | user-row lock plus unique user constraint | real MySQL concurrency test |
| Lost/corrupt race state | single lock order and atomic transactions | creation/update/onboarding/race stress matrix |
| Partial write | transaction rollback | controlled failure-injection test |
| Stored XSS | plain text contract and React text rendering; no raw HTML API | backend/frontend inert-string tests and source scan |
| Validation reflection | existing global sanitized 422 handler excludes input/context/URLs | malicious validation tests |
| Resource exhaustion | bounded peer/user in-memory sliding windows | HTTP 429 and Retry-After test |
| Sensitive logging | no request body or profile contents logged | focused source review |
| Stale cross-user frontend data | user-scoped query key and private-cache removal | frontend cache-isolation tests |

## Account-state matrix

| State | Authenticate for profile | Read own | Mutate/complete | Public visibility |
|---|---|---|---|---|
| ACTIVE | allowed | allowed | allowed | only after completion |
| SUSPENDED | rejected by auth dependency | rejected | rejected | hidden as 404 |
| BANNED | rejected by auth dependency | rejected | rejected | hidden as 404 |
| DELETED | rejected by auth dependency | rejected | rejected | hidden as 404 |

## Targeted OWASP API Security Top 10 2023 review

- API1 BOLA: ownership derives from the bearer subject, not a client ID.
- API2 Broken Authentication: the closed ACTIVE-only JWT dependency is reused unchanged.
- API3 Broken Object Property Level Authorization: strict allow-list schemas reject privileged/internal fields.
- API4 Unrestricted Resource Consumption: writes and public reads are bounded, with bounded key cardinality.
- API5 Broken Function Level Authorization: only authenticated ACTIVE users can mutate/complete.
- API8 Security Misconfiguration: PATCH is explicitly allowed in CORS; production dev routes remain absent.
- API9 Improper Inventory: four Phase 6 operations occur exactly once in OpenAPI.
- API10 Unsafe Consumption: no third-party service is used by profiles.

## Targeted ASVS 5.0 review

Access control, input validation, output encoding, authentication/session regression, data minimization, error handling, logging, and API configuration were targeted. This report does not claim ASVS certification.

## Residual risks

- Rate limits are process-local until production adopts shared storage.
- Access JWTs remain valid until their existing 15-minute expiry.
- City values are deliberately bounded in code/schema until Phase 8 migrates to a managed city catalog.
- Database deadlock victims receive an atomic rollback and must retry.
- Browser automation was unavailable; automated component tests and real HTTP runtime evidence are fresh, while prior authentication browser evidence is inherited.
