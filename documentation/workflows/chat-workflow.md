# chat workflow

1. Authenticate using the existing login/access-token flow.
2. POST a public product slug to `/api/v1/chat/conversations`. The server derives
   the seller and checks canonical public eligibility; concurrent retries reuse
   one database-protected conversation identity.
3. Connect to `/api/v1/chat/ws` with an allowed Origin, no token URL, and send the
   authentication event within five seconds. Subscribe to the owned conversation.
4. Send a plain-text message with a fresh canonical UUID client message ID. The
   server checks current accounts/membership and rate limits, locks rows in stable
   order, inserts or resolves an idempotent retry, and commits before returning.
5. Receive the creation ACK and optional subscribed event. Lost ACK: retry the
   same client ID and content, never generate a new ID for the same attempted send.
6. Reconnect after expiry/network failure and recover from bounded HTTP history.
   Use message references for deduplication; real-time events are best effort.

Active participants retain history for paused/archived products or an inactive
counterparty. New messages require both accounts active, but an existing conversation
does not require the product to remain public. New conversations do require public
eligibility. Physical user/product deletion is restricted while history references
them; no chat delete endpoint or retention cleanup is introduced.

The connection manager is single-process and bounded, not a message store. No session
is shared across concurrent tasks: each synchronous WebSocket database operation gets
a fresh session inside a worker thread. Outbound queues recheck authorization before
bytes. Server shutdown cancels and closes tracked connections.

See [API/events](../api/chat-api.md), [architecture](../architecture/ADR_PHASE_13_PRIVATE_CHAT.md)
and [implementation evidence](../phases/PHASE_13_SECURE_CHAT.md). This phase adds no
frontend messaging screens, attachments, read receipts, typing indicators or Phase 14.
