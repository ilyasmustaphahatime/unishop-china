import hashlib
import hmac
import secrets
from collections.abc import Callable

from pwdlib import PasswordHash
from pydantic import SecretStr

from app.core.exceptions import VerificationCodeConfigurationError

password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password, password_hash)
    except Exception:
        return False


def hash_rate_limit_identifier(identifier: str, secret: SecretStr | str) -> str:
    """Return a non-reversible, secret-keyed identifier limiter key."""
    return hash_rate_limit_value(identifier, secret, namespace="login:identifier")


def hash_rate_limit_value(
    value: str,
    secret: SecretStr | str,
    *,
    namespace: str,
) -> str:
    """Return a bounded-store key without retaining attacker-controlled secret material."""
    key = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    if not key:
        raise ValueError("A rate-limit hashing secret is required.")
    digest = hmac.new(
        key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{namespace}:{digest}"


def generate_verification_code(
    randbelow: Callable[[int], int] | None = None,
) -> str:
    secure_randbelow = randbelow or secrets.randbelow
    return f"{secure_randbelow(1_000_000):06d}"


def resolve_verification_code_secret(secret: SecretStr | str | None) -> str:
    value = secret.get_secret_value() if isinstance(secret, SecretStr) else secret
    normalized = (value or "").strip()
    placeholder_markers = ("replace_with", "change_me", "local_secret", "your_secret")
    if not normalized or any(marker in normalized.lower() for marker in placeholder_markers):
        raise VerificationCodeConfigurationError(
            "VERIFICATION_CODE_HASH_SECRET must be configured with a non-placeholder value."
        )
    return normalized


def hash_verification_code(code: str, secret: SecretStr | str) -> str:
    key = resolve_verification_code_secret(secret).encode("utf-8")
    return hmac.new(key, code.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_verification_code(code: str, code_hash: str, secret: SecretStr | str) -> bool:
    candidate_hash = hash_verification_code(code, secret)
    return hmac.compare_digest(candidate_hash, code_hash)


def hash_password_reset_code(code: str, secret: SecretStr | str) -> str:
    """Hash a reset code in a domain isolated from phone-verification codes."""
    key = resolve_verification_code_secret(secret).encode("utf-8")
    payload = b"unishop-china:password-reset:v1\x00" + code.encode("ascii")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_password_reset_code(
    code: str,
    code_hash: str,
    secret: SecretStr | str,
) -> bool:
    candidate_hash = hash_password_reset_code(code, secret)
    return hmac.compare_digest(candidate_hash, code_hash)


def hash_email_verification_code(code: str, secret: SecretStr | str) -> str:
    """Hash an email code in a purpose isolated from every other challenge."""
    key = resolve_verification_code_secret(secret).encode("utf-8")
    payload = b"unishop-china:email-verification:v1\x00" + code.encode("ascii")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_email_verification_code(
    code: str,
    code_hash: str,
    secret: SecretStr | str,
) -> bool:
    candidate_hash = hash_email_verification_code(code, secret)
    return hmac.compare_digest(candidate_hash, code_hash)


VerificationCodeGenerator = Callable[[], str]
