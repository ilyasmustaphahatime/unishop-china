from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.common.catalog_slugs import CatalogSlug
from app.common.plain_text import normalize_plain_text

class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = None
    bio: str | None = None
    city: CatalogSlug | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_plain_text(
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
        normalized = normalize_plain_text(
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

    public_handle: str
    display_name: str | None
    bio: str | None
    city: str | None
    city_slug: str | None
    city_active: bool
    onboarding_completed: bool
    member_since: datetime
    created_at: datetime
    updated_at: datetime
    email_verified: bool
    phone_verified: bool


class PublicProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_handle: str
    display_name: str
    bio: str | None
    city: str
    member_since: datetime
    email_verified: bool
    phone_verified: bool
    seller_verified: bool
