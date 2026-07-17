from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

from app.common.enums import AccountStatus, UserRoleType
from app.common.validators import normalize_chinese_phone_number, validate_password_policy


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
        normalized = value.strip().lower()
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
