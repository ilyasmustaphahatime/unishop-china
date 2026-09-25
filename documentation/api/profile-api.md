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
| member_since | yes | yes | no |
| onboarding_completed | yes | no | no |
| email_verified | yes | yes | no |
| phone_verified | yes | yes | no |
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
  "city": "Qingdao"
}
```

Supported cities are Qingdao, Beijing, Shanghai, Shenzhen, Guangzhou, and Hangzhou. Unknown or privileged fields return a sanitized 422. A valid update returns 200. Limits are 30 per authenticated user and 60 per connection peer per minute; 429 includes `Retry-After`.

## `POST /profile/onboarding/complete`

Requires an ACTIVE bearer-authenticated user and exactly `{}`. The server checks the committed display name and city. It returns 200 when complete or already complete, 409 when required data is absent, 422 for extra fields, and 429 when limited. Limits are 10 per user and 30 per peer per minute.

## `GET /profiles/by-handle/{handle}`

Public read using the stable, server-generated `public_handle`. Only completed profiles belonging to ACTIVE accounts are visible. Unknown, incomplete, suspended, banned, and deleted profiles all return generic 404. The response is schema-minimized and never contains email, phone, internal user/profile ID, legacy public UUID, role, account status, auth/session/reset data, or secrets. Limit: 120 per connection peer per minute.

The canonical browser link is `/u/{handle}`. ASCII letters are lowercased; handles are 3-30 characters with alphanumeric ends and only alphanumeric/underscore/hyphen inside. Reserved names are rejected. Generated handles use `user-` plus 20 random hexadecimal characters. Invalid syntax returns sanitized 422; percent-encoded path variants are not a compatibility mechanism. No UUID or database-ID fallback exists. The old API and browser routes are removed without redirects. Clients cannot set or rename handles.

See [URL privacy policy](../security/URL_PRIVACY_AND_PUBLIC_IDENTIFIERS.md) for the exact reserved names, migration and authorization rules.

All profile text is untrusted plain text. Clients must render it as text and must not interpret it as HTML.
