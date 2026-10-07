# Profile API

Base URL: `/api/v1`

## Private and public fields

| Field | Own profile | Public profile | Client editable |
|---|:---:|:---:|:---:|
| public_handle | yes | yes | no |
| public_id (legacy internal UUID) | no | no | no |
| display_name | yes | yes | yes |
| bio | yes | yes | yes |
| city | yes | yes | yes |
| city_slug | yes | no | via the city request field only |
| city_active | yes | no | no |
| member_since | yes | yes | no |
| onboarding_completed | yes | no | no |
| email_verified | yes | yes | no |
| phone_verified | yes | yes | no |
| seller_verified | no (use seller-verification/me) | yes, boolean only | no |
| email / phone | no | no | no |
| user_id / internal ID | no | no | no |
| roles / account status | no | no | no |

## `GET /profile/me`

Requires an ACTIVE bearer-authenticated user. Lazily creates exactly one empty profile if necessary. Returns 200 with the own-profile schema, 401 for missing/invalid/inactive authentication, or a generic 500.

## `PATCH /profile/me`

Requires an ACTIVE bearer-authenticated user. The strict body accepts any subset of:

```json
{
  "display_name": "Lin Wei",
  "bio": "International student in Qingdao.",
  "city": "qingdao"
}
```

Phase 8: `city` in a write request is a canonical public slug from `GET /cities`,
not an English display label or internal ID. The server resolves an active database
city while holding its row lock until the profile transaction commits. Unknown or
inactive slugs, invalid syntax and privileged fields return a sanitized 422. Set
`city` to `null` to clear it (and invalidate onboarding completion). Omit it when
editing other fields without changing the saved city.

Own responses still return the display label in `city`, plus nullable `city_slug`
and boolean `city_active`. Public profile responses retain only the display label.
There is no client-side six-city allowlist; the six initial cities are migration
seed data, not application authority. A retired city remains visible on existing
profiles. Name/bio-only edits preserve it, but explicitly assigning an inactive
slug is rejected, including reassigning the same slug.

This is an intentional write-contract change from the Phase 6 label payload;
deploy the frontend and backend together. A valid update returns 200. Limits are
30 per authenticated user and 60 per connection peer per minute; 429 includes
`Retry-After`. See [catalog contracts and administration](catalog-api.md).

## `POST /profile/onboarding/complete`

Requires an ACTIVE bearer-authenticated user and exactly `{}`. First completion
requires the committed display name and an active referenced city. Previously
completed onboarding remains complete when an admin retires that city, and repeat
completion stays idempotent. Returns 200 when complete or already complete, 409
when required data or an active city for first completion is absent, 422 for extra
fields, and 429 when limited. Limits are 10 per user and 30 per peer per minute.

## `GET /profiles/by-handle/{handle}`

Phase 7 adds `seller_verified`, true only for a VERIFIED DB attempt with currently verified
phone/email. It is informational, never a listing permission. Other seller state/evidence is private.

Public read using the stable, server-generated `public_handle`. Only completed profiles belonging to ACTIVE accounts are visible. Unknown, incomplete, suspended, banned, and deleted profiles all return generic 404. The response is schema-minimized and never contains email, phone, internal user/profile ID, legacy public UUID, role, account status, auth/session/reset data, or secrets. Limit: 120 per connection peer per minute.

The canonical browser link is `/u/{handle}`. ASCII letters are lowercased; handles are 3-30 characters with alphanumeric ends and only alphanumeric/underscore/hyphen inside. Reserved names are rejected. Generated handles use `user-` plus 20 random hexadecimal characters. Invalid syntax returns sanitized 422; percent-encoded path variants are not a compatibility mechanism. No UUID or database-ID fallback exists. The old API and browser routes are removed without redirects. Clients cannot set or rename handles.

See [URL privacy policy](../security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md) for the exact reserved names, migration and authorization rules.

All profile text is untrusted plain text. Clients must render it as text and must not interpret it as HTML.
