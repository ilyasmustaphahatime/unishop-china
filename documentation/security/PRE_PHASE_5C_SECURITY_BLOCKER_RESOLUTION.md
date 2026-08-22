# Pre-Phase 5C Security Blocker Resolution

Date: 2026-08-22

Scope: only the two blockers verified by the Pre-Phase 5C readiness audit. No Phase 5C route, email-verification feature, database model, schema migration, or authentication business rule was added.

## Validation-response exposure

### Original finding

FastAPI's default `RequestValidationError` response included Pydantic `input` and sometimes `ctx`. Synthetic registration, login, forgot/reset-password, phone-verification, unexpected-field, and nested-malformed requests demonstrated that submitted passwords, codes, identifiers, and token-like values could be reflected in HTTP 422 bodies.

### Risk

Although the caller supplied the value, returning it unnecessarily could place credentials or recovery material into browser, proxy, observability, or error-capture logs. Removing only top-level input was insufficient because nested input and exception context could also retain submitted material.

### Remediation

The application now registers one global `RequestValidationError` handler. It constructs a new allow-listed response instead of filtering and reusing the original error dictionaries. Every error contains only:

- a sanitized stable error type;
- sanitized field-location segments;
- a fixed non-reflective message.

The handler never serializes `input`, `ctx`, Pydantic URLs, exception objects, raw validator messages, request bodies, headers, cookies, or authorization material. Missing-field responses still identify the affected field.

### Evidence

Focused tests cover weak registration and reset passwords, oversized login passwords, malformed reset and phone-verification codes, invalid forgot-password identifiers, extra token/secret fields, nested malformed content, safe required-field metadata, recursive key/value scans, and absence from captured logs. A post-fix runtime probe reported `input_echoed=false` for every tested surface.

## Docker build-context exposure

### Original finding

The backend build context is `./backend`, the Dockerfile uses `COPY . .`, a real ignored `backend/.env` exists locally, and no backend `.dockerignore` existed. Git ignore rules do not prevent Docker from sending or copying files into build layers.

### Risk

A backend image build could embed local database, JWT, HMAC, or provider credentials in an image layer.

### Remediation

`backend/.dockerignore` now excludes `.env`, `.env.*`, environments, bytecode, caches, coverage, tests, logs, repository metadata, private/runtime uploads, and common editor artifacts. `.env.example` is intentionally re-included because it contains placeholders only. Runtime configuration continues to come from environment injection.

The Dockerfile contains no direct `.env` `COPY`/`ADD` or hardcoded secret `ENV`. Compose uses the guarded `./backend` context and environment substitution for database configuration. Docker CLI was unavailable, so deterministic project tests validate these policies without weakening the gate.

## Regression evidence

- New blocker tests: 16 passed.
- Phase 5A: 45 passed.
- Phase 5B: 57 passed.
- Full backend: 401 passed, zero failed, one third-party TestClient deprecation warning.
- Frontend: 49 passed; TypeScript, lint, production build, and both npm audits passed.
- MySQL table counts and relationship integrity remained unchanged.
- Alembic current/head remained `aca2dda0ef53` with no drift and no migration.
- Local pip was upgraded from 26.1.2 to 26.2.1; `pip check` and `pip-audit` passed.

## Residual risks

- Endpoint rate limiters remain process-local.
- Issued stateless access JWTs remain valid until their short expiration.
- Structured authentication/security logging remains future operational work.
- Phone verification retains some differentiated state responses.
- Production TLS, CSP, monitoring, managed secret rotation, and shared rate limiting remain deployment work.
- Marketplace object/function authorization remains future work because those APIs are not active.

## Phase 5C boundary

The blockers are resolved, but Phase 5C remains not started. No email-verification route, schema, model, provider, repository, service, frontend behavior, or migration was introduced by this remediation.
