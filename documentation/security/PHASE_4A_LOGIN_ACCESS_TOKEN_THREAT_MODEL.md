# Phase 4A Login and Access Token Threat Model

## Scope

This is a targeted Phase 4A threat model using OWASP API Security Top 10 2023 and relevant OWASP ASVS 5.0 authentication, session, validation, cryptography, and logging guidance. It is not a penetration test or ASVS certification.

| Threat | Attack path | Security control | Test evidence | Residual risk / Phase 4B |
|---|---|---|---|---|
| Brute force | Repeated passwords from one network peer | Five attempts per 60 seconds using actual connection peer; 429 with retry delay | IP-limit and recovery tests | Distributed attackers require a shared/global defense |
| Credential stuffing | One password set tested across accounts | Per-peer and per-normalized-identifier limits | Identifier isolation and IP isolation tests | Add monitoring and breached-password policy later |
| User enumeration | Compare unknown, wrong-password, or inactive responses | Identical 401 message, status, shape, and no status disclosure | Generic-response integration tests | Large-scale timing analysis remains possible |
| Timing attack | Unknown user skips expensive Argon2 work | One startup-generated dummy Argon2 hash uses the same verifier path | Injected verifier spy proves dummy path | Hardware/load variance cannot be eliminated completely |
| Argon2 denial of service | Force many expensive password checks | Rate limits run before account lookup and Argon2; bounded state | Blocked-request service-call test | Multi-process limits need Redis in production |
| Password leakage | Logs, errors, responses, or persistence expose password | No credential logging; dedicated response schemas; no DB write | Negative field and response tests | Operational log configuration still requires review |
| JWT theft | Steal a Bearer token from browser or transit | Fifteen-minute token; TLS required in deployment; no browser persistence added | Token lifetime and frontend regression tests | Phase 4B adds HttpOnly refresh cookie and revocation strategy |
| JWT tampering | Modify payload or signature | HS256 signature validation with one configured algorithm | Modified and wrong-signature tests | Protect and rotate server secret operationally |
| Algorithm confusion | Supply `none` or another algorithm | Startup permits HS256 only; decoder supplies a one-item algorithm allowlist | Unsafe-configuration tests | Key rotation is Phase 4B/operations work |
| Token-type confusion | Use a refresh-like JWT as access | Required `type=access` claim | Wrong-type unit and `/me` integration tests | Refresh tokens do not yet exist |
| Expired-token reuse | Replay after expiration | Required and verified `exp`, `nbf`, `iat`; bounded skew | Expired-token tests | No early revocation until Phase 4B |
| Wrong issuer/audience | Replay a token from another service/client | Exact issuer and audience validation | Wrong issuer/audience tests | Coordinate values across deployments |
| Missing/malformed subject | Use no subject or invalid user ID | Required canonical UUID `sub` | Missing and malformed subject tests | Future subject migrations need explicit versioning |
| Weak JWT secret | Guess or use placeholder signing key | Startup rejects missing, short, and placeholder secrets | Startup configuration tests | Secret storage/rotation remains operational responsibility |
| Mass assignment | Submit role, status, verification, admin, or token fields | Pydantic `extra=forbid`; server-owned roles/status | Privileged-extra-field tests | Apply the same pattern to future APIs |
| Rate-limit bypass | Forge proxy headers or vary input formatting | Actual peer only; identifiers normalized before keyed HMAC | X-Forwarded-For and normalization tests | Trusted proxy support needs an explicit allowlist design |
| Rate-limit memory exhaustion | Generate unlimited unique keys | Bounded limiter map and expired-key cleanup | Existing bounded-memory limiter tests | Process-local eviction reduces precision under attack |
| Credential/token logging | Authorization or secrets appear in logs | No token values or Authorization headers are logged; safe exceptions | Static inspection and negative output tests | Infrastructure access logs must keep header redaction |
| SQL injection | Place SQL syntax in identifier | Pydantic validation plus SQLAlchemy bound expressions | Repository inspection and invalid-input tests | Continue banning request-built raw SQL |
| Inactive-account bypass | Valid credentials for suspended/banned/deleted user | ACTIVE check during login and every authenticated request | Status login and `/me` tests | Administrative status-change audit is future work |
| Stale authorization | Token retains obsolete roles | Roles are not embedded; `/me` loads roles from MySQL | Role-change-after-login test | Add endpoint-specific object authorization in later phases |
| Sensitive response fields | ORM serialization leaks hashes or security records | Dedicated `SafeAuthenticatedUserResponse` allowlist | Exact-field integration assertions | Review every future response model |
| Development feature leakage | Fake SMS inbox appears outside development | Existing environment, loopback, and production OpenAPI guards unchanged | Full Phase 3B regression suite | Keep production configuration fail-closed |

## OWASP API Security Top 10 2023 mapping

- API1/API5: the authentication dependency establishes identity; future object/function authorization remains outside Phase 4A.
- API2: Argon2 verification, generic authentication failure, JWT validation, account-status checks, and short expiry.
- API3: strict input and response schemas prevent property-level mass assignment and leakage.
- API4/API6: bounded IP and identifier limits protect login as a sensitive business flow.
- API8: fail-closed JWT and development-feature configuration.
- API9: OpenAPI tests enforce the exact Phase 4A route inventory.
- API10: no request-controlled external service call exists in login.

## ASVS 5.0 targeted mapping

- Authentication: generic failures, secure password verification, inactive-account enforcement, brute-force controls.
- Session/token management: signed short-lived token, required temporal/type/issuer/audience claims, no persistent frontend storage.
- Validation and business logic: strict schemas, canonical identifiers, server-owned status and roles.
- Cryptography: Argon2id, HMAC-SHA256 limiter keys, cryptographically random JTI, configured HS256 key.
- Error handling and logging: library errors are mapped to safe responses and credential/token values are not logged.
- Data protection: dedicated response allowlists and no token/password/OTP database storage.

Full ASVS certification is not claimed.
