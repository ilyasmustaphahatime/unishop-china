from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
from uuid import UUID

import jwt
from jwt import InvalidTokenError

from app.common.datetime_utils import as_utc
from app.core.config import Settings, settings, validate_authentication_configuration
from app.core.exceptions import TokenValidationError
from app.models.base import utc_now


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    subject: str
    token_id: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime


class AccessTokenService:
    """Create and validate short-lived Phase 4A access tokens."""

    def __init__(
        self,
        config: Settings = settings,
        *,
        now_provider: Callable[[], datetime] = utc_now,
        token_id_provider: Callable[[], str] | None = None,
    ) -> None:
        validate_authentication_configuration(config)
        assert config.jwt_secret_key is not None
        self._secret = config.jwt_secret_key.get_secret_value()
        self._algorithm = config.jwt_algorithm.strip().upper()
        self._issuer = config.jwt_issuer.strip()
        self._audience = config.jwt_audience.strip()
        self._lifetime = timedelta(minutes=config.access_token_expire_minutes)
        self._clock_skew_seconds = config.jwt_clock_skew_seconds
        self._now_provider = now_provider
        self._token_id_provider = token_id_provider or (lambda: secrets.token_urlsafe(32))

    @property
    def expires_in_seconds(self) -> int:
        return int(self._lifetime.total_seconds())

    def create_access_token(self, user_id: str) -> str:
        subject = self._validate_subject(user_id)
        issued_at = as_utc(self._now_provider())
        expires_at = issued_at + self._lifetime
        claims = {
            "sub": subject,
            "type": "access",
            "jti": self._token_id_provider(),
            "iss": self._issuer,
            "aud": self._audience,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
        }
        return jwt.encode(claims, self._secret, algorithm=self._algorithm)

    def decode_access_token(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._clock_skew_seconds,
                options={
                    "require": ["sub", "type", "jti", "iss", "aud", "iat", "nbf", "exp"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_iss": True,
                    "verify_aud": True,
                },
            )
            if payload.get("type") != "access":
                raise TokenValidationError
            subject = self._validate_subject(payload.get("sub"))
            token_id = payload.get("jti")
            if not isinstance(token_id, str) or not token_id:
                raise TokenValidationError
            return AccessTokenClaims(
                subject=subject,
                token_id=token_id,
                issued_at=self._timestamp(payload.get("iat")),
                not_before=self._timestamp(payload.get("nbf")),
                expires_at=self._timestamp(payload.get("exp")),
            )
        except TokenValidationError:
            raise
        except (InvalidTokenError, TypeError, ValueError, OverflowError) as exc:
            raise TokenValidationError from exc

    @staticmethod
    def _validate_subject(value: object) -> str:
        if not isinstance(value, str):
            raise TokenValidationError
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError) as exc:
            raise TokenValidationError from exc
        canonical = str(parsed)
        if value != canonical:
            raise TokenValidationError
        return canonical

    @staticmethod
    def _timestamp(value: object) -> datetime:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TokenValidationError
        return datetime.fromtimestamp(value, tz=timezone.utc)
