"""Small anonymous listing-card contract; no owner or storage fields."""
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import Field

from app.models.product import ProductCondition
from app.schemas.catalog import PublicCategory, PublicCity, StrictBody
from app.schemas.product import PublicSeller


class BrowseSort(StrEnum):
    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"


@dataclass(frozen=True, slots=True)
class BrowseQuery:
    q: str | None = None
    city: str | None = None
    category: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    condition: ProductCondition | None = None
    sort: BrowseSort = BrowseSort.NEWEST
    limit: int = 24
    cursor: str | None = None


class ProductCover(StrictBody):
    ref: str
    url: str


class ProductCard(StrictBody):
    public_slug: str
    title: str
    price: str
    currency: str
    condition: ProductCondition
    city: PublicCity
    category: PublicCategory
    cover_image: ProductCover | None
    seller: PublicSeller
    published_at: str


class ProductBrowsePage(StrictBody):
    items: list[ProductCard] = Field(max_length=50)
    next_cursor: str | None
    has_more: bool
