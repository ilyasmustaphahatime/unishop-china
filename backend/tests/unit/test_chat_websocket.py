"""Real ASGI WebSocket protocol tests and isolated delivery-resource invariants."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import logging
from threading import Event as ThreadEvent
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import jwt
import pytest
from starlette.websockets import WebSocketDisconnect

from app.common.chat import ChatError, MessageView, SendResult
from app.core.chat_logging import ChatTransportLogFilter, install_chat_log_protection
from app.core.config import allowed_frontend_origins, settings
from app.core.rate_limit import InMemoryRateLimiter
from app.core.websocket_manager import WebSocketConnectionManager
from app.schemas.chat_events import MAX_EVENT_BYTES, parse_event
from app.services.token_service import AccessTokenService

REFERENCE = "cv-" + "a" * 32
OTHER_REFERENCE = "cv-" + "b" * 32
ACTOR = "00000000-0000-4000-8000-000000000001"
OTHER_ACTOR = "00000000-0000-4000-8000-000000000002"
PATH = "/api/v1/chat/ws"


class Socket:
    def __init__(self, *, slow=False, broken=False):
        self.sent = []
        self.codes = []
        self.slow = slow
        self.broken = broken
        self.started = asyncio.Event()
        self.closed = asyncio.Event()

    async def send_json(self, payload):
        self.started.set()
        if self.slow:
            await asyncio.Event().wait()
        if self.broken:
            raise OSError("Private transport detail")
        self.sent.append(payload)

    async def close(self, *, code):
        self.codes.append(code)
        self.closed.set()


async def allow(_actor, _reference):
    return None


def test_manager_pending_global_peer_and_user_caps_and_cleanup():
    async def scenario():
        manager = WebSocketConnectionManager(max_connections=3, max_connections_per_peer=2,
                                             max_connections_per_user=1)
        first = manager.reserve(Socket(), "peer1")
        second = manager.reserve(Socket(), "peer1")
        assert manager.reserve(Socket(), "peer1") is None
        third = manager.reserve(Socket(), "peer2")
        assert manager.reserve(Socket(), "peer3") is None
        assert manager.authenticate(first, ACTOR, time.time() + 60, allow)
        assert not manager.authenticate(second, ACTOR, time.time() + 60, allow)
        assert manager.authenticate(third, OTHER_ACTOR, time.time() + 60, allow)
        await manager.shutdown()
        assert not manager.connections
        assert first.writer.done() and first.expiry.done() and third.writer.done()
    asyncio.run(scenario())


def test_manager_subscription_limit_duplicate_and_broadcast_isolation():
    async def scenario():
        manager = WebSocketConnectionManager(max_subscriptions=1)
        first = manager.reserve(Socket(), "peer1")
        second = manager.reserve(Socket(), "peer2")
        for item in (first, second):
            assert manager.authenticate(item, ACTOR, time.time() + 60, allow)
        assert manager.subscribe(first, REFERENCE)
        assert manager.subscribe(first, REFERENCE)
        assert not manager.subscribe(first, OTHER_REFERENCE)
        assert manager.subscribe(second, OTHER_REFERENCE)
        await manager.publish(REFERENCE, {"type": "message.created"})
        await asyncio.wait_for(first.websocket.started.wait(), 1)
        await asyncio.sleep(0)
        assert first.websocket.sent == [{"type": "message.created"}]
        assert second.websocket.sent == []
        await manager.shutdown()
        assert not first.subscriptions and not second.subscriptions
    asyncio.run(scenario())


def test_manager_authorization_rechecked_after_enqueue_before_bytes():
    async def scenario():
        ready = asyncio.Event()
        calls = []
        async def reject(actor, reference):
            calls.append((actor, reference))
            await ready.wait()
            raise ChatError("Private denied membership", 404)
        manager = WebSocketConnectionManager()
        connection = manager.reserve(Socket(), "peer")
        manager.authenticate(connection, ACTOR, time.time() + 60, reject)
        await manager.enqueue(connection, {"private": "queued message"}, REFERENCE)
        await asyncio.sleep(0)
        ready.set()
        await asyncio.wait_for(connection.websocket.closed.wait(), 1)
        assert calls == [(ACTOR, REFERENCE)]
        assert connection.websocket.sent == [] and connection.closed
        assert not manager.connections
    asyncio.run(scenario())


@pytest.mark.parametrize("problem", ["slow", "broken", "expiry", "queue"])
def test_manager_slow_broken_expired_and_full_queue_fail_closed(problem):
    async def scenario():
        manager = WebSocketConnectionManager(max_queue=1, send_timeout=0.02)
        socket = Socket(slow=problem == "slow", broken=problem == "broken")
        connection = manager.reserve(socket, "peer")
        if problem == "queue":
            await manager.enqueue(connection, {"first": True})
            await manager.enqueue(connection, {"second": True})
            assert socket.codes == [1013]
        else:
            lifetime = 0.02 if problem == "expiry" else 60
            manager.authenticate(connection, ACTOR, time.time() + lifetime, allow)
            if problem != "expiry":
                await manager.enqueue(connection, {"private": "message"}, REFERENCE)
            await asyncio.wait_for(socket.closed.wait(), 1)
        assert not manager.connections and connection.closed and connection.queue.empty()
        assert not socket.sent
        await manager.shutdown()
    asyncio.run(scenario())


def test_manager_expiry_cancels_an_inflight_slow_writer():
    async def scenario():
        manager = WebSocketConnectionManager(send_timeout=5)
        connection = manager.reserve(Socket(slow=True), "peer")
        manager.authenticate(connection, ACTOR, time.time() + 0.03, allow)
        await manager.enqueue(connection, {"private": "message"}, REFERENCE)
        await asyncio.wait_for(connection.websocket.started.wait(), 1)
        await asyncio.wait_for(connection.websocket.closed.wait(), 1)
        assert connection.websocket.codes == [4401] and not connection.websocket.sent
        assert connection.writer.done()
    asyncio.run(scenario())


def test_manager_full_slow_consumer_does_not_delay_other_recipient():
    async def scenario():
        release = asyncio.Event()
        class SlowCloseSocket(Socket):
            async def close(self, *, code):
                await release.wait()
                await super().close(code=code)
        manager = WebSocketConnectionManager(max_queue=1)
        slow = manager.reserve(SlowCloseSocket(), "slow")
        fast = manager.reserve(Socket(), "fast")
        manager.subscribe(slow, REFERENCE)
        manager.authenticate(fast, ACTOR, time.time() + 60, allow)
        manager.subscribe(fast, REFERENCE)
        await manager.enqueue(slow, {"queued": "old"}, REFERENCE)
        publish = asyncio.create_task(manager.publish(REFERENCE, {"new": "message"}))
        try:
            await asyncio.wait_for(fast.websocket.started.wait(), 0.5)
            assert fast.websocket.sent == [{"new": "message"}]
            assert not publish.done()
        finally:
            release.set()
            await publish
            await manager.shutdown()
    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [
    '{"v":1,"v":1,"type":"ping"}', '{"v":true,"type":"ping"}',
    '{"v":"1","type":"ping"}', '{"v":2,"type":"ping"}',
    '{"v":1,"type":"unknown"}', '{"v":1,"type":"ping","user_id":"forged"}',
    '{"v":1,"type":"ping","extra":NaN}', '[]', 'null', '{',
    '{"v":1,"type":"subscribe","conversation_ref":"internal-id"}',
    '{"v":1,"type":"authenticate","access_token":123}',
])
def test_event_contract_rejects_malformed_version_types_extra_and_duplicate_fields(payload):
    with pytest.raises(ValueError):
        parse_event(payload)


@pytest.mark.parametrize("content", ["", " \t\n", "\u200d", "bad\x00", "bad\r", "bad\u202e", "x" * 2001])
def test_event_contract_uses_shared_plain_text_validation(content):
    with pytest.raises(ValueError):
        parse_event(json.dumps({"v": 1, "type": "message.send", "conversation_ref": REFERENCE,
                               "client_message_id": str(uuid4()), "content": content}))


def test_event_contract_preserves_international_plain_text_and_hides_auth_repr():
    content = "Hello مرحبا 你好 👩\u200d💻\n<script>plain text</script>"
    event = parse_event(json.dumps({"v": 1, "type": "message.send", "conversation_ref": REFERENCE,
                                  "client_message_id": str(uuid4()), "content": content}))
    assert event.content == content
    auth = parse_event('{"v":1,"type":"authenticate","access_token":"synthetic-private-token"}')
    assert "synthetic-private-token" not in repr(auth)


@pytest.fixture
def protocol(monkeypatch):
    from app.api.v1.chat import websocket as transport
    config = settings.model_copy(update={"app_debug": False})
    manager = WebSocketConnectionManager()
    state = {"active": True, "calls": [], "sent": [], "created": True, "send_error": None}
    state["original_send"] = transport._send

    def authorize(_config, actor, reference=None):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AssertionError("Synchronous authorization ran on the event loop")
        state["calls"].append((actor, reference))
        if not state["active"]:
            raise ChatError("Account unavailable.", 401)
        if reference not in (None, REFERENCE):
            raise ChatError("Conversation unavailable.", 404)

    def send(_config, actor, event, expires_at):
        assert expires_at > time.time()
        authorize(_config, actor, event.conversation_ref)
        if state["send_error"]:
            raise state["send_error"]
        message = MessageView("msg-" + "c" * 32, event.conversation_ref, "buyer",
            event.client_message_id, event.content, datetime.now(timezone.utc))
        state["sent"].append(message)
        return SendResult(message, state["created"])

    monkeypatch.setattr(transport, "_authorize", authorize)
    monkeypatch.setattr(transport, "_send", send)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await manager.shutdown()
    app = FastAPI(lifespan=lifespan)
    app.state.settings, app.state.chat_manager = config, manager
    app.include_router(transport.router, prefix="/api/v1/chat")
    with TestClient(app) as client:
        yield client, manager, config, state, transport
    assert not manager.connections


def connect(protocol, *, token=None):
    client, _, config, _, _ = protocol
    socket = client.websocket_connect(PATH, headers={"Origin": allowed_frontend_origins(config)[0]})
    return socket, token or AccessTokenService(config).create_access_token(ACTOR)


def authenticate(socket, token):
    socket.send_json({"v": 1, "type": "authenticate", "access_token": token})
    assert socket.receive_json() == {"v": 1, "type": "authenticated"}


@pytest.mark.parametrize("case", ["missing", "null", "evil", "duplicate", "query", "header", "subprotocol"])
def test_protocol_rejects_invalid_origin_and_url_or_header_credentials(protocol, case):
    client, manager, config, _, _ = protocol
    origin = allowed_frontend_origins(config)[0]
    headers = {"Origin": origin}
    if case == "missing":
        headers = {}
    elif case in {"null", "evil"}:
        headers = {"Origin": "null" if case == "null" else "https://attacker.invalid"}
    elif case == "duplicate":
        headers = httpx.Headers([("Origin", origin), ("Origin", origin)])
    elif case == "header":
        headers["Authorization"] = "Bearer synthetic"
    with pytest.raises(Exception) as error:
        with client.websocket_connect(PATH + ("?access_token=synthetic" if case == "query" else ""),
                headers=headers, subprotocols=["synthetic"] if case == "subprotocol" else None):
            pytest.fail("Unsafe handshake accepted")
    response = error.value
    assert getattr(response, "status_code", None) == 403
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert not manager.connections


@pytest.mark.parametrize("case", ["invalid", "expired", "wrong_type", "wrong_issuer", "wrong_audience", "suspended"])
def test_protocol_rejects_invalid_access_tokens_and_accounts(protocol, case):
    _, _, config, state, _ = protocol
    token = AccessTokenService(config).create_access_token(ACTOR)
    if case == "invalid":
        token = "invalid"
    elif case == "suspended":
        state["active"] = False
    else:
        claims = jwt.decode(token, options={"verify_signature": False})
        if case == "expired":
            claims["exp"] = int(time.time()) - 600
        else:
            claims[{"wrong_type": "type", "wrong_issuer": "iss", "wrong_audience": "aud"}[case]] = "invalid"
        token = jwt.encode(claims, config.jwt_secret_key.get_secret_value(), algorithm=config.jwt_algorithm)
    context, _ = connect(protocol)
    with context as socket:
        socket.send_json({"v": 1, "type": "authenticate", "access_token": token})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 4401


def test_protocol_authentication_deadline_without_first_message(protocol, monkeypatch):
    monkeypatch.setattr(protocol[4], "WS_AUTH_TIMEOUT_SECONDS", 0.02)
    context, _ = connect(protocol)
    with context as socket:
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1008


def test_protocol_auth_deadline_is_enforced_while_database_worker_is_blocked(protocol, monkeypatch):
    transport = protocol[4]
    release = ThreadEvent()
    original = transport._authenticate
    def blocked_auth(config, token):
        release.wait(0.5)
        return original(config, token)
    monkeypatch.setattr(transport, "WS_AUTH_TIMEOUT_SECONDS", 0.03)
    monkeypatch.setattr(transport, "_authenticate", blocked_auth)
    context, token = connect(protocol)
    try:
        with context as socket:
            started = time.monotonic()
            socket.send_json({"v": 1, "type": "authenticate", "access_token": token})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 1008
            assert time.monotonic() - started < 0.3
            assert not protocol[1].connections
    finally:
        release.set()


def test_protocol_expired_worker_never_opens_a_database_session(protocol, monkeypatch):
    transport = protocol[4]
    # The fixture substitutes the send adapter; exercise the saved original below.
    original_send = protocol[3]["original_send"]
    def forbidden_session():
        pytest.fail("Expired send opened a database session")
    monkeypatch.setattr(transport, "SessionLocal", forbidden_session)
    event = parse_event(json.dumps({"v": 1, "type": "message.send", "conversation_ref": REFERENCE,
                                   "client_message_id": str(uuid4()), "content": "late request"}))
    with pytest.raises(ChatError) as error:
        original_send(protocol[2], ACTOR, event, time.time() - 1)
    assert error.value.status_code == 401


def test_protocol_requires_authentication_before_subscription(protocol):
    context, _ = connect(protocol)
    with context as socket:
        socket.send_json({"v": 1, "type": "subscribe", "conversation_ref": REFERENCE})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 4401


def test_protocol_subscriptions_authorization_no_private_error_detail(protocol):
    context, token = connect(protocol)
    with context as socket:
        authenticate(socket, token)
        socket.send_json({"v": 1, "type": "subscribe", "conversation_ref": OTHER_REFERENCE})
        assert socket.receive_json() == {"v": 1, "type": "error", "code": "not_found"}
        socket.send_json({"v": 1, "type": "subscribe", "conversation_ref": REFERENCE})
        assert socket.receive_json() == {"v": 1, "type": "subscribed", "conversation_ref": REFERENCE}


@pytest.mark.parametrize("created", [True, False])
def test_protocol_committed_ack_broadcast_and_idempotent_replay(protocol, created):
    context, token = connect(protocol)
    _, _, _, state, _ = protocol
    state["created"] = created
    with context as socket:
        authenticate(socket, token)
        socket.send_json({"v": 1, "type": "subscribe", "conversation_ref": REFERENCE})
        assert socket.receive_json()["type"] == "subscribed"
        socket.send_json({"v": 1, "type": "message.send", "conversation_ref": REFERENCE,
                          "client_message_id": str(uuid4()), "content": "مرحبا 你好"})
        ack = socket.receive_json()
        assert state["sent"] and ack["type"] == "message.ack" and ack["created"] is created
        assert ack["message"]["content"] == "مرحبا 你好"
        assert not any(key in json.dumps(ack) for key in ("user_id", "wechat", "storage_key"))
        if created:
            assert socket.receive_json() == {"v": 1, "type": "message.created", "message": ack["message"]}
        socket.send_json({"v": 1, "type": "ping"})
        assert socket.receive_json() == {"v": 1, "type": "pong"}


def test_protocol_failed_service_commit_never_acknowledges_or_broadcasts(protocol):
    context, token = connect(protocol)
    protocol[3]["send_error"] = RuntimeError("private database detail")
    with context as socket:
        authenticate(socket, token)
        socket.send_json({"v": 1, "type": "message.send", "conversation_ref": REFERENCE,
                          "client_message_id": str(uuid4()), "content": "not committed"})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1011 and not protocol[3]["sent"]


def test_protocol_suspension_after_connection_prevents_commands(protocol):
    context, token = connect(protocol)
    with context as socket:
        authenticate(socket, token)
        protocol[3]["active"] = False
        socket.send_json({"v": 1, "type": "ping"})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 4401


@pytest.mark.parametrize("case,code", [("oversized", 1009), ("binary", 1003), ("malformed", 1008),
                                     ("duplicate", 1008), ("reauth", 1008), ("impersonate", 1008)])
def test_protocol_rejects_oversized_binary_and_malformed_events(protocol, case, code):
    context, token = connect(protocol)
    with context as socket:
        authenticate(socket, token)
        if case == "binary":
            socket.send_bytes(b"private bytes")
        elif case == "oversized":
            socket.send_text("x" * (MAX_EVENT_BYTES + 1))
        elif case == "malformed":
            socket.send_text("{")
        elif case == "duplicate":
            socket.send_text('{"v":1,"type":"ping","type":"ping"}')
        elif case == "reauth":
            socket.send_json({"v": 1, "type": "authenticate", "access_token": token})
        else:
            socket.send_json({"v": 1, "type": "message.send", "conversation_ref": REFERENCE,
                "client_message_id": str(uuid4()), "content": "hello", "sender_id": OTHER_ACTOR})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == code and not protocol[3]["sent"]


def test_protocol_frame_rate_limit_and_disconnect_cleanup(protocol):
    context, token = connect(protocol)
    protocol[1].user_budget = InMemoryRateLimiter(max_requests=1, window_seconds=60, max_keys=10)
    with context as socket:
        authenticate(socket, token)
        socket.send_json({"v": 1, "type": "ping"})
        assert socket.receive_json()["type"] == "pong"
        socket.send_json({"v": 1, "type": "ping"})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 1008
    assert not protocol[1].connections


def test_protocol_token_expiry_timer_closes_idle_connection(protocol, monkeypatch):
    transport = protocol[4]
    original = transport._authenticate
    def short_auth(config, token):
        from dataclasses import replace
        return replace(original(config, token), expires_at=datetime.now(timezone.utc) + timedelta(seconds=0.05))
    monkeypatch.setattr(transport, "_authenticate", short_auth)
    context, token = connect(protocol)
    with context as socket:
        authenticate(socket, token)
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 4401


def test_protocol_expiry_closes_during_accepted_send_without_late_ack(protocol, monkeypatch):
    transport = protocol[4]
    original_auth, original_send = transport._authenticate, transport._send
    release, entered = ThreadEvent(), ThreadEvent()
    def short_auth(config, token):
        from dataclasses import replace
        return replace(original_auth(config, token), expires_at=datetime.now(timezone.utc) + timedelta(seconds=0.08))
    def accepted_send(config, actor, event, expires_at):
        # Authorization and acceptance occurred before expiry. Commit completion may
        # outlive the connection; storage/history, not a late ACK, recovers it.
        result = original_send(config, actor, event, expires_at)
        entered.set()
        release.wait(0.5)
        return result
    monkeypatch.setattr(transport, "_authenticate", short_auth)
    monkeypatch.setattr(transport, "_send", accepted_send)
    context, token = connect(protocol)
    try:
        with context as socket:
            authenticate(socket, token)
            socket.send_json({"v": 1, "type": "message.send", "conversation_ref": REFERENCE,
                "client_message_id": str(uuid4()), "content": "accepted before expiry"})
            assert entered.wait(0.3)
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 4401
            assert len(protocol[3]["sent"]) == 1
            assert not protocol[1].connections
            release.set()
    finally:
        release.set()


def test_real_app_lifespan_installs_chat_transport_and_shuts_manager_down():
    from app.main import create_app
    app = create_app(settings.model_copy(update={"app_debug": False}))
    manager = app.state.chat_manager
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        # A real app route is present but needs Origin + explicit first-message auth.
        with pytest.raises(Exception) as error:
            with client.websocket_connect(PATH):
                pytest.fail("Missing Origin accepted")
        assert getattr(error.value, "status_code", None) == 403
    assert not manager.connections


def test_transport_logging_drops_query_credentials_and_frame_debug_and_sanitizes_decoder():
    guard = ChatTransportLogFilter()
    handshake = logging.LogRecord("uvicorn.error", logging.INFO, "server.py", 1,
        '%s - "WebSocket %s" [accepted]', ("peer", PATH + "?access_token=synthetic-private"), None)
    assert not guard.filter(handshake)
    debug = logging.LogRecord("websockets.server", logging.DEBUG, "protocol.py", 1,
        "TEXT %r", ("private message",), None)
    assert not guard.filter(debug)
    error = logging.LogRecord("uvicorn.error", logging.ERROR, "websockets_sansio_impl.py", 1,
        "Invalid private bytes", (), (ValueError, ValueError("private bytes"), None))
    assert guard.filter(error)
    assert error.getMessage() == "WebSocket protocol error." and error.exc_info is None
    install_chat_log_protection()
    install_chat_log_protection()
    for name in ("uvicorn.error", "uvicorn.access", "uvicorn.asgi", "websockets.server"):
        assert sum(isinstance(item, ChatTransportLogFilter) for item in logging.getLogger(name).filters) == 1


def test_denial_leaves_content_length_to_sansio_protocol():
    from app.api.v1.chat.websocket import _deny

    class DeniedSocket:
        scope = {"extensions": {"websocket.http.response": {}}}

        async def send_denial_response(self, response):
            assert response.status_code == 403
            assert "content-length" not in response.headers
            assert response.headers["cache-control"] == "no-store"
            assert response.body == b'{"detail":"Connection unavailable."}'

    asyncio.run(_deny(DeniedSocket()))
