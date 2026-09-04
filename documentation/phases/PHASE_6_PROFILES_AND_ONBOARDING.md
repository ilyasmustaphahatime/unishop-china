# Phase 6 Profiles and Onboarding

## Decision

- Phase 6 complete: YES
- Ready for Phase 7: YES
- Migration required: YES, one additive migration
- Authentication architecture changed: NO
- Unresolved Critical/High/Medium findings: 0/0/0

This is an engineering verification record, not a compliance certification.

## 6A — Profile foundation

Migration `f6a1b2c3d4e5` adds `user_profiles` after `d5f0c1e2a3b4`. Authentication data remains in `users` and the existing auth/security tables. Marketplace-facing data is one-to-one with a user and contains:

- UUID primary key;
- immutable, unique UUID `public_id` for URLs;
- unique foreign key `user_id -> users.id` with delete cascade;
- nullable `display_name`, `bio`, and `city` while onboarding is incomplete;
- server-controlled `onboarding_completed`;
- creation/update timestamps.

Database checks bound display names to 2–50 trimmed characters when present, bios to 300 characters, and cities to the six supported Phase 6 values. Application validation additionally performs Unicode NFC normalization, trimming, strict extra-field rejection, and control/direction-character rejection.

Profiles are created lazily so the closed registration flow is untouched. A locked user row serializes first creation; unique `user_id` and `public_id` constraints provide database backstops.

## 6B — Onboarding rules

The server is the source of truth. Onboarding requires a valid display name and one supported city. The client cannot submit `onboarding_completed`; completion uses a strict empty object and derives the account from the bearer principal. Completion is idempotent. A later update that clears a required field automatically clears completion.

All own-profile reads and mutations require the existing ACTIVE-only authentication dependency. Public lookup returns only ACTIVE, completed profiles and otherwise uses the same generic 404 response.

## 6C — Design system and shell

The frontend now has reusable accessible buttons, inputs, textarea, select, card, badge, generated avatar, form field, alert, empty state, spinner, and step progress components. The authenticated shell is responsive, uses the red/white UniShop identity, and exposes only working Phase 6 profile navigation plus existing logout controls.

Scaffolded seller, product, messages, and admin pages remain untouched on disk for later phases but are not registered as functional application routes.

## 6D — Frontend profile experience

Routes:

- `/onboarding` — refresh-safe, server-backed five-step onboarding;
- `/profile` — own profile, verification indicators, member date, and empty-bio state;
- `/profile/edit` — aligned validation and safe API errors;
- `/users/:publicId` — safe public profile.

TanStack Query keys include the authenticated user ID. Private queries carry private metadata and are removed by the existing logout/session-clear boundary. Access tokens remain memory-only; refresh remains in the HttpOnly cookie architecture.

## 6E — Integration and closure evidence

- Backend full regression: 597 passed, one third-party Starlette deprecation warning.
- Frontend full regression: 68 passed.
- Python compile/import/OpenAPI, Ruff, TypeScript, ESLint, and production build: pass.
- `pip check`, `pip-audit`, `npm audit`, and `npm audit --omit=dev`: pass.
- Real MySQL migration upgrade, downgrade to `d5f0c1e2a3b4`, upgrade to `f6a1b2c3d4e5`, one-head check, and drift check: pass.
- Five consecutive real-MySQL concurrency runs: pass.
- Fresh real HTTP/MySQL lifecycle through profile creation, onboarding, safe public read, edit, logout, and refresh rejection: pass with exact synthetic cleanup.
- Fresh in-app browser automation: environment blocked before a browser tab could be created; no result was fabricated.

## Transaction semantics

Profile mutation locks the authoritative user row before reading or creating the profile. First creation, updates, onboarding completion, and update-versus-completion races therefore use one lock order. Concurrent updates are serialized with documented last-committer state. In adversarial InnoDB conditions a transaction may still be selected as a deadlock victim; rollback remains atomic and the failed caller must retry.

A controlled repository failure after in-memory mutation proves rollback leaves the committed profile unchanged.

## Rate limits

- profile PATCH: 30/user/minute and 60/peer/minute;
- onboarding completion: 10/user/minute and 30/peer/minute;
- public profile GET: 120/peer/minute;
- all key maps are bounded to 10,000 entries.

Forwarded headers are ignored. These limiters are intentionally process-local and require shared production storage for horizontal deployment.

## Phase boundary

Phase 6 does not implement seller verification, KYC, document/selfie/WeChat checks, products, image upload, search, chat, deals, reviews, notifications, or admin functionality. The next approved boundary is Phase 7.
