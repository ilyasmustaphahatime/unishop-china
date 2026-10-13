# Product workflow through Phase 10

An ACTIVE user with completed onboarding, verified email/phone and current seller
approval creates a DRAFT using active Phase 8 catalog slugs. Plain text and CNY
Decimal fields are validated by the backend. The owner can add 0-8 sanitized
static images; publishing without images remains valid. Image position 0 is cover.

```text
DRAFT -> PUBLISHED -> PAUSED -> PUBLISHED
  |           |          |
  +-----------+----------+-> ARCHIVED (terminal)
```

Eligible owners edit/upload/reorder in non-archived states. ACTIVE owners retain
read, pause, archive and image deletion after losing approval/onboarding, so they
can withdraw/clean up personal photos. Archived listings permit private image
list/read/delete, never upload/reorder or republish. Inactive identities cannot
perform owner operations. Approval is not derived from BUYER/SELLER JWT roles.

Public detail and public image bytes require the same current seller/onboarding,
PUBLISHED and active-catalog predicate. Hidden listings/images return generic
404. Deleting cover resequences and promotes the next image; the old opaque ref
never becomes a different image. Owner previews use authenticated Blob URLs;
logout, account switch and unmount revoke them. No URL tokens or storage keys.

Upload saves sanitized bytes once, then reacquires/rechecks authority/parent/quota
before metadata commit; failures compensate storage. Delete removes metadata
transactionally before physical cleanup. Operational failure leaves an invisible
orphan, detected by report-only media audit; never restores public visibility.

No feed/search, chat, deals, reviews, orders or payments were implemented.
See [listing API](../api/product-api.md), [image API](../api/product-images-api.md)
and [Phase 10 gate](../phases/PHASE_10_PRODUCT_IMAGES_STORAGE.md).
