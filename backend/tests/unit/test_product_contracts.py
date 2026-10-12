from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.common.product_slugs import generate_product_slug, validate_product_slug
from app.schemas.product import ProductCreate, ProductUpdate, price_text
from app.core.http_input import bounded_json_body
import asyncio


@pytest.mark.parametrize("value", ["0.01", "123", "123.4", "123.45", "9999999999.99"])
def test_price_is_exact_decimal_string(value):
    assert Decimal(price_text(value)) == Decimal(value)


@pytest.mark.parametrize("value", ["", "../item", "item-A" + "a" * 23, "item-" + "a" * 23,
                                   "item-" + "a" * 25, "item-" + "a" * 24 + "?token=x"])
def test_slug_validation(value):
    with pytest.raises(ValueError):
        validate_product_slug(value)


def test_random_slug_generation_opaque_unique_and_valid():
    slugs = {generate_product_slug() for _ in range(500)}
    assert len(slugs) == 500 and all(validate_product_slug(s) == s for s in slugs)


def test_schema_has_only_explicit_writable_fields():
    allowed = {"title", "description", "price", "condition", "city_slug", "category_slug"}
    assert set(ProductCreate.model_fields) == set(ProductUpdate.model_fields) == allowed
    with pytest.raises(ValidationError):
        ProductUpdate(status="PUBLISHED")


def test_input_timeout_and_disconnect_fail_closed():
    async def pending():
        await asyncio.Event().wait()
    async def disconnected():
        return {"type": "http.disconnect"}
    with pytest.raises(TimeoutError):
        asyncio.run(bounded_json_body(pending, maximum_bytes=10, timeout_seconds=0))
    with pytest.raises(ConnectionError):
        asyncio.run(bounded_json_body(disconnected, maximum_bytes=10))
