"""Private, bounded personal-product-list contracts."""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import Field, field_validator

from app.common.product_slugs import ProductSlug
from app.schemas.catalog import StrictBody
from app.schemas.product_browse import ProductCard


class PersonalListKind(StrEnum):
    FAVORITES = "favorites"
    RECENTLY_VIEWED = "recently-viewed"


@dataclass(frozen=True, slots=True)
class PersonalListQuery:
    limit: int = 24
    cursor: str | None = None


class FavoriteLookupRequest(StrictBody):
    product_slugs: list[ProductSlug] = Field(min_length=1, max_length=50, strict=True)

    @field_validator("product_slugs")
    @classmethod
    def unique_slugs(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate listing references are not permitted.")
        return value


class FavoriteStatus(StrictBody):
    favorited: bool


class FavoritesLookupResponse(StrictBody):
    favorites: dict[str, bool]


def utc_timestamp(value: datetime) -> datetime:
    """MySQL DATETIME stores UTC without an offset; API timestamps are explicit."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class FavoriteItem(StrictBody):
    product: ProductCard
    favorited_at: datetime

    _utc = field_validator("favorited_at")(utc_timestamp)


class RecentlyViewedItem(StrictBody):
    product: ProductCard
    last_viewed_at: datetime

    _utc = field_validator("last_viewed_at")(utc_timestamp)


class FavoritesPage(StrictBody):
    items: list[FavoriteItem] = Field(max_length=50)
    next_cursor: str | None
    has_more: bool


class RecentlyViewedPage(StrictBody):
    items: list[RecentlyViewedItem] = Field(max_length=50)
    next_cursor: str | None
    has_more: bool
