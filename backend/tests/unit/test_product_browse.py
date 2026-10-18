"""Pure search normalization and signed-cursor adversarial tests."""
import base64
from datetime import datetime
from decimal import Decimal
import hashlib
import hmac
import json
import secrets

import pytest
from pydantic import SecretStr
from sqlalchemy.dialects import mysql

from app.api.v1.products.browse_dependencies import normalize_search, parse_price
from app.core.config import settings, validate_browse_cursor_configuration, UnsafeRuntimeConfigurationError
from app.repositories.product_browse_repository import ProductBrowseRepository
from app.schemas.product_browse import BrowseQuery, BrowseSort
from app.services.product_browse_cursor import (
    BrowseCursorCodec, BrowsePosition, InvalidBrowseCursor, query_fingerprint,
)

SLUG = "item-" + "a" * 24


@pytest.fixture
def codec():
    config = settings.model_copy(update={"browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48))})
    return BrowseCursorCodec(config)


def test_unicode_normalization_and_bounds():
    assert normalize_search("  Cafe\u0301   桌子  ") == "Café 桌子"
    assert normalize_search("مكتب جميل") == "مكتب جميل"
    for bad in ("", " ", "a", "a b", "!!!", "x" * 81, "x\x00y", "desk\u202etitle",
                "' OR 1=1 --", "desk+seller", "desk*", "café!",
                "one two three four five six seven eight nine"):
        with pytest.raises(ValueError):
            normalize_search(bad)


@pytest.mark.parametrize("payload", [
    "'", '"', "%", "_", "\\", "--", "#", ";", "OR 1=1",
    "' OR '1'='1", "/* */", "中文%' OR 1=1 --", "العربية'--",
])
def test_search_rejects_sql_metacharacters_before_query(payload):
    with pytest.raises(ValueError):
        normalize_search(payload)


def test_decimal_boundaries_are_exact():
    assert parse_price("0") == Decimal(0)
    assert parse_price("9999999999.99") == Decimal("9999999999.99")
    for bad in ("-1", "NaN", "Infinity", "1e3", ".5", "1.001", "10000000000", "+1", "01"):
        with pytest.raises(ValueError):
            parse_price(bad)


@pytest.mark.parametrize("sort,value", [
    (BrowseSort.NEWEST, datetime(2026, 1, 2, 3, 4, 5, 123456)),
    (BrowseSort.PRICE_ASC, Decimal("0.01")),
    (BrowseSort.PRICE_DESC, Decimal("9999999999.99")),
])
def test_cursor_round_trip_and_cross_instance(codec, sort, value):
    query = BrowseQuery(q="桌子", city="qingdao", category="furniture",
                        condition=None, sort=sort, limit=7)
    token = codec.encode(query, BrowsePosition(value, SLUG))
    assert len(token) <= 512 and SLUG not in token
    assert codec.decode(token, query) == BrowsePosition(value, SLUG)
    other = BrowseCursorCodec(settings.model_copy(update={
        "browse_cursor_signing_key": SecretStr(codec._key.decode("utf-8")),
    }))
    assert other.decode(token, query) == BrowsePosition(value, SLUG)
    rotated = BrowseCursorCodec(settings.model_copy(update={
        "browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48)),
    }))
    with pytest.raises(InvalidBrowseCursor):
        rotated.decode(token, query)
    for changed in (BrowseQuery(q="other", city="qingdao", category="furniture", sort=sort, limit=7),
                    BrowseQuery(q="桌子", city="beijing", category="furniture", sort=sort, limit=7),
                    BrowseQuery(q="桌子", city="qingdao", category="other", sort=sort, limit=7),
                    BrowseQuery(q="桌子", city="qingdao", category="furniture", sort=sort, limit=8),
                    BrowseQuery(q="桌子", city="qingdao", category="furniture",
                                sort=BrowseSort.PRICE_ASC if sort == BrowseSort.NEWEST else BrowseSort.NEWEST,
                                limit=7)):
        with pytest.raises(InvalidBrowseCursor):
            codec.decode(token, changed)


def test_cursor_rejects_tampering_and_bad_encodings(codec):
    query = BrowseQuery()
    token = codec.encode(query, BrowsePosition(datetime(2026, 1, 1), SLUG))
    for bad in ("", "a", "a.b", token[:10], token[:-1], token + "x", "!" + token[1:],
                token.replace(".", ".."), "a" * 513, "💥"):
        with pytest.raises(InvalidBrowseCursor):
            codec.decode(bad, query)


def test_signed_but_invalid_payloads_are_rejected(codec):
    query = BrowseQuery()
    base = {"v": 1, "s": "newest", "f": query_fingerprint(query, codec._key),
            "k": "2026-01-01T00:00:00.000000", "r": SLUG}
    variants = [dict(base, v=2), dict(base, s="not-a-sort"),
                dict(base, k="not-a-time"), dict(base, r="item-invalid"),
                dict(base, f="0" * 64), dict(base, extra="x")]
    for payload in variants:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
        sig = hmac.new(codec._key, data, hashlib.sha256).digest()
        token = (base64.urlsafe_b64encode(data).rstrip(b"=").decode() + "." +
                 base64.urlsafe_b64encode(sig).rstrip(b"=").decode())
        with pytest.raises(InvalidBrowseCursor):
            codec.decode(token, query)


def test_bounded_random_cursor_fuzz_never_crashes(codec):
    query = BrowseQuery()
    for _ in range(300):
        token = secrets.token_urlsafe(secrets.randbelow(100))
        with pytest.raises(InvalidBrowseCursor):
            codec.decode(token, query)


def test_production_requires_dedicated_distinct_cursor_secret():
    for value in (None, SecretStr("short"), settings.jwt_secret_key):
        with pytest.raises(UnsafeRuntimeConfigurationError) as caught:
            validate_browse_cursor_configuration(settings.model_copy(update={
                "app_env": "production", "browse_cursor_signing_key": value,
            }))
        assert caught.value.unsafe_variables == ("BROWSE_CURSOR_SIGNING_KEY",)
    validate_browse_cursor_configuration(settings.model_copy(update={
        "app_env": "production", "browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48)),
    }))


@pytest.mark.parametrize("sort,index", [
    (BrowseSort.NEWEST, "ix_product_listings_browse_newest"),
    (BrowseSort.PRICE_ASC, "ix_product_listings_browse_price"),
    (BrowseSort.PRICE_DESC, "ix_product_listings_browse_price"),
])
def test_repository_sql_is_bounded_parameterized_and_uses_allowlisted_index(sort, index):
    query = BrowseQuery(q="桌子", city="qingdao", category="furniture", min_price=Decimal("10.00"),
                        sort=sort, limit=24)
    value = datetime(2026, 1, 1) if sort == BrowseSort.NEWEST else Decimal("10.00")
    stmt = ProductBrowseRepository().page_statement(query, BrowsePosition(value, SLUG))
    compiled = stmt.compile(dialect=mysql.dialect())
    sql = compiled.string
    assert "LIMIT" in sql and "OFFSET" not in sql
    assert "MATCH" in sql and "IN BOOLEAN MODE" in sql
    assert "FORCE INDEX (ix_product_listings_search_ngram)" in sql
    assert "password_hash" not in sql and "storage_key" not in sql
    assert "桌子" not in sql and "qingdao" not in sql
    assert "+桌子" in compiled.params.values()
    no_search = ProductBrowseRepository().page_statement(BrowseQuery(sort=sort), None)
    assert f"FORCE INDEX ({index})" in no_search.compile(dialect=mysql.dialect()).string
    suffix = "newest" if sort == BrowseSort.NEWEST else "price"
    for filter_name in ("city", "category"):
        filtered = BrowseQuery(**{filter_name: "qingdao", "sort": sort})
        compiled_filter = ProductBrowseRepository().page_statement(filtered, None).compile(
            dialect=mysql.dialect())
        assert f"FORCE INDEX (ix_product_listings_{filter_name}_{suffix})" in compiled_filter.string
        assert "qingdao" not in compiled_filter.string
