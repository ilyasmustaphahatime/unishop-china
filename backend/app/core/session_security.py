import hashlib
import hmac
import secrets

from app.core.config import Settings, allowed_frontend_origins, settings
from app.core.exceptions import RequestVerificationError


def generate_refresh_token() -> str:
    """Return an opaque token with 512 bits of pre-encoding entropy."""
    return secrets.token_urlsafe(64)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def hash_csrf_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def validate_csrf_tokens(
    *,
    cookie_token: str | None,
    header_token: str | None,
    stored_hash: str | None = None,
) -> None:
    if not cookie_token or not header_token:
        raise RequestVerificationError
    if not hmac.compare_digest(cookie_token, header_token):
        raise RequestVerificationError
    if stored_hash is not None and not hmac.compare_digest(
        hash_csrf_token(header_token), stored_hash
    ):
        raise RequestVerificationError


def validate_request_origin(origin: str | None, config: Settings = settings) -> None:
    """Allow non-browser clients without Origin and exact configured browser origins."""
    if origin is None:
        return
    if origin.rstrip("/") not in allowed_frontend_origins(config):
        raise RequestVerificationError
