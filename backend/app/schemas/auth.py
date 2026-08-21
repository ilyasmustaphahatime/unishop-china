from datetime import datetime
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from typing import Annotated, Literal

from app.common.enums import AccountStatus, UserRoleType
from app.common.validators import (
    normalize_chinese_phone_number,
    normalize_email_address,
    validate_password_policy,
)

EMAIL_ADAPTER = TypeAdapter(EmailStr)


def normalize_account_identifier(value: object) -> object:
    """Normalize the shared email-or-mainland-phone authentication identifier."""
    if not isinstance(value, str):
        return value
    candidate = value.strip()
    if not candidate or len(candidate) > 255:
        raise ValueError("Enter a valid email address or mainland Chinese phone number.")
    if "@" in candidate:
        try:
            return str(EMAIL_ADAPTER.validate_python(normalize_email_address(candidate)))
        except (ValidationError, ValueError) as exc:
            raise ValueError(
                "Enter a valid email address or mainland Chinese phone number."
            ) from exc
    try:
        return normalize_chinese_phone_number(candidate)
    except ValueError as exc:
        raise ValueError(
            "Enter a valid email address or mainland Chinese phone number."
        ) from exc


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    phone_number: str | None = None
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = normalize_email_address(value) if value.strip() else ""
        return normalized or None

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        if not value.strip():
            return None
        return normalize_chinese_phone_number(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_policy(value)

    @model_validator(mode="after")
    def require_identifier(self) -> Self:
        if self.email is None and self.phone_number is None:
            raise ValueError("At least one email address or phone number is required.")
        return self


class RegisterResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    email: EmailStr | None
    phone_number: str | None
    phone_verified: bool
    email_verified: bool
    account_status: AccountStatus
    roles: list[UserRoleType]
    phone_verification_required: bool
    created_at: datetime


class ResendPhoneVerificationCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: str

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return normalize_chinese_phone_number(value)


class ResendPhoneVerificationCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    expires_in_seconds: int = 600


AsciiCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$", strict=True)]


class VerifyPhoneCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: str
    code: AsciiCode

    @field_validator("phone_number", mode="before")
    @classmethod
    def normalize_phone(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return normalize_chinese_phone_number(value)


class VerifyPhoneCodeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    phone_verified: bool


LoginIdentifier = Annotated[str, StringConstraints(min_length=1, max_length=255, strict=True)]
LoginPassword = Annotated[str, StringConstraints(min_length=1, max_length=128, strict=True)]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: LoginIdentifier
    password: LoginPassword

    @field_validator("identifier", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        return normalize_account_identifier(value)

    @property
    def identifier_kind(self) -> Literal["email", "phone"]:
        return "email" if "@" in self.identifier else "phone"


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: LoginIdentifier

    @field_validator("identifier", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        return normalize_account_identifier(value)

    @property
    def identifier_kind(self) -> Literal["email", "phone"]:
        return "email" if "@" in self.identifier else "phone"


class ForgotPasswordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identifier: LoginIdentifier
    code: AsciiCode
    new_password: LoginPassword

    @field_validator("identifier", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        return normalize_account_identifier(value)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        return validate_password_policy(value)

    @property
    def identifier_kind(self) -> Literal["email", "phone"]:
        return "email" if "@" in self.identifier else "phone"


class ResetPasswordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


class SafeAuthenticatedUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    email: EmailStr | None
    phone_number: str | None
    email_verified: bool
    phone_verified: bool
    account_status: AccountStatus
    roles: list[UserRoleType]
    created_at: datetime


class LoginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: SafeAuthenticatedUserResponse


class RefreshResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
