# Authentication API

The authentication surface closed through Phase 5E is mounted below `/api/v1/auth`:

- registration: `POST /register`;
- phone ownership: `POST /phone/resend-code`, `POST /phone/verify`;
- email ownership: `POST /email/resend-code`, `POST /email/verify`;
- sessions: `POST /login`, `POST /refresh`, `POST /logout`, `POST /logout-all`, `GET /me`;
- password recovery/change: `POST /password/forgot`, `POST /password/reset`, `POST /password/change`.

Email resend accepts only an empty JSON object and requires a valid Bearer access token. Email verify accepts only a six-ASCII-digit `code` and derives the account exclusively from that token. Both use exact Origin validation, safe no-store responses, process-local peer/user HTTP limits, and database-backed challenge controls. Full contracts and security behavior are documented in `documentation/phases/PHASE_5D_SECURE_EMAIL_VERIFICATION.md`.

Phone resend and verification accept only a normalized Mainland China phone number and, for verification, a strict six-ASCII-digit code. Unknown, already verified, and non-`ACTIVE` resend requests retain the generic accepted contract. Non-`ACTIVE` accounts cannot receive or consume a phone challenge; verification returns the existing generic invalid-code response without mutating account state.

Development fake-delivery routes are separate, explicitly gated, and never part of production OpenAPI.
