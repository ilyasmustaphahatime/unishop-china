"""Private cursor cryptography, strict schemas and bounded SQL composition."""
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.dialects import mysql

from app.core.config import settings
from app.repositories.favorites_repository import FavoritesRepository
from app.repositories.recently_viewed_repository import RecentlyViewedRepository
from app.schemas.product_browse import BrowseQuery
from app.schemas.product_personalization import (
    FavoriteLookupRequest, PersonalListKind, PersonalListQuery,
)
from app.services.personalization_cursor import (
    InvalidPersonalizationCursor, PersonalizationCursorCodec, PersonalizationPosition,
)
from app.services.product_browse_cursor import BrowseCursorCodec, BrowsePosition

USER = str(uuid4())
SLUG = "item-" + "a" * 24
POSITION = PersonalizationPosition(datetime(2026, 10, 18, 1, 2, 3, 456789), SLUG)


@pytest.fixture
def cursor_config():
    return settings.model_copy(update={"browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48))})


@pytest.fixture
def codec(cursor_config):
    return PersonalizationCursorCodec(cursor_config)


def base64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def sign_payload(codec, payload):
    data = payload if isinstance(payload, bytes) else json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    signature = hmac.new(codec._key, b"personal-page-v1\0" + data, hashlib.sha256).digest()
    return base64url(data) + "." + base64url(signature)


@pytest.mark.parametrize("kind", list(PersonalListKind))
@pytest.mark.parametrize("limit", [1, 24, 50])
def test_private_cursor_round_trip_and_cross_instance_stability(codec, cursor_config, kind, limit):
    token = codec.encode(USER, kind, limit, POSITION)
    assert len(token) <= 512
    assert codec.decode(token, USER, kind, limit) == POSITION
    assert PersonalizationCursorCodec(cursor_config).decode(token, USER, kind, limit) == POSITION
    payload = base64.urlsafe_b64decode(token.split(".")[0] + "==").decode("ascii")
    assert USER not in payload
    assert "user_id" not in payload and "product_listing_id" not in payload
    assert USER not in token and cursor_config.browse_cursor_signing_key.get_secret_value() not in token
    assert codec.encode(USER, kind, limit, POSITION) == token


def test_cursor_binds_to_user_kind_limit_and_rotated_key(codec, cursor_config):
    token = codec.encode(USER, PersonalListKind.FAVORITES, 24, POSITION)
    for user, kind, limit in ((str(uuid4()), PersonalListKind.FAVORITES, 24),
        (USER, PersonalListKind.RECENTLY_VIEWED, 24), (USER, PersonalListKind.FAVORITES, 1)):
        with pytest.raises(InvalidPersonalizationCursor, match="^Invalid cursor\\.$"):
            codec.decode(token, user, kind, limit)
    rotated = PersonalizationCursorCodec(cursor_config.model_copy(update={
        "browse_cursor_signing_key": SecretStr(secrets.token_urlsafe(48))}))
    with pytest.raises(InvalidPersonalizationCursor):
        rotated.decode(token, USER, PersonalListKind.FAVORITES, 24)


def test_private_and_public_browse_cursor_keys_are_domain_separated(codec, cursor_config):
    browse = BrowseCursorCodec(cursor_config)
    query = BrowseQuery(limit=24)
    public_token = browse.encode(query, BrowsePosition(POSITION.value, SLUG))
    with pytest.raises(InvalidPersonalizationCursor):
        codec.decode(public_token, USER, PersonalListKind.FAVORITES, 24)
    private_token = codec.encode(USER, PersonalListKind.FAVORITES, 24, POSITION)
    # Even possession of a valid public token cannot re-sign a personal cursor.
    body = base64.urlsafe_b64decode(private_token.split(".")[0] + "==")
    public_signature = hmac.new(browse._key, body, hashlib.sha256).digest()
    with pytest.raises(InvalidPersonalizationCursor):
        codec.decode(base64url(body) + "." + base64url(public_signature),
            USER, PersonalListKind.FAVORITES, 24)


def test_cursor_rejects_truncation_tampering_oversize_and_noncanonical_base64(codec):
    token = codec.encode(USER, PersonalListKind.FAVORITES, 24, POSITION)
    invalid = ("", "a", "a.b", token[:20], token[:-1], token + "a", "!" + token[1:],
        token.replace(".", ".."), "x" * 513, "💥", token + "=", token + "\n")
    for value in invalid:
        with pytest.raises(InvalidPersonalizationCursor, match="^Invalid cursor\\.$"):
            codec.decode(value, USER, PersonalListKind.FAVORITES, 24)


@pytest.mark.parametrize("field,value", [
    ("v", 2), ("v", True), ("v", "1"), ("f", "0" * 64), ("f", 1),
    ("k", "2026-10-18"), ("k", "2026-10-18T01:02:03.000000Z"),
    ("k", "2026-99-18T01:02:03.000000"), ("k", "0001-01-01T01:02:03.000000"),
    ("k", None), ("r", "invalid-slug"), ("r", None), ("r", 1),
])
def test_signed_but_invalid_payloads_fail_closed(codec, field, value):
    payload = {"v": 1, "f": codec._context(USER, PersonalListKind.FAVORITES, 24),
        "k": POSITION.value.isoformat(timespec="microseconds"), "r": SLUG}
    payload[field] = value
    with pytest.raises(InvalidPersonalizationCursor):
        codec.decode(sign_payload(codec, payload), USER, PersonalListKind.FAVORITES, 24)


def test_signed_extra_missing_and_duplicate_payload_fields_rejected(codec):
    payload = {"v": 1, "f": codec._context(USER, PersonalListKind.FAVORITES, 24),
        "k": POSITION.value.isoformat(timespec="microseconds"), "r": SLUG}
    for altered in (dict(payload, user_id=USER), {k: v for k, v in payload.items() if k != "r"},
                    b'{"v":1,"v":1}', b'\xff\xfe', [], None):
        with pytest.raises(InvalidPersonalizationCursor):
            codec.decode(sign_payload(codec, altered), USER, PersonalListKind.FAVORITES, 24)


def test_cursor_random_fuzz_has_one_safe_error(codec):
    for _ in range(150):
        token = secrets.token_urlsafe(secrets.randbelow(100) + 1)
        with pytest.raises(InvalidPersonalizationCursor, match="^Invalid cursor\\.$"):
            codec.decode(token, USER, PersonalListKind.FAVORITES, 24)


def test_cursor_encode_rejects_aware_positions(codec):
    aware = PersonalizationPosition(POSITION.value.replace(tzinfo=timezone.utc), SLUG)
    with pytest.raises(ValueError):
        codec.encode(USER, PersonalListKind.FAVORITES, 24, aware)


@pytest.mark.parametrize("payload", [
    {}, {"product_slugs": []}, {"product_slugs": [SLUG, SLUG]},
    {"product_slugs": ["not-a-product"]}, {"product_slugs": [True]},
    {"product_slugs": [123]}, {"product_slugs": SLUG},
    {"product_slugs": (SLUG,)}, {"product_slugs": [SLUG], "user_id": USER},
    {"product_slugs": ["item-" + f"{index:024x}" for index in range(51)]},
])
def test_lookup_schema_rejects_unbounded_or_coerced_input(payload):
    with pytest.raises(ValidationError):
        FavoriteLookupRequest.model_validate(payload)


def test_lookup_schema_accepts_bounded_distinct_slugs_and_default_query():
    references = ["item-" + f"{index:024x}" for index in range(50)]
    assert FavoriteLookupRequest(product_slugs=references).product_slugs == references
    assert PersonalListQuery().limit == 24 and PersonalListQuery().cursor is None


@pytest.mark.parametrize("repository,table,time_column", [
    (FavoritesRepository(), "product_favorites", "favorited_at"),
    (RecentlyViewedRepository(), "product_recent_views", "last_viewed_at"),
])
def test_private_page_sql_scoped_parameterized_bounded_and_visibility_filtered(repository, table, time_column):
    statement = repository.page_statement(USER, 24, POSITION)
    compiled = statement.compile(dialect=mysql.dialect())
    sql = compiled.string
    assert table in sql and f"{table}.user_id =" in sql
    assert time_column in sql and "LIMIT" in sql and "OFFSET" not in sql
    assert "count(" not in sql.lower()
    assert "password_hash" not in sql and "storage_key" not in sql
    assert "seller_verifications" in sql and "is_active" in sql
    assert USER not in sql and SLUG not in sql
    assert USER in compiled.params.values() and SLUG in compiled.params.values()
    assert 25 in compiled.params.values()
