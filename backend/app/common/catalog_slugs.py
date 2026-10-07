"""Public catalog names identify resources; they never confer authorization."""
import re
from typing import Annotated

from pydantic import AfterValidator, Field

from app.common.public_handles import RESERVED_PUBLIC_HANDLES

CATALOG_SLUG_PATTERN = r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
RESERVED_CATALOG_SLUGS = RESERVED_PUBLIC_HANDLES | {"city", "category"}


def validate_catalog_slug(value: str) -> str:
    if (not isinstance(value, str) or not 2 <= len(value) <= 63
            or not value.isascii() or re.fullmatch(CATALOG_SLUG_PATTERN, value) is None
            or value in RESERVED_CATALOG_SLUGS):
        raise ValueError("Invalid catalog slug.")
    return value


CatalogSlug = Annotated[str, Field(strict=True, min_length=2, max_length=63,
                                   pattern=CATALOG_SLUG_PATTERN), AfterValidator(validate_catalog_slug)]
