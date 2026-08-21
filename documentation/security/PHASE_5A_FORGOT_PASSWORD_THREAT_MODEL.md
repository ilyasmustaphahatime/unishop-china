# Phase 5A Forgot-Password Threat Model

Review date: 2026-08-21

Scope: reset-request normalization, enumeration resistance, challenge generation/storage, abuse controls, provider boundary, development fake delivery, transaction behavior, configuration, and Phase 5B preparation.

This is a targeted engineering threat model against relevant OWASP API Security Top 10 2023 and OWASP ASVS 5.0 control areas. It is not a penetration test, external assessment, or certification.

| Threat | Attack path | Control | Test evidence | Residual risk |
|---|---|---|---|---|
| Account enumeration | Compare status/body/fields for known, unknown, or inactive identifiers | One exact 202 body; no destination, ID, eligibility, expiry, or provider fields; dummy generation/hash/database workload | Existing, unknown email/phone, inactive-state, and service-failure route tests compare the public contract | Database cache, provider, contention, and network behavior can still create timing differences |
| Reset spam | Repeatedly request challenges for one account | 60-second database cooldown, five stored challenges per rolling hour, identifier limiter | Cooldown, hourly cap, and identifier limiter integration tests | Distributed attackers can cross process-local limiter boundaries |
| SMS/email harassment | Trigger repeated provider delivery to a victim | Normalized identifier HMAC limit, account cooldown/hour cap, provider disabled by default | Delivery-count assertions prove limited/suppressed calls do not reach provider | A valid low-rate attacker may still cause nuisance; real provider controls are pending |
| OTP brute force | Guess a six-digit code during Phase 5B | Short ten-minute expiry, HMAC storage, newest-only/single-use metadata prepared; reset verification not exposed in Phase 5A | Expiry/hash/newest-only tests; OpenAPI asserts no reset endpoint | Attempt enforcement is mandatory in Phase 5B and does not yet exist in schema |
| Predictable reset code | Infer code from time, row ID, or weak PRNG | Existing secure generator uses `secrets.randbelow`; exactly six ASCII digits | Generator/helper unit tests and source review | Six digits provide limited entropy and depend on Phase 5B online controls |
| Reset-code database theft | Read `password_reset_codes` | Only domain-separated HMAC-SHA256 is stored; secret remains outside DB | Integration test verifies raw code differs from DB and validates only through helper | Offline guessing is possible if the HMAC secret is also compromised |
| Cross-purpose hash substitution | Reuse phone-verification hash as reset hash | Password-reset HMAC includes a dedicated domain prefix | Unit test proves phone and reset hashes differ for the same code/secret | Secret lifecycle is shared; a separate managed reset key may be chosen later |
| Reset-code logging | Capture raw code/hash in logs, stdout, or exceptions | New runtime flow has no logging/printing; generic exception containment | Fake-provider no-output/network test and source/Ruff review | Future provider telemetry must maintain strict redaction |
| Provider failure leakage | Force delivery exception and compare API result | Exceptions and unconfirmed results return the same generic 202; provider detail is discarded | Raise/unconfirmed/route-failure tests | Operational diagnosis needs future safe event metrics |
| Provider failure inconsistency | Delivery fails after database commit | New row starts inactive and activates only after confirmed delivery | Provider and activation failure tests assert no usable undelivered row | Previous code is already invalidated, creating temporary availability loss |
| Rate-limit bypass | Rotate identifiers/peers or exploit unbounded keys | Peer plus normalized-identifier HMAC limits; bounded expiring maps; database account limits | IP, identifier, key, cooldown, and hour tests | Multi-replica/distributed bypass remains until shared storage is approved |
| Forwarded-header spoofing | Claim a trusted or new IP in `X-Forwarded-For` | Application uses the actual TestClient/socket peer | Forged-header limiter and local-inbox tests | A reverse proxy deployment needs an explicit trusted-proxy design |
| Replay of older codes | Use Code A after Code B is issued | Prior active rows are marked used; activation re-locks user and confirms row is still latest | Replacement and delayed-delivery race tests | Phase 5B must repeat newest, expiry, and `used_at` checks atomically |
| Multiple active codes | Race two requests or delay first delivery | User row locks serialize issuance; exact latest-row check precedes activation | Cooldown/replacement and delayed-delivery interleaving tests | Cross-system provider delays still affect availability, not validity, under current design |
| User-targeted denial of service | Invalidate a victim's valid code, then cause delivery failure | Limits reduce frequency; failed new challenge remains inactive and public response stays generic | Provider failure and cooldown/hour tests | Safe newest-only policy intentionally favors confidentiality/integrity over uninterrupted recovery availability |
| Fake provider exposure | Enable fake inbox in production or access it remotely | Startup guards, development-only route inclusion, actual-loopback check, identifier-scoped HMAC lookup, bounded expiry/consume | Production configuration and OpenAPI tests; forged forwarding rejection | A compromised local development machine can read local test challenges |
| Production misconfiguration | Use fake delivery, weak/missing HMAC key, or exposed inbox | Fail-closed startup validation; fake route omitted outside development | Parameterized unsafe-production tests | External secret manager, TLS, monitoring, and deployment policy remain prerequisites |
| Secret leakage | Commit or return HMAC/JWT/provider/database secrets | `.env` remains ignored, example uses placeholders, `SecretStr` settings, no public secret fields | Git diff/config review, response tests, prior Phase 4D secret audit | Operational secret custody and rotation are outside this repository phase |
| Mass assignment and identifier confusion | Submit `user_id`, status, admin flags, code, password, Unicode, or oversized data | Strict extra-forbid schema, one bounded identifier, shared email/phone validation | Invalid/privileged/oversized/cross-origin negative tests | Unicode handling follows current email validator policy and should be reassessed if internationalized email is added |
| Unsafe provider/API consumption | Inject provider errors or configure an unapproved external sender | Provider-neutral protocol, delivered-status check, no real integration, disabled default | Provider contract and production-builder tests | Real Tencent/email timeout, certificate, retry, and response policy must be reviewed when approved |

## Security invariants for Phase 5B

1. No password may change from possession of an identifier alone.
2. Verification must select the newest row for the server-resolved user and reject pending, used, expired, or superseded rows.
3. HMAC comparison must remain constant-time and use the password-reset domain.
4. Failed guesses must have an atomic, bounded server-side attempt policy before verification is exposed.
5. Successful consumption and password replacement must be atomic; replay must fail.
6. Session revocation behavior must be explicitly approved and tested; Phase 5A deliberately does not revoke anything.
7. Every public failure must preserve enumeration safety and omit provider/database detail.

## OWASP disposition

- API2 Broken Authentication: addressed for request/generation scope; actual reset authentication remains Phase 5B.
- API4 Unrestricted Resource Consumption: addressed with bounded multi-layer limits; distributed enforcement remains residual.
- API6 Unrestricted Access to Sensitive Business Flows: addressed with cooldown/hourly/peer/identifier controls; harassment cannot be eliminated entirely.
- API8 Security Misconfiguration: fake-provider, inbox, secret, and production-route guards are tested.
- API10 Unsafe Consumption of APIs: no real third-party integration exists; provider errors are contained and delivery must be confirmed.
- ASVS 5.0 recovery, validation, cryptography, error, rate-limit, logging, and session-safety areas were reviewed for this phase. Certification is not claimed.

