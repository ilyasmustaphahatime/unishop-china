"""Real-MySQL private lists, visibility, ownership and request security."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.api.v1.me.dependencies import (
    personal_peer_limiter, personal_read_limiter, personal_write_limiter,
)
from app.common.enums import AccountStatus
from app.core.config import settings
from app.core.database import get_db
from app.main import create_app
from app.models import (
    Category, City, ProductFavorite, ProductImage, ProductListing, ProductRecentView,
    SellerVerification, UserProfile,
)
from app.models.base import utc_now
from app.models.seller_verification import VerificationStatus
from app.repositories.favorites_repository import FavoritesRepository
from app.repositories.recently_viewed_repository import RecentlyViewedRepository
from app.services.token_service import AccessTokenService
from tests.integration.test_product_listings import eligible_user
from tests.integration.test_seller_verification import headers, make_user

FAVORITES = "/api/v1/me/favorites"
RECENT = "/api/v1/me/recently-viewed"
UNKNOWN = "item-" + "f" * 24
TIMESTAMP = datetime(2026, 1, 2, 3, 4, 5, 123456)
LIMITERS = (personal_peer_limiter, personal_read_limiter, personal_write_limiter)


@pytest.fixture
def personal_world(db_session):
    for limiter in LIMITERS:
        limiter.clear()
    seller = eligible_user(db_session)
    buyer, other = make_user(db_session), make_user(db_session)
    category = Category(slug="personal-test-category", name_en="Personal test", name_zh="测试")
    db_session.add(category)
    db_session.commit()
    app = create_app(settings.model_copy(update={"app_debug": False}))
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db_session, seller, buyer, other, category
    for limiter in LIMITERS:
        limiter.clear()


def product(world, **changes):
    _, db, seller, _, _, category = world
    city = db.scalar(select(City).where(City.slug == "qingdao"))
    row = ProductListing(seller_user_id=seller.id, title="Synthetic personal-list desk",
        description="A synthetic desk for private-list regression tests.", price="100.25",
        currency="CNY", condition="good", status="PUBLISHED", city_id=city.id,
        category_id=category.id, published_at=TIMESTAMP, **changes)
    db.add(row)
    db.commit()
    return row


def save(world, row, user=None):
    client, _, _, buyer, _, _ = world
    response = client.put(f"{FAVORITES}/{row.public_slug}", headers=headers(user or buyer))
    assert response.status_code == 200, response.text
    return response


def record(world, row, user=None):
    client, _, _, buyer, _, _ = world
    response = client.post(f"{RECENT}/{row.public_slug}", headers=headers(user or buyer))
    assert response.status_code == 204, response.text
    return response


def fetch(world, path, user=None, **params):
    response = world[0].get(path, headers=headers(user or world[3]), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def slugs(page):
    return [item["product"]["public_slug"] for item in page["items"]]


@pytest.mark.parametrize("method,path", [
    ("PUT", FAVORITES + "/" + UNKNOWN), ("DELETE", FAVORITES + "/" + UNKNOWN),
    ("GET", FAVORITES), ("POST", FAVORITES + "/lookup"),
    ("POST", RECENT + "/" + UNKNOWN), ("GET", RECENT),
    ("DELETE", RECENT + "/" + UNKNOWN), ("DELETE", RECENT),
])
@pytest.mark.parametrize("token", [None, "invalid"])
def test_all_private_endpoints_require_valid_auth(personal_world, method, path, token):
    response = personal_world[0].request(method, path,
        headers={} if token is None else {"Authorization": "Bearer " + token},
        **({"json": {"product_slugs": [UNKNOWN]}} if path.endswith("/lookup") else {}))
    assert response.status_code == 401, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.parametrize("status", [AccountStatus.SUSPENDED, AccountStatus.BANNED, AccountStatus.DELETED])
def test_ineligible_account_cannot_read_or_write(personal_world, status):
    client, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    buyer.account_status = status
    db.commit()
    assert client.get(FAVORITES, headers=headers(buyer)).status_code == 401
    assert client.put(f"{FAVORITES}/{row.public_slug}", headers=headers(buyer)).status_code == 401
    assert client.post(f"{RECENT}/{row.public_slug}", headers=headers(buyer)).status_code == 401


def test_expired_access_token_rejected(personal_world):
    token = AccessTokenService(now_provider=lambda: utc_now() - timedelta(days=1)).create_access_token(
        personal_world[3].id)
    response = personal_world[0].get(FAVORITES, headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401


def test_buyer_without_seller_profile_can_use_both_features(personal_world):
    row = product(personal_world)
    assert save(personal_world, row).json() == {"favorited": True}
    record(personal_world, row)
    assert slugs(fetch(personal_world, FAVORITES)) == [row.public_slug]
    assert slugs(fetch(personal_world, RECENT)) == [row.public_slug]


def test_favorite_idempotent_preserves_original_timestamp(personal_world):
    _, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    save(personal_world, row)
    association = db.get(ProductFavorite, (buyer.id, row.id))
    association.favorited_at = TIMESTAMP
    db.commit()
    save(personal_world, row)
    db.expire_all()
    assert db.get(ProductFavorite, (buyer.id, row.id)).favorited_at == TIMESTAMP
    assert db.scalar(select(func.count()).select_from(ProductFavorite).where(
        ProductFavorite.user_id == buyer.id)) == 1


def test_recent_repetition_refreshes_one_timestamp(personal_world):
    _, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    record(personal_world, row)
    association = db.get(ProductRecentView, (buyer.id, row.id))
    association.last_viewed_at = TIMESTAMP
    db.commit()
    record(personal_world, row)
    db.expire_all()
    assert db.get(ProductRecentView, (buyer.id, row.id)).last_viewed_at > TIMESTAMP
    assert db.scalar(select(func.count()).select_from(ProductRecentView).where(
        ProductRecentView.user_id == buyer.id)) == 1


def test_private_ownership_deletion_and_clear_do_not_cross_users(personal_world):
    client, db, _, buyer, other, _ = personal_world
    row = product(personal_world)
    save(personal_world, row)
    record(personal_world, row)
    assert fetch(personal_world, FAVORITES, other)["items"] == []
    assert fetch(personal_world, RECENT, other)["items"] == []
    for path in (FAVORITES + "/" + row.public_slug, RECENT + "/" + row.public_slug, RECENT):
        assert client.delete(path, headers=headers(other)).status_code == 204
    assert db.get(ProductFavorite, (buyer.id, row.id)) is not None
    assert db.get(ProductRecentView, (buyer.id, row.id)) is not None
    save(personal_world, row, other)
    record(personal_world, row, other)
    assert client.delete(RECENT, headers=headers(buyer)).status_code == 204
    db.expire_all()
    assert db.get(ProductRecentView, (buyer.id, row.id)) is None
    assert db.get(ProductRecentView, (other.id, row.id)) is not None
    assert db.get(ProductFavorite, (buyer.id, row.id)) is not None


@pytest.mark.parametrize("path", [FAVORITES, RECENT])
def test_delete_hidden_and_unknown_is_idempotent_non_disclosing(personal_world, path):
    client, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    save(personal_world, row)
    record(personal_world, row)
    row.status = "PAUSED"
    db.commit()
    for slug in (row.public_slug, row.public_slug, UNKNOWN):
        response = client.delete(f"{path}/{slug}", headers=headers(buyer))
        assert response.status_code == 204 and response.content == b""
    model = ProductFavorite if path == FAVORITES else ProductRecentView
    assert db.get(model, (buyer.id, row.id)) is None


def test_lookup_public_membership_hidden_unknown_and_other_users(personal_world):
    client, db, _, buyer, other, _ = personal_world
    saved, unsaved, hidden = (product(personal_world) for _ in range(3))
    save(personal_world, saved)
    save(personal_world, hidden)
    save(personal_world, unsaved, other)
    hidden.status = "PAUSED"
    db.commit()
    response = client.post(FAVORITES + "/lookup", headers=headers(buyer), json={
        "product_slugs": [saved.public_slug, unsaved.public_slug, hidden.public_slug, UNKNOWN]})
    assert response.status_code == 200
    assert response.json() == {"favorites": {saved.public_slug: True, unsaved.public_slug: False,
        hidden.public_slug: False, UNKNOWN: False}}


@pytest.mark.parametrize("state", ["DRAFT", "PAUSED", "ARCHIVED"])
def test_lifecycle_visibility_retains_hidden_rows(personal_world, state):
    client, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    save(personal_world, row)
    record(personal_world, row)
    row.status = state
    if state == "DRAFT":
        row.published_at = None
    db.commit()
    assert client.get(f"/api/v1/products/{row.public_slug}").status_code == 404
    assert fetch(personal_world, FAVORITES)["items"] == []
    assert fetch(personal_world, RECENT)["items"] == []
    assert client.put(f"{FAVORITES}/{row.public_slug}", headers=headers(buyer)).status_code == 404
    assert client.post(f"{RECENT}/{row.public_slug}", headers=headers(buyer)).status_code == 404
    assert db.get(ProductFavorite, (buyer.id, row.id)) is not None
    assert db.get(ProductRecentView, (buyer.id, row.id)) is not None
    row.status = "PUBLISHED"
    row.published_at = TIMESTAMP
    db.commit()
    assert slugs(fetch(personal_world, FAVORITES)) == [row.public_slug]
    assert slugs(fetch(personal_world, RECENT)) == [row.public_slug]


@pytest.mark.parametrize("target,field,value", [
    ("seller", "account_status", AccountStatus.SUSPENDED),
    ("seller", "email_verified", False), ("seller", "phone_verified", False),
    ("profile", "onboarding_completed", False), ("profile", "display_name", None),
    ("verification", "status", VerificationStatus.REJECTED),
    ("category", "is_active", False), ("city", "is_active", False),
])
def test_private_lists_use_same_visibility_as_canonical_public_detail(personal_world, target, field, value):
    client, db, seller, buyer, _, category = personal_world
    row = product(personal_world)
    save(personal_world, row)
    record(personal_world, row)
    objects = {"seller": seller, "category": category,
        "profile": db.scalar(select(UserProfile).where(UserProfile.user_id == seller.id)),
        "verification": db.scalar(select(SellerVerification).where(SellerVerification.user_id == seller.id)),
        "city": db.scalar(select(City).where(City.slug == "qingdao"))}
    setattr(objects[target], field, value)
    if target == "verification":
        objects[target].rejection_reason = "Synthetic revocation"
    db.commit()
    assert client.get(f"/api/v1/products/{row.public_slug}").status_code == 404
    assert fetch(personal_world, FAVORITES)["items"] == []
    assert fetch(personal_world, RECENT)["items"] == []
    lookup = client.post(FAVORITES + "/lookup", headers=headers(buyer),
        json={"product_slugs": [row.public_slug]})
    assert lookup.json() == {"favorites": {row.public_slug: False}}


def test_inactive_parent_hides_personal_card(personal_world):
    client, db, _, _, _, parent = personal_world
    child = Category(slug="personal-test-child", name_en="Child", name_zh="子类",
        parent_id=parent.id, parent_level=1, level=2)
    db.add(child)
    db.commit()
    row = product(personal_world)
    row.category_id = child.id
    db.commit()
    save(personal_world, row)
    record(personal_world, row)
    parent.is_active = False
    db.commit()
    assert client.get(f"/api/v1/products/{row.public_slug}").status_code == 404
    assert fetch(personal_world, FAVORITES)["items"] == fetch(personal_world, RECENT)["items"] == []


@pytest.mark.parametrize("path,model,field", [
    (FAVORITES, ProductFavorite, "favorited_at"), (RECENT, ProductRecentView, "last_viewed_at"),
])
def test_equal_timestamp_keysets_complete_and_private_cursor_replay_denied(personal_world, path, model, field):
    client, db, _, buyer, other, _ = personal_world
    rows = [product(personal_world) for _ in range(7)]
    for row in rows:
        db.add(model(user_id=buyer.id, product_listing_id=row.id, **{field: TIMESTAMP}))
    db.commit()
    first = fetch(personal_world, path, limit=2)
    token = first["next_cursor"]
    assert first["has_more"] and token
    for wrong_path, wrong_user, limit in ((path, other, 2),
        (RECENT if path == FAVORITES else FAVORITES, buyer, 2), (path, buyer, 3)):
        response = client.get(wrong_path, headers=headers(wrong_user), params={"limit": limit, "cursor": token})
        assert response.status_code == 400 and response.json() == {"detail": "Invalid cursor."}
    seen = slugs(first)
    for _ in range(6):
        page = fetch(personal_world, path, limit=2, cursor=token)
        seen.extend(slugs(page))
        token = page["next_cursor"]
        if token is None:
            assert page["has_more"] is False
            break
    assert len(seen) == len(set(seen)) == 7
    assert seen == sorted([row.public_slug for row in rows], reverse=True)


@pytest.mark.parametrize("path", [FAVORITES, RECENT])
def test_private_cursor_tamper_and_public_cursor_rejected(personal_world, path):
    for _ in range(3):
        row = product(personal_world)
        save(personal_world, row)
        record(personal_world, row)
    token = fetch(personal_world, path, limit=1)["next_cursor"]
    public_token = personal_world[0].get("/api/v1/products", params={"limit": 1}).json()["next_cursor"]
    for bad in (token[:-1], "A" + token[1:], token + "A", "a.b", public_token):
        response = personal_world[0].get(path, headers=headers(personal_world[3]),
            params={"limit": 1, "cursor": bad})
        assert response.status_code == 400 and response.json() == {"detail": "Invalid cursor."}


@pytest.mark.parametrize("path,model,field", [
    (FAVORITES, ProductFavorite, "favorited_at"), (RECENT, ProductRecentView, "last_viewed_at"),
])
@pytest.mark.parametrize("count", [1, 24, 50])
def test_personal_lists_bounded_projection_queries_without_private_fields(personal_world, path, model, field, count):
    client, db, seller, buyer, _, _ = personal_world
    for _ in range(count):
        row = product(personal_world)
        db.add(model(user_id=buyer.id, product_listing_id=row.id, **{field: TIMESTAMP}))
    db.commit()
    statements = []
    auth_headers = headers(buyer)
    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)
    event.listen(db.bind.engine, "before_cursor_execute", capture)
    try:
        response = client.get(path, headers=auth_headers, params={"limit": count})
    finally:
        event.remove(db.bind.engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    assert len(response.json()["items"]) == count
    # Fixed authentication loads and one bounded public projection, independent of page size.
    association_selects = [sql for sql in statements if model.__tablename__ in sql]
    assert len(association_selects) == 1
    assert len(statements) <= 3
    assert "LIMIT" in association_selects[0] and "OFFSET" not in association_selects[0]
    assert "count(" not in association_selects[0].lower()
    for secret in (seller.id, seller.email, seller.password_hash, buyer.id,
                   "storage_key", "seller_user_id", "product_listing_id", "review_reference"):
        assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_lookup_is_one_bounded_query(personal_world):
    client, db, _, buyer, _, _ = personal_world
    rows = [product(personal_world) for _ in range(50)]
    db.add_all(ProductFavorite(user_id=buyer.id, product_listing_id=row.id, favorited_at=TIMESTAMP)
        for row in rows)
    db.commit()
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if "product_favorites" in statement and statement.lstrip().lower().startswith("select"):
            statements.append(statement)
    event.listen(db.bind.engine, "before_cursor_execute", capture)
    try:
        response = client.post(FAVORITES + "/lookup", headers=headers(buyer),
            json={"product_slugs": [row.public_slug for row in rows]})
    finally:
        event.remove(db.bind.engine, "before_cursor_execute", capture)
    assert response.status_code == 200, response.text
    assert set(response.json()["favorites"].values()) == {True}
    assert len(statements) == 1


@pytest.mark.parametrize("path", [FAVORITES, RECENT])
@pytest.mark.parametrize("query", ["limit=0", "limit=51", "limit=abc", "limit=1&limit=2",
    "cursor=", "cursor=" + "x" * 1025, "user_id=forged", "sort=users.password_hash"])
def test_strict_safe_query_validation(personal_world, path, query):
    response = personal_world[0].get(path + "?" + query, headers=headers(personal_world[3]))
    assert response.status_code in {400, 413, 422}
    assert "forged" not in response.text and "password_hash" not in response.text


@pytest.mark.parametrize("body", [
    {}, {"product_slugs": []}, {"product_slugs": [UNKNOWN, UNKNOWN]},
    {"product_slugs": [UNKNOWN], "user_id": "forged"}, {"product_slugs": [True]},
    {"product_slugs": "not-a-list"}, {"product_slugs": ["' OR 1=1 --"]},
    {"product_slugs": ["item-" + f"{index:024x}" for index in range(51)]},
])
def test_lookup_strict_schema(personal_world, body):
    response = personal_world[0].post(FAVORITES + "/lookup", headers=headers(personal_world[3]), json=body)
    assert response.status_code == 422, response.text
    assert "forged" not in response.text and "OR 1=1" not in response.text


@pytest.mark.parametrize("method,path", [("PUT", FAVORITES + "/" + UNKNOWN),
    ("DELETE", FAVORITES + "/" + UNKNOWN), ("POST", RECENT + "/" + UNKNOWN),
    ("DELETE", RECENT + "/" + UNKNOWN), ("DELETE", RECENT)])
def test_bodyless_commands_reject_mass_assignment(personal_world, method, path):
    response = personal_world[0].request(method, path, headers=headers(personal_world[3]),
        json={"user_id": "forged"})
    assert response.status_code == 422
    assert "forged" not in response.text


def test_malformed_lookup_consumes_rate_budget_and_has_safe_retry_after(personal_world):
    client, _, _, buyer, _, _ = personal_world
    rejected = None
    for _ in range(190):
        response = client.post(FAVORITES + "/lookup", headers={**headers(buyer),
            "Content-Type": "application/json"}, content="{")
        if response.status_code == 429:
            rejected = response
            break
        assert response.status_code == 422
    assert rejected is not None
    assert int(rejected.headers["retry-after"]) > 0
    assert rejected.headers["cache-control"] == "no-store"


def test_lookup_oversized_body_is_bounded(personal_world):
    response = personal_world[0].post(FAVORITES + "/lookup", headers={**headers(personal_world[3]),
        "Content-Type": "application/json"}, content='{"product_slugs":["' + "x" * 20000 + '"]}')
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"


def test_favorite_put_cors_preflight_and_no_store(personal_world):
    origin = settings.backend_cors_origins[0] if hasattr(settings, "backend_cors_origins") else "http://localhost:5173"
    response = personal_world[0].options(FAVORITES + "/" + UNKNOWN, headers={
        "Origin": origin, "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "authorization"})
    assert response.status_code == 200, response.text
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-origin"] == origin


def test_public_gets_never_write_history_or_favorites(personal_world):
    client, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    for path in ("/api/v1/products", "/api/v1/products/" + row.public_slug):
        assert client.get(path, headers=headers(buyer)).status_code == 200
        assert client.get(path).status_code == 200
    assert db.scalar(select(func.count()).select_from(ProductFavorite).where(ProductFavorite.user_id == buyer.id)) == 0
    assert db.scalar(select(func.count()).select_from(ProductRecentView).where(ProductRecentView.user_id == buyer.id)) == 0


def test_public_card_cover_tracks_reorder_without_storage_keys(personal_world):
    _, db, _, _, _, _ = personal_world
    row = product(personal_world)
    first, second = "img-" + "a" * 32, "img-" + "b" * 32
    db.add_all([ProductImage(product_listing_id=row.id, public_ref=ref,
        storage_key="product-media/" + character * 64, mime_type="image/png", width=1,
        height=1, file_size=100, position=index) for index, (ref, character) in
        enumerate(((first, "a"), (second, "b")))])
    db.commit()
    save(personal_world, row)
    record(personal_world, row)
    for path in (FAVORITES, RECENT):
        card = fetch(personal_world, path)["items"][0]["product"]
        assert card["cover_image"] == {"ref": first,
            "url": f"/api/v1/products/{row.public_slug}/images/{first}"}
    image = db.scalar(select(ProductImage).where(ProductImage.public_ref == first))
    image.position = 8
    db.flush()
    db.scalar(select(ProductImage).where(ProductImage.public_ref == second)).position = 0
    db.flush()
    image.position = 1
    db.commit()
    for path in (FAVORITES, RECENT):
        assert fetch(personal_world, path)["items"][0]["product"]["cover_image"]["ref"] == second


@pytest.mark.parametrize("model,field", [(ProductFavorite, "favorited_at"),
    (ProductRecentView, "last_viewed_at")])
def test_composite_key_and_foreign_key_integrity(personal_world, model, field):
    _, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    db.add(model(user_id=buyer.id, product_listing_id=row.id, **{field: TIMESTAMP}))
    db.commit()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(model(user_id=buyer.id, product_listing_id=row.id, **{field: TIMESTAMP}))
        db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(model(user_id=buyer.id, product_listing_id="00000000-0000-4000-8000-000000000000",
            **{field: TIMESTAMP}))
        db.flush()


def test_quota_counts_hidden_and_repeat_put_still_succeeds(personal_world):
    client, db, _, buyer, _, _ = personal_world
    rows = [product(personal_world) for _ in range(settings.personal_favorites_limit + 1)]
    db.add_all(ProductFavorite(user_id=buyer.id, product_listing_id=row.id, favorited_at=TIMESTAMP)
        for row in rows[:-1])
    rows[0].status = "PAUSED"
    db.commit()
    assert save(personal_world, rows[1]).json() == {"favorited": True}
    denied = client.put(FAVORITES + "/" + rows[-1].public_slug, headers=headers(buyer))
    assert denied.status_code == 409
    assert db.scalar(select(func.count()).select_from(ProductFavorite).where(
        ProductFavorite.user_id == buyer.id)) == settings.personal_favorites_limit


def test_retention_removes_oldest_and_never_other_users(personal_world):
    _, db, _, buyer, other, _ = personal_world
    rows = [product(personal_world) for _ in range(settings.personal_history_limit + 1)]
    for index, row in enumerate(rows[:-1]):
        db.add(ProductRecentView(user_id=buyer.id, product_listing_id=row.id,
            last_viewed_at=TIMESTAMP + timedelta(seconds=index)))
    db.add(ProductRecentView(user_id=other.id, product_listing_id=rows[0].id, last_viewed_at=TIMESTAMP))
    db.commit()
    record(personal_world, rows[0])
    record(personal_world, rows[-1])
    db.expire_all()
    assert db.get(ProductRecentView, (buyer.id, rows[1].id)) is None
    assert db.get(ProductRecentView, (buyer.id, rows[0].id)) is not None
    assert db.get(ProductRecentView, (other.id, rows[0].id)) is not None
    assert db.scalar(select(func.count()).select_from(ProductRecentView).where(
        ProductRecentView.user_id == buyer.id)) == settings.personal_history_limit


@pytest.mark.parametrize("path,model,field", [
    (FAVORITES, ProductFavorite, "favorited_at"), (RECENT, ProductRecentView, "last_viewed_at"),
])
def test_visibility_precedes_sql_limit_and_mutation_rechecks_public_access(personal_world, path, model, field):
    client, db, _, buyer, _, _ = personal_world
    rows = [product(personal_world) for _ in range(5)]
    for index, row in enumerate(rows):
        db.add(model(user_id=buyer.id, product_listing_id=row.id,
            **{field: TIMESTAMP + timedelta(seconds=index)}))
    rows[-1].status = "PAUSED"
    rows[-2].status = "DRAFT"
    rows[-2].published_at = None
    db.commit()
    first = fetch(personal_world, path, limit=1)
    assert slugs(first) == [rows[2].public_slug]
    assert first["has_more"]
    rows[1].status = "PAUSED"
    db.commit()
    assert client.get("/api/v1/products/" + rows[1].public_slug).status_code == 404
    following = fetch(personal_world, path, limit=1, cursor=first["next_cursor"])
    assert slugs(following) == [rows[0].public_slug]
    assert following["has_more"] is False


def test_recent_upsert_preserves_newer_observation_against_stale_time(personal_world):
    _, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    repo = RecentlyViewedRepository()
    newest = TIMESTAMP + timedelta(days=2)
    repo.upsert(db, buyer.id, row.id, newest)
    repo.upsert(db, buyer.id, row.id, TIMESTAMP)
    db.commit()
    assert db.get(ProductRecentView, (buyer.id, row.id)).last_viewed_at == newest


def test_favorite_failure_rolls_back_insert_and_hides_driver_detail(personal_world, monkeypatch):
    client, db, _, buyer, _, _ = personal_world
    row = product(personal_world)
    add = FavoritesRepository.add
    def fail_after_insert(self, session, *args):
        add(self, session, *args)
        session.flush()
        raise RuntimeError("private database credential material")
    monkeypatch.setattr(FavoritesRepository, "add", fail_after_insert)
    response = client.put(FAVORITES + "/" + row.public_slug, headers=headers(buyer))
    assert response.status_code == 503
    assert "credential" not in response.text and "database" not in response.text
    db.expire_all()
    assert db.get(ProductFavorite, (buyer.id, row.id)) is None


def test_history_failure_rolls_back_upsert_and_does_not_erase_old_history(personal_world, monkeypatch):
    client, db, _, buyer, _, _ = personal_world
    existing, new = product(personal_world), product(personal_world)
    record(personal_world, existing)
    upsert = RecentlyViewedRepository.upsert
    def fail_after_upsert(self, session, *args):
        upsert(self, session, *args)
        session.flush()
        raise RuntimeError("private database credential material")
    monkeypatch.setattr(RecentlyViewedRepository, "upsert", fail_after_upsert)
    response = client.post(RECENT + "/" + new.public_slug, headers=headers(buyer))
    assert response.status_code == 503 and "credential" not in response.text
    db.expire_all()
    assert db.get(ProductRecentView, (buyer.id, new.id)) is None
    assert db.get(ProductRecentView, (buyer.id, existing.id)) is not None
