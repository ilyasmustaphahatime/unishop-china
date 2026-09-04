# Phase 5E Security Findings

This register records confirmed findings from the final integrated authentication audit. Severity is project-specific; upstream dependency severity is noted separately. This is an engineering review, not a certification.

## AUTH-5E-001 — non-active accounts could complete phone verification

- Severity: MEDIUM
- Status: fixed in Phase 5E
- Component: `PhoneVerificationService`
- Preconditions: the attacker controls or obtains the newest valid phone challenge for a `SUSPENDED`, `BANNED`, or `DELETED` account.
- Impact: the endpoint could mutate `users.phone_verified` for an account that was not eligible for security-state changes. It did not reactivate the account, grant a role, issue a token, or permit login.
- Evidence: a rollback-only real-MySQL probe reproduced `phone_verified: false -> true` for a suspended account. The account-state regression now covers every actual non-active `AccountStatus`.
- Root cause: phone resend/verify checked existence and prior verification but did not enforce `AccountStatus.ACTIVE`.
- Remediation: require `ACTIVE` before sending or consuming a phone challenge. Resend remains enumeration-safe; verify returns the existing generic invalid-code response.
- Regression test: `test_inactive_accounts_cannot_resend_or_complete_phone_verification`.
- Migration: not required.

## AUTH-5E-002 — vulnerable development-only Browserslist version

- Severity: LOW for this project; upstream advisory severity: HIGH
- Status: fixed in Phase 5E
- Component: frontend build/development dependency graph
- Preconditions: an attacker must influence build-time Browserslist queries or custom statistics processed in a developer/CI environment.
- Impact: build-process crash, unbounded memory growth, or prototype mutation. `npm audit --omit=dev` confirmed that the production runtime dependency graph was unaffected.
- Evidence: `npm audit` reported GHSA-c83g-rgw3-j3cx and GHSA-73wf-gq98-2v4g through transitive `browserslist@4.28.6`.
- Root cause: the lockfile predated `browserslist@4.28.8`.
- Remediation: add the existing-style package override for exactly `browserslist@4.28.8` and refresh the lockfile.
- Regression evidence: both `npm audit` and `npm audit --omit=dev` report zero vulnerabilities; frontend tests, TypeScript, ESLint, and production build pass.
- Migration: not applicable.

## AUTH-5E-003 — registration conflict responses disclose account existence

- Severity: LOW
- Status: accepted residual; not changed in Phase 5E
- Component: `POST /api/v1/auth/register`
- Preconditions: an unauthenticated caller submits a candidate email address or phone number.
- Impact: the `201` versus `409` result and conflict code can reveal whether an identifier is already registered. This can support targeted phishing or privacy inference, but does not disclose credentials, roles, status, verification codes, or sessions.
- Evidence: the deliberate registration conflict contract returns `EMAIL_ALREADY_REGISTERED` or `PHONE_ALREADY_REGISTERED`; duplicate constraints enforce the same distinction.
- Root cause: the current product contract prioritizes actionable duplicate-registration feedback.
- Recommended remediation: if product requirements later prioritize identifier privacy, redesign registration as a uniform asynchronous/generic response and notify only the identifier owner. A message-only change would not remove the status/timing oracle.
- Phase 5E decision: accepted because a complete fix is an externally visible workflow/API change, not a minimal security patch; login and recovery remain generic.
- Regression test: existing registration conflict and rollback tests preserve the documented contract.

## AUTH-5E-004 — adversarial MySQL races may require request retry

- Severity: INFO
- Status: accepted operational behavior
- Component: password reset/change/logout-all versus refresh rotation
- Preconditions: two security mutations for the same account/family reach conflicting InnoDB row locks concurrently.
- Impact: InnoDB may choose one transaction as a deadlock victim. The victim receives a safe failure and must retry. No tested execution produced a partial password change, consumed-but-unapplied challenge, active descendant after a successful revocation operation, or cross-user mutation.
- Evidence: the Phase 5E real-MySQL suite repeatedly exercised reset-versus-refresh, change-versus-refresh, reset-versus-change, and logout-all-versus-refresh. Rollback and post-retry invariants passed.
- Root cause: intentionally strict row locking across user, challenge, and refresh-session records can create opposing lock acquisition under hostile concurrency.
- Recommended remediation: production observability should count deadlock/retry outcomes; clients may retry a failed operation. Do not add blind service retries without idempotency analysis.
- Phase 5E decision: not a vulnerability or closure blocker because failed transactions roll back and only successful responses establish the corresponding security guarantee.

## Finding totals

| Severity | Confirmed | Unresolved |
|---|---:|---:|
| Critical | 0 | 0 |
| High | 0 | 0 |
| Medium | 1 | 0 |
| Low | 2 | 1 accepted |
| Informational | 1 | 1 accepted |
