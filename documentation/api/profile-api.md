# Profile API

Base URL: `/api/v1`

## Private and public fields

| Field | Own profile | Public profile | Client editable |
|---|:---:|:---:|:---:|
| public_id | yes | yes | no |
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

## `GET /profiles/{public_id}`

Public read using the random UUID `public_id`. Only completed profiles belonging to ACTIVE accounts are visible. Unknown, incomplete, suspended, banned, and deleted profiles all return generic 404. The response is schema-minimized and never contains email, phone, internal user ID, role, account status, auth/session/reset data, or secrets. Limit: 120 per connection peer per minute.

All profile text is untrusted plain text. Clients must render it as text and must not interpret it as HTML.
