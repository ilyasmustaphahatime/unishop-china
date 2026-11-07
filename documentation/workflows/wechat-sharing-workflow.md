# wechat sharing workflow

```text
NONE -- buyer request --> PENDING -- seller approve(contact) --> APPROVED
                           |                                     |
                           +-- seller deny --> DENIED            |
                           +-- seller revoke --------------------+--> REVOKED
```

There is one consent state per product conversation. Only its buyer requests, only
its seller approves/denies/revokes. Pending/approved request retries preserve current
state; denied/revoked requests return 409 and cannot reopen. Repeated same approval,
denial or revocation is idempotent. A different contact cannot replace an already
approved value through a retry. Approve without a pending request is rejected.

Both accounts must be active for requests, approvals and contact reads. The seller
may revoke even when the buyer is inactive. Row locks serialize concurrent request,
approval and revocation. If revoke wins, a later approval cannot re-enable access;
if approval wins first, revoke clears the ciphertext. Revocation protects subsequent
reads, not previously copied contacts or a response already authorized in flight.

Only GET `/api/v1/chat/conversations/{conversation_ref}/wechat` can return an approved
contact, and only to current participants. Mutation responses contain status/times
and `contact: null`. General socket events, conversation summaries, public profiles
and products never project stored WeChat contacts. No seller-document extraction,
image processing, external WeChat API or payment integration is involved.

Contact IDs are validated and stored with AES-GCM authenticated encryption bound to
the conversation. Missing/wrong keys or invalid ciphertext fail closed with a generic
503. Denial/revocation leaves no stored contact ciphertext. Responses are non-cacheable;
do not log private payloads. See [key provisioning/rotation and limitations](../architecture/ADR_PHASE_13_PRIVATE_CHAT.md)
and [HTTP contract](../api/chat-api.md).
