"""Chat-domain adversarial validation, cursor binding and consent-policy boundaries."""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy.dialects import mysql

from app.common.chat import (
    ChatCursorCodec, ChatError, CursorPosition, HandoffView, MessageView,
    validate_client_message_id, validate_message_content,
)
from app.common.enums import AccountStatus
from app.core.authorization import AuthorizationError
from app.core.config import settings
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.services import chat_authorization
from app.services.wechat_service import WeChatHandoffService, handoff_view

ACTOR = str(uuid4())
CONVERSATION = "cv-" + "a" * 32
MESSAGE = "msg-" + "b" * 32
AT = datetime(2026, 10, 24, 1, 2, 3, 456789)


@pytest.fixture
def cursor_config():
    return settings.model_copy(update={
        "browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48)),
    })


@pytest.fixture
def codec(cursor_config):
    return ChatCursorCodec(cursor_config)


def encoded(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def signed(codec, payload):
    body = payload if isinstance(payload, bytes) else json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    return encoded(body) + "." + encoded(hmac.new(
        codec._key, b"chat-page-v1\0" + body, hashlib.sha256,
    ).digest())


@pytest.mark.parametrize("purpose,reference,position_ref", [
    ("conversations", None, CONVERSATION), ("messages", CONVERSATION, MESSAGE),
])
@pytest.mark.parametrize("limit", [1, 20, 50])
def test_cursor_round_trip_stable_across_workers_without_identity_disclosure(
    codec, cursor_config, purpose, reference, position_ref, limit,
):
    position = CursorPosition(AT, position_ref)
    token = codec.encode(ACTOR, purpose, reference, limit, position)
    assert len(token) <= 512
    assert ChatCursorCodec(cursor_config).decode(token, ACTOR, purpose, reference, limit) == position
    decoded = base64.urlsafe_b64decode(token.split(".")[0] + "==").decode()
    assert ACTOR not in decoded and "user_id" not in decoded
    assert cursor_config.browse_cursor_signing_key.get_secret_value() not in token


def test_cursor_rejects_user_conversation_purpose_size_and_key_replay(codec, cursor_config):
    token = codec.encode(ACTOR, "messages", CONVERSATION, 20, CursorPosition(AT, MESSAGE))
    for actor, purpose, reference, limit in (
        (str(uuid4()), "messages", CONVERSATION, 20),
        (ACTOR, "conversations", None, 20),
        (ACTOR, "messages", "cv-" + "c" * 32, 20),
        (ACTOR, "messages", CONVERSATION, 50),
    ):
        with pytest.raises(ChatError, match="^Invalid cursor\\.$") as error:
            codec.decode(token, actor, purpose, reference, limit)
        assert error.value.status_code == 400
    rotated = ChatCursorCodec(cursor_config.model_copy(update={
        "browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48)),
    }))
    with pytest.raises(ChatError):
        rotated.decode(token, ACTOR, "messages", CONVERSATION, 20)


def test_cursor_rejects_corruption_noncanonical_encoding_and_bounded_fuzz(codec):
    token = codec.encode(ACTOR, "messages", CONVERSATION, 20, CursorPosition(AT, MESSAGE))
    malformed = [None, 1, True, "", "a", "a.b", token[:-1], token + "=", token + "\n",
                 "x" * 513, "!" + token[1:], token.replace(".", "..")]
    malformed.extend(secrets.token_urlsafe(secrets.randbelow(100) + 1) for _ in range(100))
    for value in malformed:
        with pytest.raises(ChatError, match="^Invalid cursor\\.$") as error:
            codec.decode(value, ACTOR, "messages", CONVERSATION, 20)
        assert error.value.status_code == 400


@pytest.mark.parametrize("field,value", [
    ("v", 2), ("v", True), ("v", "1"), ("f", "0" * 64), ("f", 1),
    ("t", "2026-10-24"), ("t", "2026-10-24T01:02:03.456789Z"),
    ("t", "2026-99-24T01:02:03.456789"), ("t", "0001-01-01T01:02:03.456789"),
    ("r", CONVERSATION), ("r", "msg-invalid"), ("r", None),
])
def test_valid_signature_cannot_bypass_cursor_payload_contract(codec, field, value):
    payload = {"v": 1, "f": codec._context(ACTOR, "messages", CONVERSATION, 20),
               "t": AT.isoformat(timespec="microseconds"), "r": MESSAGE}
    payload[field] = value
    with pytest.raises(ChatError) as error:
        codec.decode(signed(codec, payload), ACTOR, "messages", CONVERSATION, 20)
    assert error.value.status_code == 400


def test_cursor_rejects_missing_extra_duplicate_and_nonobject_payloads(codec):
    payload = {"v": 1, "f": codec._context(ACTOR, "messages", CONVERSATION, 20),
               "t": AT.isoformat(timespec="microseconds"), "r": MESSAGE}
    for altered in [dict(payload, actor_id=ACTOR), {k: v for k, v in payload.items() if k != "r"},
                    b'{"v":1,"v":1}', b'\xff\xfe', [], None]:
        with pytest.raises(ChatError):
            codec.decode(signed(codec, altered), ACTOR, "messages", CONVERSATION, 20)


@pytest.mark.parametrize("secret", [None, "", "short"])
def test_cursor_missing_dedicated_key_fails_closed_without_jwt_fallback(cursor_config, secret):
    config = cursor_config.model_copy(update={
        "browse_cursor_signing_key": SecretStr(secret) if secret is not None else None,
    })
    with pytest.raises(ChatError) as error:
        ChatCursorCodec(config)
    assert error.value.status_code == 503
    assert config.jwt_secret_key.get_secret_value() not in str(error.value)


def test_cursor_encode_rejects_aware_timestamp_instead_of_changing_seek_semantics(codec):
    with pytest.raises(ValueError):
        codec.encode(ACTOR, "messages", CONVERSATION, 20,
                     CursorPosition(AT.replace(tzinfo=timezone.utc), MESSAGE))


@pytest.mark.parametrize("content", [
    "Hello 你好 مرحبا café", "Line one\nLine two\tvalue", "Family 👩\u200d👩\u200d👦",
    "Persian می\u200cروم", "<b>plain text only</b>", "😀" * 2000,
])
def test_message_text_preserves_valid_unicode_as_plain_text(content):
    assert validate_message_content(content) == content


@pytest.mark.parametrize("content", [
    None, 42, {}, [], "", " \t\n", "\u200c\u200d", "\u0301", "a" * 2001,
    "a\x00b", "a\rb", "a\x1bb", "a\u202eb", "a\u2066b", "a\ufeffb", "a\ud800b",
])
def test_message_text_rejects_empty_controls_bidi_surrogates_and_wrong_types(content):
    with pytest.raises(ValueError, match="^Invalid message content\\.$"):
        validate_message_content(content)


def test_idempotency_identifier_is_canonical_and_never_coerced():
    identifier = str(uuid4())
    assert validate_client_message_id(identifier) == identifier
    for invalid in [identifier.upper(), "{" + identifier + "}", identifier.replace("-", ""),
                    None, 1, "client-message", identifier + "\n"]:
        with pytest.raises(ValueError):
            validate_client_message_id(invalid)


def test_sensitive_response_values_do_not_enter_debug_representations():
    message = MessageView(MESSAGE, CONVERSATION, "buyer", str(uuid4()), "private message body", AT)
    handoff = HandoffView("APPROVED", AT, AT, None, "private_contact")
    assert "private message body" not in repr(message)
    assert "private_contact" not in repr(handoff)


@pytest.mark.parametrize("method", ["conversation", "message"])
def test_history_sql_is_parameterized_owned_bounded_and_has_no_private_contact(method):
    statement = (ConversationRepository().page_statement(ACTOR, 50, CursorPosition(AT, CONVERSATION))
                 if method == "conversation" else MessageRepository().page_statement(
                     ACTOR, CONVERSATION, 50, CursorPosition(AT, MESSAGE)))
    compiled = statement.compile(dialect=mysql.dialect())
    sql = str(compiled)
    assert "LIMIT" in sql and "OFFSET" not in sql and "count(" not in sql.lower()
    assert "buyer_user_id =" in sql and "seller_user_id =" in sql
    assert ACTOR not in sql and ACTOR in compiled.params.values()
    assert 51 in compiled.params.values()
    assert "contact_ciphertext" not in sql and "password_hash" not in sql


def test_conversation_page_merges_two_indexed_bounded_disjoint_role_seeks():
    compiled = ConversationRepository().page_statement(
        ACTOR, 50, CursorPosition(AT, CONVERSATION),
    ).compile(dialect=mysql.dialect())
    sql = str(compiled)
    assert "UNION ALL" in sql
    assert sql.count("LIMIT") == 3
    assert "FORCE INDEX (ix_conversations_buyer_activity)" in sql
    assert "FORCE INDEX (ix_conversations_seller_activity)" in sql
    assert sql.count("JOIN product_listings") == 1
    assert list(compiled.params.values()).count(51) == 3
    assert "OFFSET" not in sql and "DISTINCT" not in sql


class ConsentCipher:
    def encrypt(self, contact, reference):
        return "encrypted:" + reference + ":" + contact

    def decrypt(self, ciphertext, reference):
        return ciphertext.removeprefix("encrypted:" + reference + ":")


def pending_request():
    return SimpleNamespace(status="PENDING", requested_at=AT, decided_at=None,
                           revoked_at=None, contact_ciphertext=None)


def test_approval_idempotency_conflict_and_terminal_revocation():
    service = WeChatHandoffService(None, ConsentCipher())
    row = pending_request()
    service._transition(row, "approve", CONVERSATION, "synthetic_contact")
    original = row.contact_ciphertext, row.decided_at
    assert handoff_view(row).contact is None
    service._transition(row, "approve", CONVERSATION, "synthetic_contact")
    assert (row.contact_ciphertext, row.decided_at) == original
    with pytest.raises(ChatError) as error:
        service._transition(row, "approve", CONVERSATION, "other_contact")
    assert error.value.status_code == 409
    service._transition(row, "revoke", CONVERSATION, None)
    assert row.status == "REVOKED" and row.contact_ciphertext is None
    revoked = row.revoked_at
    service._transition(row, "revoke", CONVERSATION, None)
    assert row.revoked_at == revoked
    with pytest.raises(ChatError):
        service._transition(row, "approve", CONVERSATION, "synthetic_contact")


@pytest.mark.parametrize("decision", ["deny", "revoke"])
def test_pending_request_can_be_terminally_closed_without_encrypting(decision):
    class UnavailableCipher:
        def encrypt(self, *args):
            pytest.fail("Closing consent must not require contact encryption.")
    service = WeChatHandoffService(None, UnavailableCipher())
    row = pending_request()
    service._transition(row, decision, CONVERSATION, None)
    assert row.status == {"deny": "DENIED", "revoke": "REVOKED"}[decision]
    assert row.contact_ciphertext is None
    service._transition(row, decision, CONVERSATION, None)
    with pytest.raises(ChatError) as error:
        service._transition(row, "approve", CONVERSATION, "synthetic_contact")
    assert error.value.status_code == 409


def test_revocation_exception_keeps_sorted_locks_and_still_requires_active_seller(monkeypatch):
    calls = []
    active = {"a-buyer": False, "z-seller": True}

    def locked_active(_db, user_id, *, eligible=False):
        calls.append(user_id)
        if not active[user_id]:
            raise AuthorizationError("Account unavailable.", 401)

    def locked_any(_repo, _db, user_id):
        calls.append(user_id)
        return SimpleNamespace(account_status=AccountStatus.SUSPENDED)

    monkeypatch.setattr(chat_authorization, "lock_active_user", locked_active)
    monkeypatch.setattr(chat_authorization.UserRepository, "get_by_id_for_update", locked_any)
    chat_authorization.lock_participants(None, "z-seller", "a-buyer", "z-seller",
                                         require_counterparty_active=False)
    assert calls == ["a-buyer", "z-seller"]
    with pytest.raises(ChatError) as error:
        chat_authorization.lock_participants(None, "z-seller", "a-buyer", "z-seller")
    assert error.value.status_code == 409
    active["z-seller"] = False
    with pytest.raises(ChatError) as error:
        chat_authorization.lock_participants(None, "z-seller", "a-buyer", "z-seller",
                                             require_counterparty_active=False)
    assert error.value.status_code == 401
