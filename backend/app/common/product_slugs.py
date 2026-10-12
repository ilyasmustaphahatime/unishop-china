"""Opaque, immutable listing references; titles never enter URLs."""
import re
import secrets
from typing import Annotated
from pydantic import Field

PRODUCT_SLUG_PATTERN = r"^item-[0-9a-f]{24}$"
ProductSlug = Annotated[str, Field(strict=True, pattern=PRODUCT_SLUG_PATTERN, max_length=29)]


def generate_product_slug() -> str:
    return "item-" + secrets.token_hex(12)


def validate_product_slug(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(PRODUCT_SLUG_PATTERN, value):
        raise ValueError("Invalid listing reference.")
    return value
