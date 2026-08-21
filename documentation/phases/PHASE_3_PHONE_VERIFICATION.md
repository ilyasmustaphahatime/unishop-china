# Phase 3 — Phone Verification

## Current status

IMPLEMENTED_WITH_REAL_SMS_PENDING

## Objective

Provide secure mainland-China phone verification while keeping delivery provider-neutral and real Tencent SMS disabled until account approval.

## Endpoints

- `POST /api/v1/auth/phone/resend-code`
- `POST /api/v1/auth/phone/verify`

## Registration integration

Phone registration commits the user, BUYER role, and hashed code before making one sender call. Email-only registration never calls SMS. A delivery failure leaves the user registered and expires the exact unsent code.

## SMS abstraction

`SmsSender` returns a safe `SmsDeliveryResult`. Disabled, unavailable, fake, and Tencent implementations share that interface. Provider errors expose only a safe category and optional request ID.

## Fake SMS testing

Automated tests explicitly inject `FakeSmsSender`. It captures the normalized number and raw code only in test process memory, with no logging, database storage, HTTP response, or network access.

## Tencent adapter preparation

The adapter uses Tencent Cloud SDK 3.0, API version `v20210111`, `sms.tencentcloudapi.com`, configurable region and timeout, `SendSmsRequest`, one E.164 recipient, and one template parameter containing the code. It performs no automatic retries. The approved template must contain one code placeholder; expiry wording should remain fixed in the approved template.

## Tencent approval still required

Signature and template approval, an SDK App ID, and credentials are required before an explicitly authorized real test.

## Environment variable names

`SMS_ENABLED`, `SMS_PROVIDER`, `TENCENT_SECRET_ID`, `TENCENT_SECRET_KEY`, `TENCENT_SMS_SDK_APP_ID`, `TENCENT_SMS_SIGNATURE`, `TENCENT_SMS_TEMPLATE_ID`, `TENCENT_SMS_REGION`, `TENCENT_SMS_ENDPOINT`, and `SMS_REQUEST_TIMEOUT_SECONDS`.

## OTP generation and hashing

Codes contain exactly six ASCII digits, are generated with Python `secrets`, and are stored only as HMAC-SHA256 using the dedicated `VERIFICATION_CODE_HASH_SECRET`. Comparison is constant-time.

## Latest-code-only policy

Only the newest record ordered by `created_at DESC, id DESC` is accepted.

## Expiration policy

Codes expire after ten minutes and are invalid at `now >= expires_at`, using UTC.

## Attempt policy

Each wrong code atomically increments attempts. The fifth failure and later attempts return `VERIFICATION_ATTEMPTS_EXCEEDED`.

## Cooldown

One phone may request a new code only after 60 seconds. Cooldown responses include a safe `Retry-After` value.

## Rolling-hour limit

At most five code records may be created per phone in a rolling hour. The registration code counts.

## User-enumeration protection

Unknown and already-verified resend requests receive the same generic accepted response. Unknown-phone verification uses the generic invalid-code response.

## Provider failure behavior

Resend delivery failure expires the exact committed code and returns safe `SMS_PROVIDER_UNAVAILABLE` without raw SDK details. Registration remains HTTP 201. With `SMS_ENABLED=false`, resend returns the generic 202 response without a database write or sender call; registration creates then expires its undelivered record.

## Database behavior

The existing `users` and `phone_verification_codes` tables are reused. No table or migration was added. User/code verification updates are one transaction.

## Security decisions

No OTP, full phone number, password hash, HMAC, database URL, or Tencent credential is logged or returned. Production should additionally add IP/device controls and Redis or reverse-proxy rate limiting.

## Unit tests

17 focused Phase 3 unit tests passed.

## Integration tests

17 focused Phase 3 integration tests passed. Tests use the existing MySQL outer-transaction rollback fixture and leave no records.

## Real SMS status

Pending Tencent Signature and Template approval.
No real SMS was sent during Phase 3A.

## Postman

`documentation/postman/UniShop_Phase_3_Phone_Verification.postman_collection.json` includes ten requests. `testPhone` and `verificationCode` are intentionally empty; enter the received code manually only during a later approved real-SMS test.

## Completion checklist

- Phase 3 code: implemented
- Automated tests: passed
- Tencent integration: prepared
- Real SMS delivery: pending
- Phase 4A-4D status: subsequently completed; real Tencent SMS remains deferred
