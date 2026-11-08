"""Purpose/account/filter-bound keysets using a separate signing domain."""
import base64
import binascii
from datetime import datetime
import hashlib
import hmac
import json
import re

from app.common.offers import OfferError, OfferPosition, validate_ref, unique_pairs


def encode_bytes(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def decode_bytes(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError
    data = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if encode_bytes(data) != value:
        raise ValueError
    return data


class OfferCursor:
    def __init__(self, config, actor, purpose, query):
        secret = config.browse_cursor_signing_key
        source = secret.get_secret_value().strip() if secret is not None else ""
        if len(source) < 32:
            raise OfferError("Pagination unavailable.", 503)
        self.key = hmac.new(source.encode(), b"unishop-offers-deals-v1", hashlib.sha256).digest()
        self.kind = {"offers": "of", "deals": "dl"}[purpose]
        context = json.dumps({"actor": actor, "purpose": purpose,
                              "query": query.model_dump(exclude={"cursor"})},
                             sort_keys=True, separators=(",", ":")).encode()
        self.context = hmac.new(self.key, b"context\0" + context, hashlib.sha256).hexdigest()

    def encode(self, position):
        if position.value.tzinfo is not None or position.value.year < 1000:
            raise ValueError("Expected MySQL naive UTC.")
        body = json.dumps({"v": 1, "f": self.context, "t": position.value.isoformat(timespec="microseconds"),
                           "r": validate_ref(position.reference, self.kind)}, separators=(",", ":")).encode()
        return encode_bytes(body) + "." + encode_bytes(hmac.new(self.key, b"page\0" + body, hashlib.sha256).digest())

    def decode(self, token):
        try:
            if not isinstance(token, str) or not 1 <= len(token) <= 512 or token.count(".") != 1:
                raise ValueError
            body, signature = map(decode_bytes, token.split("."))
            if not hmac.compare_digest(signature, hmac.new(self.key, b"page\0" + body, hashlib.sha256).digest()):
                raise ValueError
            data = json.loads(body, object_pairs_hook=unique_pairs)
            if (not isinstance(data, dict) or set(data) != {"v", "f", "t", "r"}
                    or type(data["v"]) is not int or data["v"] != 1
                    or not isinstance(data["f"], str) or not hmac.compare_digest(data["f"], self.context)
                    or not isinstance(data["t"], str)
                    or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}", data["t"])):
                raise ValueError
            at = datetime.fromisoformat(data["t"])
            if at.year < 1000:
                raise ValueError
            return OfferPosition(at, validate_ref(data["r"], self.kind))
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError, binascii.Error):
            raise OfferError("Invalid cursor.", 400) from None
