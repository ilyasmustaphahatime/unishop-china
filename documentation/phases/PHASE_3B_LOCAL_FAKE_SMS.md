# Phase 3B — Local Fake SMS Verification

## Purpose

Phase 3B provides a local manual workflow for exercising the existing Phase 3A phone-verification logic while Tencent credentials and approvals are unavailable. It reuses the existing registration, resend, and verification services.

## Security warning

Development-only. Never enable this feature in staging or production. The inbox intentionally exposes a raw OTP to a developer and is not production-ready.

## Local workflow

1. Start FastAPI with development mode, the fake provider, and the fake inbox explicitly enabled.
2. Start Vite with the development page flag enabled.
3. Open `/dev/phone-verification`.
4. Enter a dedicated test mainland-China phone number and a strong password.
5. Register and wait approximately three seconds.
6. Copy or manually type the locally displayed code.
7. Verify the phone and confirm `phone_verified=true`.
8. Use the resend action after the existing cooldown when testing code replacement.

Only dedicated test data should be used. Never put a real phone number in tracked configuration or documentation.

## Configuration variable names

Backend:

- `APP_ENV`
- `SMS_ENABLED`
- `SMS_PROVIDER`
- `ENABLE_FAKE_SMS_DEV_INBOX`
- `FAKE_SMS_DELIVERY_DELAY_SECONDS`
- `FAKE_SMS_INBOX_TTL_SECONDS`
- `FAKE_SMS_INBOX_MAX_MESSAGES`
- `FAKE_SMS_LOCALHOST_ONLY`

Frontend:

- `VITE_API_BASE_URL`
- `VITE_ENABLE_FAKE_SMS_DEV_PAGE`

Tracked example files contain safe defaults and placeholders only.

## Backend fake inbox

`GET /api/v1/dev/fake-sms/latest?phone_number=...` returns only the newest delivered, unexpired message for the normalized lookup phone. The response masks the phone and has `Cache-Control: no-store` and `Pragma: no-cache`.

`DELETE /api/v1/dev/fake-sms/{message_id}` removes one local message. Successful backend verification also consumes the matching message after the database transaction commits.

Both routes are registered only when the backend is in development and the inbox flag is explicitly enabled.

## Frontend development page

The page is `/dev/phone-verification`. It is added to the router only when Vite is in development mode and `VITE_ENABLE_FAKE_SMS_DEV_PAGE=true`.

The page validates input for user experience, prevents duplicate pending requests, polls once per second for at most 20 seconds, cancels stale requests, and never automatically submits a received code. Password and OTP values remain only in component state and are cleared at the required points.

## Simulated delivery delay

The default delay is three seconds. A message is not returned before `available_at`. The default expiry is 600 seconds, and the inbox retains no more than 100 current messages.

## OTP storage behavior

- MySQL stores only the existing HMAC value.
- The raw OTP exists only inside process memory and the local page's live component state.
- The raw OTP is not written to disk or normal API responses.
- The in-memory inbox is cleared whenever the backend restarts.
- Expired, superseded, and successfully consumed messages are removed.

## Production startup guards

Startup refuses unsafe configuration when:

- `SMS_PROVIDER=fake` outside development.
- `ENABLE_FAKE_SMS_DEV_INBOX=true` outside development.
- The inbox is enabled without mandatory localhost-only mode.

Safe errors name only the unsafe variable names. Production and staging do not register or document the inbox routes.

## Localhost restrictions

The API checks the actual connection peer and permits IPv4 or IPv6 loopback only. It does not trust `X-Forwarded-For`. Development CORS is limited to the configured frontend and the expected localhost Vite origins.

## Security controls

- Thread-safe process-memory store.
- Cryptographically opaque message identifiers.
- Per-phone lookup isolation.
- Old-message superseding.
- Expiry and successful-verification cleanup.
- No Tencent call and no external network in fake sender.
- No raw OTP logs or database persistence.
- No browser storage, console logging, or unsafe HTML.
- Disabled-by-default backend and frontend flags.
- Fail-closed production/staging startup validation.

See [the Phase 3B threat model](../security/PHASE_3B_FAKE_SMS_THREAT_MODEL.md).

## Automated tests

- Backend: 146 collected, 146 passed, 0 failed, 0 skipped, 1 third-party warning.
- Frontend: 12 collected, 12 passed, 0 failed, 0 skipped.
- Frontend type check, lint, and production build pass.
- MySQL check, Alembic current/head, and schema-drift check pass at `a75289cfd4a9`.

## Manual test result

A full localhost API smoke flow passed with dedicated generated test data:

- Registration returned HTTP 201 without an OTP.
- The message was unavailable before the delay and available afterward.
- Wrong-code verification failed and retained the message.
- Duplicate, invalid-phone, and weak-password cases were rejected.
- The resend cooldown was enforced.
- Resend produced a delayed replacement; the old code failed and the new code succeeded.
- Verification set `phone_verified=true` and `verified_at`, then consumed the message.
- MySQL contained only HMAC values.
- Exact test-account cleanup restored counts to users 1, roles 1, codes 0, refresh tokens 0, reset codes 0, with zero orphans.

The in-app browser integration was unavailable because the host did not supply its required sandbox metadata. React behavior is covered by 12 passing jsdom tests and a passing production build, but a live human-style browser entry remains to be performed before declaring Phase 3B fully complete.

## Known limitation

No real SMS reaches a physical phone. The inbox is process-local and is lost on restart. A privileged malicious local process can inspect local process or browser memory.

## Tencent status

Real Tencent SMS remains pending. No Tencent call and no real SMS occurred during Phase 3B.

## Disable instructions

Set `ENABLE_FAKE_SMS_DEV_INBOX=false`, set `SMS_PROVIDER` back to the intended non-fake provider, and set `VITE_ENABLE_FAKE_SMS_DEV_PAGE=false`. Restart both processes. Confirm `/api/v1/dev/fake-sms/latest` and `/dev/phone-verification` are absent.
