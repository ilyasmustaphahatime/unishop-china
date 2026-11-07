"""Adversarial tests for contact encryption and pre-authentication HTTP limits."""
import asyncio
import base64
import secrets

import pytest
from pydantic import SecretStr, ValidationError

from app.common.chat import ChatError
from app.core.chat_limits import chat_limiters, clear_chat_limits, consume_chat_limit
from app.core.chat_security import ChatRequestBoundary
from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter
from app.integrations.wechat_cipher import WeChatCipher
from app.schemas.wechat_share import WeChatApproval

REF = "cv-" + "a" * 32
OTHER_REF = "cv-" + "b" * 32
CONTACT = "synthetic_test"


def cipher_config(**overrides):
    return settings.model_copy(update={
        "wechat_contact_encryption_key": SecretStr(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()),
        **overrides,
    })


def test_cipher_round_trip_random_nonce_and_conversation_binding():
    cipher = WeChatCipher(cipher_config())
    first, second = cipher.encrypt(CONTACT, REF), cipher.encrypt(CONTACT, REF)
    assert first != second and CONTACT not in first
    assert cipher.decrypt(first, REF) == CONTACT
    with pytest.raises(ChatError) as error:
        cipher.decrypt(first, OTHER_REF)
    assert error.value.status_code == 503 and CONTACT not in str(error.value)


@pytest.mark.parametrize("key", [None, "", "invalid", "A" * 44, "x" * 500])
def test_cipher_missing_or_malformed_secret_fails_closed(key):
    cipher = WeChatCipher(cipher_config(wechat_contact_encryption_key=SecretStr(key) if key is not None else None))
    with pytest.raises(ChatError) as error:
        cipher.encrypt(CONTACT, REF)
    assert error.value.status_code == 503
    assert CONTACT not in str(error.value)


def test_cipher_rejects_jwt_key_reuse_and_wrong_key():
    config = cipher_config()
    reused = config.model_copy(update={"jwt_secret_key": config.wechat_contact_encryption_key})
    with pytest.raises(ChatError):
        WeChatCipher(reused).encrypt(CONTACT, REF)
    encrypted = WeChatCipher(config).encrypt(CONTACT, REF)
    with pytest.raises(ChatError):
        WeChatCipher(cipher_config()).decrypt(encrypted, REF)


@pytest.mark.parametrize("value", ["v2.abcd", "v1.!", "v1." + "A" * 200, "", "v1.AAAA"])
def test_cipher_rejects_malformed_envelope(value):
    with pytest.raises(ChatError) as error:
        WeChatCipher(cipher_config()).decrypt(value, REF)
    assert error.value.status_code == 503


def test_cipher_rejects_tampered_authenticated_bytes():
    cipher = WeChatCipher(cipher_config())
    encrypted = cipher.encrypt(CONTACT, REF)
    payload = bytearray(base64.urlsafe_b64decode(encrypted[3:]))
    payload[-1] ^= 1
    with pytest.raises(ChatError):
        cipher.decrypt("v1." + base64.urlsafe_b64encode(payload).decode(), REF)


@pytest.mark.parametrize("contact", ["", "short", "123456", "test<script>", "abcdef\n", "测试测试测试", "a" * 21, 123456])
def test_private_contact_contract_is_strict_and_direct_cipher_validates(contact):
    with pytest.raises(ValidationError):
        WeChatApproval(contact=contact)
    with pytest.raises(ChatError) as error:
        WeChatCipher(cipher_config()).encrypt(contact, REF)
    assert error.value.status_code == 422


def test_private_contact_is_not_in_request_model_repr():
    assert CONTACT not in repr(WeChatApproval(contact=CONTACT))


async def boundary_request(boundary, *, body=b"", path="/api/v1/chat/conversations",
                           method="POST", query=b"", headers=None):
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(event):
        sent.append(event)

    scope = {"type": "http", "method": method, "path": path, "raw_path": path.encode(),
             "query_string": query, "client": ("127.0.0.1", 1),
             "headers": headers if headers is not None else [(b"content-type", b"application/json")]}
    await boundary(scope, receive, send)
    return sent


@pytest.mark.parametrize("body,path,method,query,expected", [
    (b'{"product_slug":"a","product_slug":"b"}', "/api/v1/chat/conversations", "POST", b"", 422),
    (b"[1]", "/api/v1/chat/conversations", "POST", b"", 422),
    (b"x" * 1025, "/api/v1/chat/conversations", "POST", b"", 413),
    (b"{}", "/api/v1/chat/conversations/abc/wechat/request", "POST", b"", 422),
    (b"{}", "/api/v1/chat/conversations", "GET", b"", 422),
    (b"", "/api/v1/chat/conversations", "GET", b"x" * 1201, 413),
    (b"{", "/api/v1/chat/conversations", "POST", b"", 422),
])
def test_http_boundary_rejects_ambiguous_or_unbounded_input_before_handler(body, path, method, query, expected):
    async def app(*args):
        pytest.fail("Rejected request reached the application.")
    events = asyncio.run(boundary_request(ChatRequestBoundary(app, "/api/v1"),
                                         body=body, path=path, method=method, query=query))
    assert events[0]["status"] == expected
    assert (b"cache-control", b"no-store") in events[0]["headers"]
    if len(body) > 1:
        assert body not in events[-1]["body"]


def test_malformed_requests_still_consume_pre_auth_peer_budget():
    async def app(*args):
        pytest.fail("Malformed request reached the application.")
    boundary = ChatRequestBoundary(app, "/api/v1")
    boundary.write = InMemoryRateLimiter(max_requests=2, window_seconds=60, max_keys=1)
    codes = [asyncio.run(boundary_request(boundary, body=b"{"))[0]["status"] for _ in range(3)]
    assert codes == [422, 422, 429]


def test_account_budget_is_shared_between_transports_and_bounded(monkeypatch):
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60, max_keys=1)
    monkeypatch.setitem(chat_limiters, "send", limiter)
    clear_chat_limits()
    consume_chat_limit("send", "synthetic-user")
    consume_chat_limit("send", "synthetic-user")
    with pytest.raises(ChatError) as error:
        consume_chat_limit("send", "synthetic-user")
    assert error.value.status_code == 429
    with pytest.raises(ChatError):
        consume_chat_limit("send", "another-user")
    assert len(limiter._requests) == 1
    clear_chat_limits()
