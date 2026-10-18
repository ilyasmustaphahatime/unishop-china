"""Real-MySQL anonymous browse, privacy and continuation contracts."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine
from app.core.database import get_db
from app.common.enums import AccountStatus
from app.main import create_app
from app.api.v1.products.dependencies import product_peer_limiter, product_read_limiter, product_write_limiter
from app.models import Category, City, ProductListing, SellerVerification, User, UserProfile, UserRole
from app.models.base import utc_now
from app.models.seller_verification import VerificationStatus
from app.services.product_image_storage import LocalProductImageStorage
from app.repositories.product_browse_repository import ProductBrowseRepository
from app.services.product_browse_cursor import BrowseCursorCodec
from tests.conftest import _database_snapshot
from tests.integration.test_product_listings import create, action, eligible_user
from tests.integration.test_seller_verification import headers
from tests.product_image_fixtures import raster

BROWSE = "/api/v1/products"


@pytest.fixture(name="world")
def listing_world(db_session):
    for limiter in (product_peer_limiter, product_read_limiter, product_write_limiter):
        limiter.clear()
    owner, other = eligible_user(db_session), eligible_user(db_session)
    category = Category(slug="product-test-category", name_en="Test Category", name_zh="测试分类")
    db_session.add(category)
    db_session.commit()
    app = create_app(settings.model_copy(update={"app_debug": False}))
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db_session, owner, other, category
    for limiter in (product_peer_limiter, product_read_limiter, product_write_limiter):
        limiter.clear()


def publish(world, **changes):
    slug = create(world, **changes)["public_slug"]
    assert action(world, slug, "publish").status_code == 200
    return slug


def test_empty_browse_contract(world):
    response = world[0].get(BROWSE)
    assert response.status_code == 200, response.text
    assert response.json() == {"items": [], "next_cursor": None, "has_more": False}
    assert response.headers["cache-control"] == "no-store"


def test_published_listing_card_is_minimal_and_matches_detail(world):
    slug = publish(world)
    response = world[0].get(BROWSE)
    assert response.status_code == 200, response.text
    card = response.json()["items"][0]
    detail = world[0].get(f"{BROWSE}/{slug}").json()
    assert card["public_slug"] == slug
    assert card["price"] == "150.25"
    assert card["seller"] == detail["seller"]
    assert card["city"] == detail["city"]
    assert card["category"] == detail["category"]
    assert card["cover_image"] is None
    assert set(card) == {"public_slug", "title", "price", "currency", "condition", "city",
                         "category", "cover_image", "seller", "published_at"}
    for secret in (world[2].id, world[2].email, world[2].password_hash,
                   "storage_key", "seller_user_id", "verification"):
        assert secret not in response.text


@pytest.mark.parametrize("sort", ["newest", "price_asc", "price_desc"])
def test_keyset_complete_without_duplicates_at_ties(world, sort):
    slugs = [publish(world, price="100.00", title=f"Desk number {number}") for number in range(7)]
    seen = []
    cursor = None
    for _ in range(8):
        response = world[0].get(BROWSE, params={"sort": sort, "limit": 2,
                                                 **({"cursor": cursor} if cursor else {})})
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(page["items"])
        if page["next_cursor"] is None:
            assert page["has_more"] is False
            break
        assert page["has_more"] is True
        cursor = page["next_cursor"]
    assert len(seen) == len(slugs)
    assert {item["public_slug"] for item in seen} == set(slugs)
    reverse = sort != "price_asc"
    sort_value = "published_at" if sort == "newest" else "price"
    assert seen == sorted(seen, key=lambda item: (item[sort_value], item["public_slug"]),
                          reverse=reverse)


def test_decimal_filter_and_cursor_query_binding(world):
    low = publish(world, price="0.01")
    publish(world, price="150.25")
    high = publish(world, price="9999999999.99")
    page = world[0].get(BROWSE, params={"sort": "price_asc", "limit": 1}).json()
    assert page["items"][0]["public_slug"] == low
    assert world[0].get(BROWSE, params={"sort": "price_asc", "limit": 1,
                                        "cursor": page["next_cursor"]}).status_code == 200
    assert world[0].get(BROWSE, params={"sort": "price_desc", "limit": 1,
                                        "cursor": page["next_cursor"]}).status_code == 400
    assert world[0].get(BROWSE, params={"sort": "price_asc", "limit": 1,
                                        "city": "beijing", "cursor": page["next_cursor"]}).status_code == 400
    filtered = world[0].get(BROWSE, params={"min_price": "9999999999.99"}).json()
    assert [x["public_slug"] for x in filtered["items"]] == [high]


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 51}, {"sort": "users.password_hash"},
    {"min_price": "NaN"}, {"min_price": "1.001"}, {"min_price": "-1"},
    {"min_price": "2", "max_price": "1"}, {"city": "../private"},
    {"q": " "}, {"q": "a"}, {"q": "x" * 161}, {"q": "\u202e desk"},
    {"cursor": ""}, {"cursor": "x" * 513}, {"unexpected": "1"},
])
def test_invalid_parameters_are_safe(world, params):
    response = world[0].get(BROWSE, params=params)
    assert response.status_code in {400, 413, 422}
    assert "password_hash" not in response.text


def test_duplicate_parameters_rejected(world):
    assert world[0].get(BROWSE + "?limit=1&limit=2").status_code == 422


def test_browse_query_size_and_malformed_requests_consume_rate_limit(world):
    client = world[0]
    assert client.get(BROWSE + "?q=" + "x" * 1100).status_code == 413
    for _ in range(59):
        assert client.get(BROWSE + "?limit=1&limit=2").status_code == 422
    assert client.get(BROWSE + "?limit=1&limit=2").status_code == 429
    rejected = client.get(BROWSE)
    assert rejected.status_code == 429 and rejected.headers["retry-after"]


def test_cursor_tamper_and_truncation_rejected(world):
    for _ in range(3):
        publish(world)
    cursor = world[0].get(BROWSE, params={"limit": 1}).json()["next_cursor"]
    assert cursor
    for bad in (cursor[:-1], cursor[:20], "A" + cursor[1:], cursor + "A", "a.b"):
        result = world[0].get(BROWSE, params={"limit": 1, "cursor": bad})
        assert result.status_code == 400 and result.json() == {"detail": "Invalid cursor."}


def test_filters_and_visibility_follow_detail(world):
    draft = create(world)["public_slug"]
    published = publish(world, condition="new", price="80.00")
    paused = publish(world, price="90.00")
    action(world, paused, "pause")
    page = world[0].get(BROWSE, params={"city": "qingdao", "category": "product-test-category",
                                        "condition": "new", "min_price": "80", "max_price": "80"}).json()
    assert [x["public_slug"] for x in page["items"]] == [published]
    assert world[0].get(f"{BROWSE}/{draft}").status_code == 404
    assert world[0].get(f"{BROWSE}/{paused}").status_code == 404


@pytest.mark.parametrize("target,field,value", [
    ("owner", "account_status", AccountStatus.SUSPENDED),
    ("owner", "email_verified", False),
    ("owner", "phone_verified", False),
    ("profile", "onboarding_completed", False),
    ("profile", "display_name", None),
    ("category", "is_active", False),
    ("city", "is_active", False),
])
def test_detail_browse_visibility_differential(world, target, field, value):
    slug = publish(world)
    client, db, owner, _, category = world
    assert [x["public_slug"] for x in client.get(BROWSE).json()["items"]] == [slug]
    objects = {"owner": owner, "profile": db.scalar(select(UserProfile).where(UserProfile.user_id == owner.id)),
               "category": category, "city": db.scalar(select(City).where(City.slug == "qingdao"))}
    setattr(objects[target], field, value)
    db.commit()
    assert client.get(f"{BROWSE}/{slug}").status_code == 404
    assert client.get(BROWSE).json()["items"] == []


def test_revoked_seller_verification_hides_detail_and_browse(world):
    slug = publish(world)
    client, db, owner, _, _ = world
    verification = db.scalar(select(SellerVerification).where(SellerVerification.user_id == owner.id))
    verification.status = VerificationStatus.REJECTED
    verification.rejection_reason = "Synthetic regression test"
    db.commit()
    assert client.get(f"{BROWSE}/{slug}").status_code == 404
    assert client.get(BROWSE).json()["items"] == []


def test_child_category_parent_deactivation_hides_detail_and_browse(world):
    client, db, _, _, root = world
    child = Category(slug="product-test-child", name_en="Child", name_zh="子类",
                     parent_id=root.id, parent_level=1, level=2)
    db.add(child)
    db.commit()
    slug = publish(world, category_slug=child.slug)
    assert [x["public_slug"] for x in client.get(BROWSE, params={"category": child.slug}).json()["items"]] == [slug]
    root.is_active = False
    db.commit()
    assert client.get(f"{BROWSE}/{slug}").status_code == 404
    assert client.get(BROWSE, params={"category": child.slug}).json()["items"] == []


def test_cursor_rechecks_current_visibility_and_lifecycle(world):
    client, _, _, _, _ = world
    slugs = [publish(world) for _ in range(3)]
    page = client.get(BROWSE, params={"limit": 1}).json()
    assert page["next_cursor"]
    remaining = set(slugs) - {page["items"][0]["public_slug"]}
    hidden = next(iter(remaining))
    assert action(world, hidden, "pause").status_code == 200
    next_page = client.get(BROWSE, params={"limit": 1, "cursor": page["next_cursor"]})
    assert next_page.status_code == 200
    assert hidden not in {item["public_slug"] for item in next_page.json()["items"]}


def test_public_cover_ref_tracks_reorder_and_delete(world, tmp_path):
    client, _, owner, _, _ = world
    storage = LocalProductImageStorage(tmp_path / "browse-media")
    client.app.state.product_image_storage = storage
    slug = create(world)["public_slug"]
    url = f"/api/v1/seller/products/{slug}/images"
    try:
        first = client.post(url, headers=headers(owner),
                            files={"file": ("one.png", raster(), "image/png")})
        second = client.post(url, headers=headers(owner),
                             files={"file": ("two.png", raster(), "image/png")})
        assert first.status_code == second.status_code == 201
        refs = [first.json()["ref"], second.json()["ref"]]
        assert client.get(BROWSE).json()["items"] == []
        assert action(world, slug, "publish").status_code == 200
        def cover():
            return client.get(BROWSE).json()["items"][0]["cover_image"]
        assert cover() == {"ref": refs[0], "url": f"{BROWSE}/{slug}/images/{refs[0]}"}
        assert client.patch(url + "/order", headers=headers(owner),
                            json={"images": refs[::-1]}).status_code == 200
        assert cover()["ref"] == refs[1]
        assert client.get(cover()["url"]).status_code == 200
        assert client.delete(url + "/" + refs[1], headers=headers(owner)).status_code == 204
        assert cover()["ref"] == refs[0]
        assert action(world, slug, "pause").status_code == 200
        assert client.get(BROWSE).json()["items"] == []
        assert client.get(f"{BROWSE}/{slug}/images/{refs[0]}").status_code == 404
    finally:
        for key in list(storage.keys()):
            storage.delete(key)


@pytest.mark.parametrize("count", [1, 24, 50])
def test_browse_has_one_sql_statement_for_many_cards(world, count):
    _, db, owner, _, category = world
    city = db.scalar(select(City).where(City.slug == "qingdao"))
    for index in range(count):
        db.add(ProductListing(seller_user_id=owner.id, title=f"Desk index {index}",
            description="A sturdy desk in good condition.", price="100.00", currency="CNY",
            condition="good", status="PUBLISHED", city_id=city.id, category_id=category.id,
            published_at=utc_now()))
    db.commit()
    statements = []
    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().lower().startswith("select"):
            statements.append(statement)
    event.listen(db.bind.engine, "before_cursor_execute", capture)
    try:
        result = world[0].get(BROWSE, params={"limit": count})
    finally:
        event.remove(db.bind.engine, "before_cursor_execute", capture)
    assert result.status_code == 200, result.text
    assert len(result.json()["items"]) == count
    assert len(statements) == 1


def test_database_and_cursor_signing_fail_closed(world, monkeypatch):
    publish(world)
    monkeypatch.setattr(ProductBrowseRepository, "page", lambda *_: (_ for _ in ()).throw(RuntimeError("private db")))
    response = world[0].get(BROWSE)
    assert response.status_code == 503 and "private db" not in response.text
    monkeypatch.undo()
    publish(world)
    monkeypatch.setattr(BrowseCursorCodec, "encode", lambda *_: (_ for _ in ()).throw(RuntimeError("private key")))
    response = world[0].get(BROWSE, params={"limit": 1})
    assert response.status_code == 503 and "private key" not in response.text


@pytest.fixture
def committed_search_world():
    # InnoDB FULLTEXT indexes become visible on commit, unlike ordinary reads
    # in the outer-rollback fixture. The exact synthetic IDs are removed below.
    before = _database_snapshot()
    user_id = category_id = None
    with Session(engine) as db:
        try:
            owner = eligible_user(db)
            user_id = owner.id
            category = Category(slug=f"browse-fts-{uuid4().hex[:12]}",
                                name_en="Synthetic Search", name_zh="搜索测试")
            db.add(category)
            db.flush()
            category_id = category.id
            city = db.scalar(select(City).where(City.slug == "qingdao"))
            titles = ["Beautiful 中文桌子", "مكتب جميل للطلاب", "Bureau café moderne",
                      "laptop phone book", "ordinateur téléphone livre", "手机电脑书",
                      "هاتف حاسوب كتاب", "Mixed laptop 手机 هاتف"]
            slugs = []
            for title in titles:
                row = ProductListing(seller_user_id=user_id, title=title,
                    description="A sturdy desk in good condition.", price="150.25",
                    currency="CNY", condition="good", status="PUBLISHED",
                    city_id=city.id, category_id=category_id, published_at=utc_now())
                db.add(row)
                db.flush()
                slugs.append(row.public_slug)
            db.commit()
            with TestClient(create_app(settings.model_copy(update={"app_debug": False})),
                            raise_server_exceptions=False) as client:
                yield client, slugs
        finally:
            db.rollback()
            if user_id is not None:
                db.execute(delete(ProductListing).where(ProductListing.seller_user_id == user_id))
                if category_id is not None:
                    db.execute(delete(Category).where(Category.id == category_id))
                db.execute(delete(SellerVerification).where(SellerVerification.user_id == user_id))
                db.execute(delete(UserProfile).where(UserProfile.user_id == user_id))
                db.execute(delete(UserRole).where(UserRole.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
                db.commit()
    assert _database_snapshot() == before


def test_search_chinese_arabic_latin_and_injection_literal(committed_search_world):
    client, slugs = committed_search_world
    for term, expected in (("桌子", 0), ("مكتب", 1), ("café", 2),
                           ("laptop", 3), ("phone", 3), ("book", 3),
                           ("ordinateur", 4), ("téléphone", 4), ("livre", 4),
                           ("手机", 5), ("电脑", 5), ("手机电脑书", 5),
                           ("هاتف", 6), ("حاسوب", 6), ("كتاب", 6),
                           ("laptop 手机", 7)):
        response = client.get(BROWSE, params={"q": term})
        assert response.status_code == 200, response.text
        assert slugs[expected] in {item["public_slug"] for item in response.json()["items"]}
    literal = client.get(BROWSE, params={"q": "UNION SELECT"})
    assert literal.status_code == 200 and literal.json()["items"] == []
    response = client.get(BROWSE, params={"q": "' OR 1=1 --"})
    assert response.status_code == 422 and "OR 1=1" not in response.text


@pytest.mark.parametrize("repeat", range(3))
def test_concurrent_identical_cursor_requests_are_deterministic(committed_search_world, repeat):
    client, slugs = committed_search_world
    first = client.get(BROWSE, params={"limit": 1, "sort": "price_asc"}).json()
    assert first["next_cursor"]
    params = {"limit": 1, "sort": "price_asc", "cursor": first["next_cursor"]}
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.get(BROWSE, params=params), range(12)))
    assert all(response.status_code == 200 for response in responses)
    assert len({response.text for response in responses}) == 1
    assert responses[0].json()["items"][0]["public_slug"] in slugs
