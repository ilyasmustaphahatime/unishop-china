# Postman and local API verification

`UniShop-China.postman_collection.json` contains scaffold folders, not a complete runnable
Phase 7 test collection. Earlier authentication collections in `documentation/postman/`
are historical examples. The current API is described by backend `/docs` and
[Phase 7 endpoint contracts](../documentation/phases/PHASE_7_SELLER_VERIFICATION.md).

For seller verification, authenticate first and send JSON `{"action":"start"}` to
`POST /api/v1/seller-verification`. Upload each required image; for HANDWRITTEN_CODE,
include the current challenge as a multipart field. Submit with `{"action":"submit"}`.
An expired draft can renew with `{"action":"renew_challenge"}` and must upload new handwritten proof.

Admin review requires a current DB ADMIN role. Review-reference path values are opaque
routing references, not internal DB IDs. Evidence access requires a grant from
`POST /api/v1/seller-verification/evidence/access`, then the same actor's bearer token and
`X-Evidence-Ticket` header on the returned fixed URL. Never put the ticket in a query string,
save it in a shared environment/export, or log it. The grant expires after 60 seconds and is one-use.

Prefer `backend/scripts/audit_security_http.py` for the complete synthetic lifecycle with
exact row/file cleanup and safe aggregate output. Never use real identity documents in development.
