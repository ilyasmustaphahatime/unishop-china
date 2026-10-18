"""Versioned, query-bound HMAC cursor. No internal database identifiers."""
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import re

from app.common.product_slugs import validate_product_slug
from app.core.config import Settings
from app.schemas.product_browse import BrowseQuery, BrowseSort


class InvalidBrowseCursor(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BrowsePosition:
    value: datetime | Decimal
    slug: str


def _base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unbase64url(value: str) -> bytes:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise InvalidBrowseCursor
    data = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if _base64url(data) != value:
        raise InvalidBrowseCursor
    return data


def query_fingerprint(query: BrowseQuery, key: bytes) -> str:
    context = {
        "q": query.q, "city": query.city, "category": query.category,
        "min_price": format(query.min_price, ".2f") if query.min_price is not None else None,
        "max_price": format(query.max_price, ".2f") if query.max_price is not None else None,
        "condition": query.condition.value if query.condition is not None else None,
        "sort": query.sort.value, "limit": query.limit,
    }
    serialized = json.dumps(context, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False).encode("utf-8")
    return hmac.new(key, b"browse-context-v1\0" + serialized, hashlib.sha256).hexdigest()


class BrowseCursorCodec:
    def __init__(self, config: Settings):
        dedicated = (config.browse_cursor_signing_key.get_secret_value().strip()
                     if config.browse_cursor_signing_key is not None else "")
        if dedicated:
            self._key = dedicated.encode("utf-8")
        else:
            # Development only; runtime configuration requires a dedicated key elsewhere.
            jwt = config.jwt_secret_key.get_secret_value().encode("utf-8")
            self._key = hmac.new(jwt, b"unishop-browse-cursor-v1", hashlib.sha256).digest()

    def encode(self, query: BrowseQuery, position: BrowsePosition) -> str:
        value = (position.value.isoformat(timespec="microseconds")
                 if isinstance(position.value, datetime) else format(position.value, ".2f"))
        payload = {"v": 1, "s": query.sort.value, "f": query_fingerprint(query, self._key),
                   "k": value, "r": position.slug}
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        signature = hmac.new(self._key, data, hashlib.sha256).digest()
        return f"{_base64url(data)}.{_base64url(signature)}"

    def decode(self, token: str, query: BrowseQuery) -> BrowsePosition:
        try:
            if not token or len(token) > 512 or token.count(".") != 1:
                raise InvalidBrowseCursor
            payload_part, signature_part = token.split(".")
            data, signature = _unbase64url(payload_part), _unbase64url(signature_part)
            expected = hmac.new(self._key, data, hashlib.sha256).digest()
            if len(signature) != 32 or not hmac.compare_digest(signature, expected):
                raise InvalidBrowseCursor

            def unique_pairs(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise InvalidBrowseCursor
                    result[key] = value
                return result

            payload = json.loads(data, object_pairs_hook=unique_pairs)
            if (not isinstance(payload, dict) or set(payload) != {"v", "s", "f", "k", "r"}
                    or type(payload["v"]) is not int or payload["v"] != 1
                    or payload["s"] != query.sort.value
                    or payload["f"] != query_fingerprint(query, self._key)
                    or not isinstance(payload["k"], str) or not isinstance(payload["r"], str)):
                raise InvalidBrowseCursor
            slug = validate_product_slug(payload["r"])
            if query.sort == BrowseSort.NEWEST:
                if len(payload["k"]) > 26:
                    raise InvalidBrowseCursor
                value = datetime.fromisoformat(payload["k"])
                if value.tzinfo is not None:
                    raise InvalidBrowseCursor
            else:
                if not re.fullmatch(r"(?:0|[1-9][0-9]{0,9})\.[0-9]{2}", payload["k"]):
                    raise InvalidBrowseCursor
                value = Decimal(payload["k"])
                if not Decimal("0") < value <= Decimal("9999999999.99"):
                    raise InvalidBrowseCursor
            return BrowsePosition(value, slug)
        except (ValueError, TypeError, OverflowError, UnicodeError, InvalidOperation,
                KeyError, binascii.Error):
            raise InvalidBrowseCursor("Invalid cursor.") from None
