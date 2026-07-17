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


VerificationCodeGenerator = Callable[[], str]
