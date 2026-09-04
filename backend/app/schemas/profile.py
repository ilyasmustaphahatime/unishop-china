from datetime import datetime
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

SupportedCity = Literal[
    "Qingdao",
    "Beijing",
    "Shanghai",
    "Shenzhen",
    "Guangzhou",
    "Hangzhou",
]

DIRECTION_CONTROL_CHARACTERS = {
    "\u202a",
    "\u202b",
    "\u202c",
    "\u202d",
    "\u202e",
    "\u2066",
    "\u2067",
    "\u2068",
    "\u2069",
}


def _normalize_plain_text(
    value: str,
    *,
    field_name: str,
    maximum: int,
    allow_newlines: bool,
) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if len(normalized) > maximum:
        raise ValueError(f"{field_name} is too long.")
    for character in normalized:
        category = unicodedata.category(character)
        if category == "Cs" or (
            category == "Cc" and not (allow_newlines and character in {"\n", "\t"})
        ):
            raise ValueError(f"{field_name} contains unsupported control characters.")
        if character in DIRECTION_CONTROL_CHARACTERS:
            raise ValueError(f"{field_name} contains unsupported direction controls.")
    return normalized


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    bio: str | None = None
    city: SupportedCity | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_plain_text(
            value,
            field_name="Display name",
            maximum=50,
            allow_newlines=False,
        )
        if len(normalized) < 2:
            raise ValueError("Display name must contain at least 2 characters.")
        return normalized

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_plain_text(
            value,
            field_name="Bio",
            maximum=300,
            allow_newlines=True,
        )
        return normalized or None


class OnboardingCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str
    display_name: str | None
    bio: str | None
    city: SupportedCity | None
    onboarding_completed: bool
    member_since: datetime
    created_at: datetime
    updated_at: datetime
    email_verified: bool
    phone_verified: bool


class PublicProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: str
    display_name: str
    bio: str | None
    city: SupportedCity
    member_since: datetime
    email_verified: bool
    phone_verified: bool
