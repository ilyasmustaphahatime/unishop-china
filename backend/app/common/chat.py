"""Transport-independent chat contracts, validation and signed pagination positions."""
import base64
import binascii
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import hmac
import json
import re
from typing import Generic, TypeVar
import unicodedata
from uuid import UUID

T = TypeVar("T")


class ChatError(Exception):
    def __init__(self, message: str, status_code: int = 404, code: str = "chat_not_found"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True, slots=True)
class ConversationView:
    conversation_ref: str
    product_slug: str
    role: str
    created_at: datetime
    activity_at: datetime


@dataclass(frozen=True, slots=True)
class MessageView:
    message_ref: str
    conversation_ref: str
    sender_role: str
    client_message_id: str
    content: str = field(repr=False)
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SendResult:
    message: MessageView
    created: bool


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: list[T]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class HandoffView:
    status: str
    requested_at: datetime | None
    decided_at: datetime | None
    revoked_at: datetime | None
    contact: str | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class CursorPosition:
    value: datetime
    reference: str


def validate_conversation_ref(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"cv-[0-9a-f]{32}", value):
        raise ValueError("Invalid conversation reference.")
    return value


def validate_message_ref(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"msg-[0-9a-f]{32}", value):
        raise ValueError("Invalid message reference.")
    return value


def validate_client_message_id(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid client message identifier.")
    try:
        canonical = str(UUID(value))
    except (ValueError, AttributeError):
        raise ValueError("Invalid client message identifier.") from None
    if value != canonical:
        raise ValueError("Invalid client message identifier.")
    return value


def validate_message_content(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 2000:
        raise ValueError("Invalid message content.")
    try:
        if len(value.encode("utf-8")) > 8000:
            raise ValueError("Invalid message content.")
    except UnicodeError:
        raise ValueError("Invalid message content.") from None
    meaningful = False
    for character in value:
        category = unicodedata.category(character)
        if (category == "Cc" and character not in "\t\n"
                or category == "Cf" and character not in "\u200c\u200d"
                or category == "Cs"):
            raise ValueError("Invalid message content.")
        meaningful |= category[0] in "LNPS"
    if not meaningful:
        raise ValueError("Invalid message content.")
    # Preserve exact accepted text; HTML-looking content is still only plain text.
    return value


def validate_page_limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 50:
        raise ChatError("Invalid pagination parameters.", 422, "chat_validation")
    return value


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError
    data = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if _encode(data) != value:
        raise ValueError
    return data


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


class ChatCursorCodec:
    """Separate signing domain; user, list purpose, conversation and size are bound."""

    def __init__(self, config):
        secret = config.browse_cursor_signing_key
        source = secret.get_secret_value().strip() if secret is not None else ""
        if len(source) < 32:
            raise ChatError("Chat pagination unavailable.", 503, "chat_unavailable")
        self._key = hmac.new(source.encode("utf-8"), b"unishop-chat-cursors-v1",
                             hashlib.sha256).digest()

    def _context(self, actor_id: str, purpose: str, reference: str | None, limit: int) -> str:
        context = json.dumps({"a": actor_id, "p": purpose, "c": reference, "l": limit},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self._key, b"chat-context-v1\0" + context, hashlib.sha256).hexdigest()

    def encode(self, actor_id: str, purpose: str, reference: str | None, limit: int,
               position: CursorPosition) -> str:
        if position.value.tzinfo is not None or position.value.year < 1000:
            raise ValueError("Cursor positions must use MySQL naive UTC.")
        validator = validate_conversation_ref if purpose == "conversations" else validate_message_ref
        payload = {"v": 1, "f": self._context(actor_id, purpose, reference, limit),
                   "t": position.value.isoformat(timespec="microseconds"),
                   "r": validator(position.reference)}
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        signature = hmac.new(self._key, b"chat-page-v1\0" + data, hashlib.sha256).digest()
        return _encode(data) + "." + _encode(signature)

    def decode(self, token: str, actor_id: str, purpose: str, reference: str | None,
               limit: int) -> CursorPosition:
        try:
            if not isinstance(token, str) or not token or len(token) > 512 or token.count(".") != 1:
                raise ValueError
            body, signature = token.split(".")
            data, actual = _decode(body), _decode(signature)
            expected = hmac.new(self._key, b"chat-page-v1\0" + data, hashlib.sha256).digest()
            if len(actual) != 32 or not hmac.compare_digest(actual, expected):
                raise ValueError
            payload = json.loads(data, object_pairs_hook=_unique_pairs)
            if (not isinstance(payload, dict) or set(payload) != {"v", "f", "t", "r"}
                    or type(payload["v"]) is not int or payload["v"] != 1
                    or not isinstance(payload["f"], str)
                    or not hmac.compare_digest(payload["f"],
                                               self._context(actor_id, purpose, reference, limit))
                    or not isinstance(payload["t"], str)
                    or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}",
                                        payload["t"])):
                raise ValueError
            value = datetime.fromisoformat(payload["t"])
            if value.year < 1000:
                raise ValueError
            validator = (validate_conversation_ref if purpose == "conversations"
                         else validate_message_ref)
            return CursorPosition(value, validator(payload["r"]))
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError, binascii.Error):
            raise ChatError("Invalid cursor.", 400, "chat_cursor") from None
