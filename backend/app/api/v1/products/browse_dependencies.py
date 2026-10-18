"""Bounded, explicit public browse query parsing."""
from decimal import Decimal
import re
import unicodedata
from typing import Annotated

from fastapi import HTTPException, Query, Request

from app.common.catalog_slugs import validate_catalog_slug
from app.common.plain_text import normalize_plain_text
from app.models.product import ProductCondition
from app.schemas.product_browse import BrowseQuery, BrowseSort

ALLOWED_QUERY_KEYS = frozenset({"q", "city", "category", "min_price", "max_price",
                                "condition", "sort", "limit", "cursor"})
PRICE_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,2})?\Z")
PRICE_MAX = Decimal("9999999999.99")


def normalize_search(value: str) -> str:
    text = " ".join(normalize_plain_text(value, field_name="Search", maximum=160,
                                        allow_newlines=False).split())
    if len(text) > 80 or sum(character.isalnum() for character in text) < 2:
        raise ValueError("Invalid search term.")
    words = text.split()
    if len(words) > 8 or any(sum(c.isalnum() for c in word) < 2 for word in words):
        raise ValueError("Too many search words.")
    if any(not (c.isalnum() or c.isspace() or unicodedata.category(c).startswith("M"))
           for c in text):
        raise ValueError("Unsupported search punctuation.")
    return text


def parse_price(value: str | None) -> Decimal | None:
    if value is None:
        return None
    if not PRICE_PATTERN.fullmatch(value):
        raise ValueError("Invalid price.")
    price = Decimal(value)
    if price > PRICE_MAX:
        raise ValueError("Invalid price.")
    return price


def browse_query(
    request: Request,
    q: Annotated[str | None, Query(max_length=160, description="Unicode keyword search (2–80 characters). ")] = None,
    city: Annotated[str | None, Query(max_length=63, description="Exact active city slug.")] = None,
    category: Annotated[str | None, Query(max_length=63, description="Exact active category slug.")] = None,
    min_price: Annotated[str | None, Query(max_length=13, description="Minimum CNY price, exact decimal.")] = None,
    max_price: Annotated[str | None, Query(max_length=13, description="Maximum CNY price, exact decimal.")] = None,
    condition: ProductCondition | None = None,
    sort: BrowseSort = BrowseSort.NEWEST,
    limit: Annotated[int, Query(ge=1, le=50)] = 24,
    cursor: Annotated[str | None, Query(max_length=512, description="Signed opaque continuation token.")] = None,
) -> BrowseQuery:
    names = [key for key, _ in request.query_params.multi_items()]
    if len(names) != len(set(names)) or any(key not in ALLOWED_QUERY_KEYS for key in names):
        raise HTTPException(422, "Invalid browse parameters.")
    try:
        normalized = normalize_search(q) if q is not None else None
        city_slug = validate_catalog_slug(city) if city is not None else None
        category_slug = validate_catalog_slug(category) if category is not None else None
        low, high = parse_price(min_price), parse_price(max_price)
        if low is not None and high is not None and high < low:
            raise ValueError("Invalid price range.")
    except ValueError:
        raise HTTPException(422, "Invalid browse parameters.") from None
    return BrowseQuery(q=normalized, city=city_slug, category=category_slug,
                       min_price=low, max_price=high, condition=condition,
                       sort=sort, limit=limit, cursor=cursor)
