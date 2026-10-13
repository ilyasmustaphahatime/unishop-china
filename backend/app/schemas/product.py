"""Strict editable contracts; explicit independent owner/public projections."""
from datetime import datetime
from decimal import Decimal
import re
from typing import Annotated, Literal
from pydantic import AfterValidator, Field, model_validator
from app.common.catalog_slugs import CatalogSlug
from app.common.plain_text import normalize_plain_text
from app.common.product_slugs import ProductSlug
from app.models.product import ProductCondition, ProductStatus
from app.schemas.catalog import PublicCategory, PublicCity, StrictBody
from app.schemas.product_image import PublicProductImage


def title_text(value: str) -> str:
    value = normalize_plain_text(value, field_name="Title", maximum=120, allow_newlines=False)
    value = " ".join(value.split())
    if len(value) < 3:
        raise ValueError("Title is too short.")
    return value


def description_text(value: str) -> str:
    value = normalize_plain_text(value.replace("\r\n", "\n"), field_name="Description", maximum=5000, allow_newlines=True)
    if len(value) < 10:
        raise ValueError("Description is too short.")
    return value


def price_text(value: str) -> str:
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?", value) or Decimal(value) <= 0:
        raise ValueError("Use a positive decimal price with at most two decimal places.")
    return format(Decimal(value), ".2f")


Title = Annotated[str, Field(strict=True, max_length=120), AfterValidator(title_text)]
Description = Annotated[str, Field(strict=True, max_length=10000), AfterValidator(description_text)]
Price = Annotated[str, Field(strict=True, max_length=13), AfterValidator(price_text)]


class ProductCreate(StrictBody):
    title: Title
    description: Description
    price: Price
    condition: ProductCondition
    city_slug: CatalogSlug
    category_slug: CatalogSlug


class ProductUpdate(StrictBody):
    title: Title | None = None
    description: Description | None = None
    price: Price | None = None
    condition: ProductCondition | None = None
    city_slug: CatalogSlug | None = None
    category_slug: CatalogSlug | None = None

    @model_validator(mode="after")
    def explicit_changes(self):
        if not self.model_fields_set or any(getattr(self, f) is None for f in self.model_fields_set):
            raise ValueError("At least one non-null editable field is required.")
        return self


class ProductFields(StrictBody):
    public_slug: ProductSlug
    title: str
    description: str
    price: str
    currency: Literal["CNY"]
    condition: ProductCondition
    city: PublicCity
    category: PublicCategory
    published_at: datetime | None


class OwnProduct(ProductFields):
    status: ProductStatus
    city_active: bool
    category_active: bool
    created_at: datetime
    updated_at: datetime


class PublicSeller(StrictBody):
    public_handle: str
    display_name: str
    seller_verified: Literal[True]


class PublicProduct(ProductFields):
    status: Literal["PUBLISHED"]
    seller: PublicSeller
    images: list[PublicProductImage] = Field(default_factory=list, max_length=8)


class OwnProductList(StrictBody):
    items: list[OwnProduct]
    next_offset: int | None
