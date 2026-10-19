"""Private HMAC keysets; no raw user or internal product identifiers in tokens."""
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import re

from app.common.product_slugs import validate_product_slug
from app.core.config import Settings
from app.schemas.product_personalization import PersonalListKind


class InvalidPersonalizationCursor(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PersonalizationPosition:
    value: datetime
    slug: str


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InvalidPersonalizationCursor
    decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if _encode(decoded) != value:
        raise InvalidPersonalizationCursor
    return decoded


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidPersonalizationCursor
        result[key] = value
    return result


class PersonalizationCursorCodec:
    def __init__(self, config: Settings):
        dedicated = (config.browse_cursor_signing_key.get_secret_value().strip()
                     if config.browse_cursor_signing_key is not None else "")
        source = dedicated or config.jwt_secret_key.get_secret_value()
        # Shared runtime configuration, but a key distinct from both JWT and browse.
        self._key = hmac.new(source.encode("utf-8"), b"unishop-personal-lists-v1",
                             hashlib.sha256).digest()

    def _context(self, user_id: str, kind: PersonalListKind, limit: int) -> str:
        context = json.dumps({"u": user_id, "p": kind.value, "l": limit, "v": 1},
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(self._key, b"personal-context-v1\0" + context,
                        hashlib.sha256).hexdigest()

    def encode(self, user_id: str, kind: PersonalListKind, limit: int,
               position: PersonalizationPosition) -> str:
        if position.value.tzinfo is not None:
            raise ValueError("Cursor positions must use naive UTC.")
        payload = {"v": 1, "f": self._context(user_id, kind, limit),
                   "k": position.value.isoformat(timespec="microseconds"),
                   "r": validate_product_slug(position.slug)}
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        signature = hmac.new(self._key, b"personal-page-v1\0" + data,
                             hashlib.sha256).digest()
        return f"{_encode(data)}.{_encode(signature)}"

    def decode(self, token: str, user_id: str, kind: PersonalListKind,
               limit: int) -> PersonalizationPosition:
        try:
            if not token or len(token) > 512 or token.count(".") != 1:
                raise InvalidPersonalizationCursor
            body, signature = token.split(".")
            data, actual = _decode(body), _decode(signature)
            expected = hmac.new(self._key, b"personal-page-v1\0" + data,
                                hashlib.sha256).digest()
            if len(actual) != 32 or not hmac.compare_digest(actual, expected):
                raise InvalidPersonalizationCursor
            payload = json.loads(data, object_pairs_hook=_unique_pairs)
            if (not isinstance(payload, dict) or set(payload) != {"v", "f", "k", "r"}
                    or type(payload["v"]) is not int or payload["v"] != 1
                    or not isinstance(payload["f"], str)
                    or not hmac.compare_digest(payload["f"], self._context(user_id, kind, limit))
                    or not isinstance(payload["k"], str)
                    or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}", payload["k"])):
                raise InvalidPersonalizationCursor
            value = datetime.fromisoformat(payload["k"])
            if value.year < 1000:
                raise InvalidPersonalizationCursor
            return PersonalizationPosition(value, validate_product_slug(payload["r"]))
        except (ValueError, TypeError, KeyError, OverflowError, UnicodeError, binascii.Error):
            raise InvalidPersonalizationCursor("Invalid cursor.") from None
