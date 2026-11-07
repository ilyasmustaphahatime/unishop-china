"""Authenticated, conversation-bound contact encryption; never logs private values."""
import base64
import binascii
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.common.chat import ChatError, validate_conversation_ref
from app.common.wechat import validate_wechat_contact
from app.core.config import Settings, settings


class WeChatCipher:
    def __init__(self, config: Settings = settings):
        self._key = config.wechat_contact_encryption_key
        self._other_keys = (config.jwt_secret_key, config.browse_cursor_signing_key)

    def _cipher(self) -> AESGCM:
        try:
            value = self._key.get_secret_value() if self._key else ""
            if len(value) != 44 or any(
                other and secrets.compare_digest(value, other.get_secret_value())
                for other in self._other_keys
            ):
                raise ValueError
            key = base64.b64decode(value, altchars=b"-_", validate=True)
            if len(key) != 32 or base64.urlsafe_b64encode(key).decode("ascii") != value:
                raise ValueError
            return AESGCM(key)
        except (ValueError, TypeError, binascii.Error):
            raise ChatError("Contact sharing is unavailable.", 503, "handoff_unavailable") from None

    @staticmethod
    def _aad(conversation_ref: str) -> bytes:
        validate_conversation_ref(conversation_ref)
        return ("unishop:wechat:v1:" + conversation_ref).encode("ascii")

    def encrypt(self, contact: str, conversation_ref: str) -> str:
        try:
            validate_wechat_contact(contact)
        except ValueError:
            raise ChatError("Invalid contact value.", 422, "invalid_contact") from None
        nonce = secrets.token_bytes(12)
        ciphertext = self._cipher().encrypt(nonce, contact.encode("utf-8"), self._aad(conversation_ref))
        return "v1." + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, ciphertext: str, conversation_ref: str) -> str:
        cipher = self._cipher()
        try:
            if not isinstance(ciphertext, str) or not ciphertext.startswith("v1.") or len(ciphertext) > 128:
                raise ValueError
            encoded = ciphertext[3:]
            payload = base64.b64decode(encoded, altchars=b"-_", validate=True)
            if (len(payload) < 34
                    or base64.urlsafe_b64encode(payload).decode("ascii") != encoded):
                raise ValueError
            contact = cipher.decrypt(payload[:12], payload[12:], self._aad(conversation_ref)).decode("utf-8")
            return validate_wechat_contact(contact)
        except (ValueError, TypeError, UnicodeError, InvalidTag, binascii.Error):
            raise ChatError("Contact sharing is unavailable.", 503, "handoff_unavailable") from None
