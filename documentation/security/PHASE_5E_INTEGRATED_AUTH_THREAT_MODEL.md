# Phase 5E Integrated Authentication Threat Model

## Scope and trust boundaries

This model covers registration, phone/email verification, login, access JWTs, `/auth/me`, refresh rotation, logout/logout-all, forgot/reset password, authenticated password change, validation/error handling, fake development providers, the React authentication client, and MySQL transaction boundaries. Phase 6 and all marketplace functionality are outside this closure gate.

Trust boundaries are:

1. browser or API client to FastAPI;
2. bearer access token to server-side user/status/role state;
3. refresh and CSRF cookies to the refresh-session database;
4. FastAPI services to MySQL/InnoDB;
5. verification/recovery services to delivery providers;
6. frontend memory to browser storage/cookies;
7. deployment configuration to development-only provider mounting.

The server, not the client, is the authorization authority. Frontend `ProtectedRoute` and `RoleRoute` are navigation controls only.

## Assets

- Argon2id password hashes and password authority
- access-token signing secret and verification-code HMAC secret
- opaque refresh tokens and their SHA-256 database references
- CSRF tokens and database binding
- phone, email, and password-reset challenges
- account status, verification flags, and roles
- refresh-family lineage and revocation state
- email/phone identifiers and development data

## Cross-feature security invariants

| Invariant | Required property | Evidence/result |
|---|---|---|
| User ownership | one principal cannot mutate another user's security state | bearer subject or server-side challenge ownership; IDOR tests pass |
| Role safety | auth endpoints never grant elevated roles | registration grants only `BUYER`; verification/recovery preserve roles |
| Account status | non-active accounts cannot gain security state or authenticate | all actual statuses reviewed; phone gap fixed and regression-tested |
| Password authority | old password fails after successful reset/change | real HTTP lifecycle and integration tests pass |
| Session revocation | policy-required refresh families fail after reset/change/logout | lifecycle and MySQL concurrency tests pass |
| Verification isolation | phone/email changes only its own flag/challenge | preservation tests pass |
| Purpose isolation | a challenge cannot cross phone/email/reset purposes | explicit 3×3 matrix passes |
| One-time challenges | used, expired, exhausted, or superseded challenges stay invalid | replay/concurrency tests pass |
| Authority source | identity/roles/status are loaded server-side | JWT subject plus current MySQL state |
| Transaction atomicity | multi-step security mutations commit together or roll back | failure injection and InnoDB races pass |

## Threats and mitigations

### Credential and identifier attacks

- Credential stuffing/brute force: login uses actual-peer and HMAC-identifier process-local sliding windows.
- Deterministic login enumeration/timing shortcut: unknown users receive dummy Argon2id work and the same public `401` as wrong-password/inactive users.
- Registration enumeration: explicit duplicate conflict remains an accepted LOW residual documented as AUTH-5E-003.
- Malformed normalization: strict email/Mainland China phone normalization, length bounds, type constraints, and sanitized `422` responses.

### JWT substitution and claim attacks

- HS256 is allow-listed; `none` and unsupported algorithms fail.
- Signature, issuer, audience, type, subject, JTI, `iat`, `nbf`, and `exp` are required and verified.
- Subjects must be canonical UUID strings.
- Future `iat`/`nbf`, wrong type, malformed subject/JTI, modified/expired tokens, and refresh-like tokens are rejected.
- Roles and mutable authorization state are not embedded in access JWTs; current user/status/roles are reloaded.

### Refresh-session attacks

- Tokens contain 512 bits of source entropy and only SHA-256 hashes are stored.
- CSRF uses cookie/header constant-time equality plus stored hash binding.
- Rotation locks the presented row, creates one descendant, and revokes the parent.
- Reuse revokes the entire family; concurrent presentation cannot create two usable descendants.
- Absolute family expiry prevents indefinite sliding renewal.
- Per-user active-family cap limits session accumulation.
- Revocation is user/family scoped; unrelated users/families remain intact.

### CSRF and Origin attacks

- Refresh/logout authority is the refresh cookie, so both exact Origin policy (when browser Origin is present) and double-submit CSRF are enforced.
- Bearer-authorized password change/email verification/logout-all require exact Origin policy but not ambient-cookie CSRF.
- Login/forgot/reset also use Origin policy; registration/phone operations do not derive authority from cookies.
- Missing Origin remains allowed for non-browser API clients. Browser-supplied malicious, lookalike, wrong-scheme, and wrong-port origins fail.
- `Forwarded`, `X-Forwarded-For`, and `X-Real-IP` are not trusted by application limiters or localhost guards.

### Recovery and verification attacks

- Phone/email/reset codes are six strict ASCII digits generated with `secrets.randbelow`.
- Password reset and email verification use explicit HMAC domain separation; phone is additionally isolated by repository/model and differs cryptographically from both prefixed purposes.
- Database stores HMACs only; fake providers retain plaintext only in bounded, expiring process memory.
- Attempts, expiry, newest-only selection, replay prevention, cooldown, and rolling issuance limits constrain guessing and flooding.
- Pending delivery prevents undelivered email/reset challenges from becoming usable.
- Phone verification now enforces ACTIVE account state before resend or verification.
- Concurrent verification/reset attempts serialize or use atomic conditional updates.

### Mass assignment and BOLA

- Every authentication request schema uses `extra="forbid"`.
- `user_id`, role/status, verification flags, password hash, and admin properties are rejected rather than silently ignored.
- Bearer operations derive the user only from validated claims; challenge operations query server-owned identifier/challenge relationships.

### Validation, error, and logging attacks

- The global validation handler returns only safe error type/location/fixed message.
- Submitted values, Pydantic context/URLs, request bodies, provider details, database errors, secrets, hashes, cookies, and tokens are not logged or reflected.
- Authentication and recovery failures use generic public contracts where designed.
- Payload and field limits reject unexpected structures and oversized strings before service work.

### Resource exhaustion

- Process-local bounded sliding-window limiters protect registration, login, refresh/logout, recovery, password change, and email verification.
- Durable challenge attempts/cooldowns/hourly issuance survive process restart for phone/email/reset where applicable.
- In-memory limiter keys and fake inboxes are bounded.
- Horizontal production deployment still requires shared limiting such as Redis; this is a documented residual.

### Provider and production misconfiguration

- Fake SMS/email/reset providers and routes require development configuration.
- Local inbox routes inspect the actual socket peer, not forwarded headers.
- Production configuration rejects fake-provider combinations, placeholder/weak secrets, insecure refresh cookies, invalid origins, and unsafe cookie settings.
- Production OpenAPI contains zero `/dev/` routes.

### Frontend token theft and redirect attacks

- Access tokens and user state live only in the in-memory Zustand store.
- Refresh token is HttpOnly and is not read by JavaScript; only the intended readable CSRF cookie is accessed.
- Credentialed requests are confined to the session client; bearer injection is centralized.
- Refresh is single-flight per tab and retries an eligible request once.
- Failed refresh/logout state clears in-memory auth and private/auth query cache.
- Redirects are constrained to same-origin internal paths.

## Purpose-separation matrix

| Source challenge | Phone Verify | Email Verify | Password Reset |
|---|---|---|---|
| Phone | PASS | rejected | rejected |
| Email | rejected | PASS | rejected |
| Password Reset | rejected | rejected | PASS |

The matrix uses distinct valid challenges for one synthetic owner and proves both off-diagonal rejection and diagonal success without exposing challenge values.

## Residual risks

- Stateless access JWTs remain usable until their approximately 15-minute expiry after session revocation.
- HTTP rate limiters and frontend refresh single-flight are process/tab local.
- Production SMS/email delivery, TLS, proxy policy, monitoring, managed secrets, and rotation require deployment work.
- Registration duplicate responses expose identifier existence (AUTH-5E-003).
- InnoDB may require a safe client retry under hostile same-account concurrency (AUTH-5E-004).
- Delayed external delivery may expose an already-cancelled code to its destination; server-side state keeps it unusable.

No unresolved Critical, High, or Medium threat was found after remediation.
