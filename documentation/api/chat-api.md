# chat api

## Scope and authentication

Phase 13 backend only. HTTP OpenAPI is authoritative for request/response shapes;
WebSocket events are documented here. Every HTTP operation below uses an existing
access JWT in `Authorization: Bearer ...`, not refresh cookies or a token query
parameter. Only active participants can access their private conversation. Unknown
and another user's conversation both return 404. HTTP browser Origins, when present,
must match configured frontend origins. WebSockets require exactly one allowed Origin.

HTTP responses, including errors, use `Cache-Control: no-store`, `Pragma: no-cache`
and `Referrer-Policy: no-referrer`. Do not log headers, bodies, tokens or contacts.

## HTTP operations

Base: `/api/v1/chat/conversations`. All successful operations return 200.

| Method | Suffix | Input | Response |
| --- | --- | --- | --- |
| POST | empty | `{ "product_slug": "item-<24 lowercase hex>" }` | Created or reused conversation |
| GET | empty | `limit=20` (1–50), optional `cursor` | Private conversation page |
| GET | `/{conversation_ref}` | No query/body | Conversation details |
| GET | `/{conversation_ref}/messages` | `limit=20` (1–50), optional `cursor` | Durable message page |
| POST | `/{conversation_ref}/wechat/request` | Empty body; buyer only | Handoff status, no contact |
| POST | `/{conversation_ref}/wechat/approve` | `{ "contact": "Synthetic_123" }`; seller only | Handoff status, no contact |
| POST | `/{conversation_ref}/wechat/deny` | Empty body; seller only | Handoff status, no contact |
| POST | `/{conversation_ref}/wechat/revoke` | Empty body; seller only | Handoff status, no contact |
| GET | `/{conversation_ref}/wechat` | No query/body | Private status; contact only when approved |

Only create/approve accept JSON. Use `Content-Type: application/json`; maximum body
1,024 actual bytes. Unknown/duplicate fields, duplicate query keys, noncanonical
limits and unsupported ownership/state inputs are rejected. A `cv-` followed by 32
lowercase hex digits is the opaque conversation reference, never an internal UUID.
There is deliberately no duplicate HTTP message-send endpoint; use the WebSocket
command and HTTP history recovery.

Conversation projection: `conversation_ref`, `product_slug`, `role` (buyer's/seller's
role relative to the current caller), `created_at`, `activity_at`. No user PKs,
emails, phones, ciphertext, contact or evidence/storage identifiers are included.

Message projection: `message_ref`, `conversation_ref`, `sender_role`,
`client_message_id`, `content`, `created_at`. `sender_role` is `buyer` or `seller`,
not a client-provided user ID. Timestamps are server UTC. Content is plain text;
render through escaped text nodes, never `innerHTML`.

Pages: `{ "items": [...], "next_cursor": null | "opaque signed value" }`, newest
first. Cursors are at most 512 characters and bind user, purpose, conversation and
page size. Keep the same `limit` when following a cursor. Message timestamp ties
are ordered by opaque message reference. On reconnect, fetch the first message
page and continue until the last known message, deduplicating by `message_ref`.
Conversation lists are live activity keysets, not a frozen snapshot: refresh the
first page to see conversations which gained new activity during pagination.

Handoff projection: `status` (`NONE`, `PENDING`, `APPROVED`, `DENIED`, `REVOKED`),
`requested_at`, `decided_at`, `revoked_at`, `contact`. Contact is null on mutations
and in all states except an authorized GET of APPROVED. Denied/revoked requests
cannot reopen. See [consent workflow](../workflows/wechat-sharing-workflow.md).

## Safe error contract

Ordinary errors: `{ "detail": "safe fixed message" }`. Schema validation may return
`{ "detail": [{ "type": "...", "loc": ["body", "field"], "msg": "Invalid value." }] }`.
Input values and backend exception details are never echoed. OpenAPI records these
models and the relevant error statuses for all nine new operations.

| Status | Meaning |
| --- | --- |
| 400 | Invalid/tampered/cross-scope cursor |
| 401 | Missing/invalid access JWT or inactive actor |
| 403 | Role, Origin or buyer eligibility denied |
| 404 | Product unavailable for creation or conversation not owned/found |
| 408 | Body input deadline exceeded |
| 409 | Invalid consent transition, self-conversation or unavailable counterparty |
| 413 / 415 | Actual input size exceeded / wrong body media type |
| 422 | Strict schema, duplicate/unknown input or bodyless-operation violation |
| 429 | Peer/account budget; `Retry-After` header supplied |
| 500 / 503 | Safe unexpected failure / persistence or required secret unavailable |

Pre-parser limits may reject malformed/oversized requests before authentication.
Clients must not assume every unauthenticated malformed request produces 401.

## WebSocket protocol v1

Endpoint: `/api/v1/chat/ws`. Use WSS outside local development. No query string,
subprotocol credentials, Authorization header or token-in-URL is accepted. Browser
authentication is the first JSON text event, within five seconds. Cookies alone do
not authenticate the socket. Version must be integer `1`, not a boolean/string.
Unknown types, extra fields, duplicate JSON keys and binary events are rejected.

```json
{"v":1,"type":"authenticate","access_token":"<access JWT from login, never a URL>"}
```

Server: `{"v":1,"type":"authenticated"}`. Do not retain the JWT in UI logs.

```json
{"v":1,"type":"subscribe","conversation_ref":"cv-<32 lowercase hex>"}
```

Server: `{"v":1,"type":"subscribed","conversation_ref":"..."}`. Subscription
requires current membership and does not grant a permanent authorization lease.

```json
{"v":1,"type":"message.send","conversation_ref":"cv-<32 lowercase hex>","client_message_id":"<canonical lowercase UUID>","content":"Hello, is this available?"}
```

Server ACK: `{"v":1,"type":"message.ack","message":{...},"created":true}`.
After the commit, authorized subscribers may receive
`{"v":1,"type":"message.created","message":{...}}`. The sending device receives
both if subscribed. Retry the **same** client ID/content after a lost ACK: the ACK
returns `created=false` and the original message; no second event is broadcast.
Reusing that sender/conversation/client ID with different content returns a conflict.

Message content supports international Unicode, max 2,000 characters / 8,000 UTF-8
bytes. Meaningless whitespace/format-only strings, unsafe controls and bidi format
controls are rejected. Tab/newline and Unicode joining characters are supported.

Keepalive: `{"v":1,"type":"ping"}` → `{"v":1,"type":"pong"}`. Ping rechecks account
state; it does not extend token lifetime. Reconnect with a fresh access JWT when
expired. Re-authentication on an existing socket is not supported.

Recoverable errors: `{"v":1,"type":"error","code":"not_found"}`. Codes include
`invalid_request`, `forbidden`, `not_found`, `conflict`, `rate_limited`, `unavailable`.
No error includes private payloads. Closure uses the native close frame and an empty
reason, not an arbitrary exception string: 4401 authentication/expiry, 1008
protocol/policy/idle timeout, 1009 oversized event, 1003 binary frame, 1013 saturated
queue, 1011 unexpected failure, 1001 server shutdown.

Authorization is checked for commands and again immediately before each queued
outbound event. Account suspension blocks subsequent sensitive work; JWT expiry
closes idle sockets independently. A write accepted before expiry may finish its
transaction after disconnection, but no late ACK is sent to that expired socket.
Retry/history recovery handles that case. Real-time delivery is best effort, may
be duplicated or reordered across concurrent senders, and is not cross-worker.
The database/history ordering remains authoritative.

WeChat contacts are never injected into general socket events. Poll the private
handoff HTTP endpoint for consent state. No seller evidence is loaded by chat.

## Local launch and secret configuration

From `backend`, after normal dependency installation and additive migration:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws websockets-sansio --ws-max-size 16384 --ws-per-message-deflate false --log-level info
```

Do not run development downgrade commands. Configure a dedicated random
`BROWSE_CURSOR_SIGNING_KEY` for private pagination and a distinct canonical base64
32-byte `WECHAT_CONTACT_ENCRYPTION_KEY` for contact approval/retrieval. `.env.example`
contains no real secrets; local `.env` is not changed by this implementation.
Generate/provision keys through a private secret-management workflow, not in chat
or screenshots. Missing configuration fails closed; other chat operations do not
require contact encryption to be enabled.

Run one application worker. Docker includes matching frame/compression flags;
NGINX forwards WebSocket upgrades. Those files are not a completed production WSS
deployment. Preserve TLS certificate validation when installing dependencies.
For full limits, lifecycle, cryptography and scaling constraints, see the
[architecture decision](../architecture/ADR_PHASE_13_PRIVATE_CHAT.md).
