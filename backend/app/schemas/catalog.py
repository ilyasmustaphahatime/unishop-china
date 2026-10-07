from typing import Annotated, Literal
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator

from app.common.catalog_slugs import CatalogSlug
from app.common.plain_text import normalize_plain_text


def catalog_text(value: str) -> str:
    value = normalize_plain_text(value, field_name="Text", maximum=500, allow_newlines=False)
    if not value or any(unicodedata.category(c) == "Cf" for c in value):
        raise ValueError("Invalid catalog text.")
    return value


Name = Annotated[str, Field(strict=True, min_length=1, max_length=80), AfterValidator(catalog_text)]
Description = Annotated[str, Field(strict=True, min_length=1, max_length=500), AfterValidator(catalog_text)]
SortOrder = Annotated[int, Field(strict=True, ge=0, le=10000)]


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CityCreate(StrictBody):
    slug: CatalogSlug
    name_en: Name
    name_zh: Name
    province_en: Name
    province_zh: Name | None = None
    country_code: Literal["CN"] = "CN"
    sort_order: SortOrder = 0


class MetadataPatch(StrictBody):
    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        for field in self.model_fields_set - {"province_zh", "description", "parent_slug"}:
            if getattr(self, field) is None:
                raise ValueError("This field cannot be null.")
        return self


class CityUpdate(MetadataPatch):
    name_en: Name | None = None
    name_zh: Name | None = None
    province_en: Name | None = None
    province_zh: Name | None = None
    sort_order: SortOrder | None = None


class CategoryCreate(StrictBody):
    slug: CatalogSlug
    name_en: Name
    name_zh: Name
    description: Description | None = None
    parent_slug: CatalogSlug | None = None
    sort_order: SortOrder = 0


class CategoryUpdate(MetadataPatch):
    name_en: Name | None = None
    name_zh: Name | None = None
    description: Description | None = None
    parent_slug: CatalogSlug | None = None
    sort_order: SortOrder | None = None


class PublicCity(StrictBody):
    slug: str
    name_en: str
    name_zh: str
    province_en: str
    province_zh: str | None
    country_code: Literal["CN"]


class AdminCity(PublicCity):
    is_active: bool
    sort_order: int


class PublicCategory(StrictBody):
    slug: str
    name_en: str
    name_zh: str
    description: str | None
    parent_slug: str | None


class CategoryTree(PublicCategory):
    children: list[PublicCategory]


class AdminCategory(PublicCategory):
    is_active: bool
    sort_order: int


class CityList(StrictBody):
    items: list[PublicCity]


class CategoryList(StrictBody):
    items: list[CategoryTree]
