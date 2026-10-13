"""Real MySQL listing contracts, BOLA, eligibility, privacy, and rollback."""
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, event
from sqlalchemy.exc import IntegrityError, OperationalError
from app.api.v1.products.dependencies import product_peer_limiter, product_read_limiter, product_write_limiter
from app.common.enums import AccountStatus
from app.core.config import settings
from app.core.database import get_db
from app.main import create_app
from app.models import Category, City, ProductListing, UserProfile, SellerVerification
from app.models.base import utc_now
from app.models.seller_verification import VerificationStatus
from app.repositories.product_repository import ProductRepository
from app.services.product_service import ProductService
from tests.integration.test_seller_verification import make_user, headers

OWN = "/api/v1/seller/products"
PUBLIC = "/api/v1/products/"


def eligible_user(db):
    user = make_user(db)
    city = db.scalar(select(City).where(City.slug == "qingdao"))
    db.add(UserProfile(user_id=user.id, display_name="Synthetic Seller", city=city.name_en,
                       city_id=city.id, onboarding_completed=True))
    db.add(SellerVerification(user_id=user.id, status=VerificationStatus.VERIFIED,
                              submitted_at=utc_now(), reviewed_at=utc_now()))
    db.flush()
    return user


@pytest.fixture
def world(db_session):
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


def body(**changes):
    return {"title": "Used study desk", "description": "A sturdy desk in good condition.",
            "price": "150.25", "condition": "good", "city_slug": "qingdao",
            "category_slug": "product-test-category", **changes}


def create(world, **changes):
    client, _, owner, _, _ = world
    response = client.post(OWN, headers=headers(owner), json=body(**changes))
    assert response.status_code == 201, response.json()
    return response.json()


def action(world, slug, name, user=None):
    return world[0].post(f"{OWN}/{slug}/{name}", headers=headers(user or world[2]), json={})


def test_complete_lifecycle_price_slug_and_safe_projections(world):
    client, db, owner, _, _ = world
    draft = create(world)
    slug = draft["public_slug"]
    assert draft["status"] == "DRAFT" and draft["published_at"] is None
    assert draft["price"] == "150.25" and draft["currency"] == "CNY"
    assert len(slug) == 29 and slug.startswith("item-") and "desk" not in slug
    assert client.get(PUBLIC + slug).status_code == 404
    published = action(world, slug, "publish").json()
    assert published["status"] == "PUBLISHED" and published["published_at"]
    public = client.get(PUBLIC + slug)
    assert public.status_code == 200 and public.headers["cache-control"] == "no-store"
    assert set(public.json()) == {"public_slug", "title", "description", "price", "currency", "condition",
                                 "city", "category", "published_at", "status", "seller", "images"}
    assert public.json()["images"] == []  # Phase 9 zero-image publishing remains valid.
    assert set(public.json()["seller"]) == {"public_handle", "display_name", "seller_verified"}
    assert public.json()["seller"]["seller_verified"] is True
    for secret in (owner.id, owner.email, owner.password_hash, "storage_key", "challenge", "review_reference"):
        assert secret not in public.text
    edit = client.patch(OWN + "/" + slug, headers=headers(owner), json={"title": "Updated desk title"}).json()
    assert edit["status"] == "PUBLISHED" and edit["public_slug"] == slug and edit["price"] == "150.25"
    assert action(world, slug, "pause").json()["status"] == "PAUSED"
    assert client.get(PUBLIC + slug).status_code == 404
    assert action(world, slug, "publish").json()["published_at"] == published["published_at"]
    assert action(world, slug, "archive").json()["status"] == "ARCHIVED"
    assert client.get(PUBLIC + slug).status_code == 404
    assert client.get(OWN + "/" + slug, headers=headers(owner)).json()["status"] == "ARCHIVED"
    assert db.scalar(select(ProductListing.seller_user_id).where(ProductListing.public_slug == slug)) == owner.id


@pytest.mark.parametrize("operation", ["read", "edit", "publish", "pause", "archive"])
def test_cross_owner_every_operation_generic_not_found(world, operation):
    client, _, _, other, _ = world
    slug = create(world)["public_slug"]
    path = OWN + "/" + slug
    response = (client.get(path, headers=headers(other)) if operation == "read" else
                client.patch(path, headers=headers(other), json={"title": "Forged update"}) if operation == "edit" else
                action(world, slug, operation, other))
    assert response.status_code == 404 and response.json() == {"detail": "Listing not found."}
    assert client.get(OWN, headers=headers(other)).json()["items"] == []


@pytest.mark.parametrize("operation", ["create", "list", "read", "edit", "publish", "pause", "archive"])
def test_every_owner_endpoint_requires_bearer(world, operation):
    client = world[0]
    slug = create(world)["public_slug"]
    path = OWN + "/" + slug
    response = (client.post(OWN, json=body()) if operation == "create" else
                client.get(OWN if operation == "list" else path) if operation in {"list", "read"} else
                client.patch(path, json={"title": "New title"}) if operation == "edit" else
                client.post(path + "/" + operation, json={}))
    assert response.status_code == 401 and response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("field", ["id", "seller_user_id", "user_id", "owner", "status", "public_slug", "currency",
                                   "created_at", "updated_at", "published_at", "city_id", "category_id",
                                   "is_admin", "seller_verified", "images", "storage_key"])
@pytest.mark.parametrize("operation", ["create", "edit"])
def test_mass_assignment_rejected(world, field, operation):
    client, _, owner, _, _ = world
    slug = create(world)["public_slug"]
    payload = {**(body() if operation == "create" else {"title": "New title"}), field: "attacker-controlled"}
    response = (client.post(OWN, headers=headers(owner), json=payload) if operation == "create" else
                client.patch(OWN + "/" + slug, headers=headers(owner), json=payload))
    assert response.status_code == 422 and "attacker-controlled" not in response.text


@pytest.mark.parametrize("price", [0, 1.2, True, False, None, "0", "0.00", "-1", "+1", "01", "1.001", "1e3",
                                   "NaN", "Infinity", " 1", "1 ", "10000000000", "1,00", ".5", "1."])
def test_unsafe_price_rejected_without_rounding(world, price):
    response = world[0].post(OWN, headers=headers(world[2]), json=body(price=price))
    assert response.status_code == 422


@pytest.mark.parametrize("price,canonical", [("0.01", "0.01"), ("10", "10.00"), ("10.1", "10.10"),
                                             ("9999999999.99", "9999999999.99")])
def test_price_decimal_boundaries(world, price, canonical):
    assert create(world, price=price)["price"] == canonical


@pytest.mark.parametrize("field,value", [("title", "  "), ("title", "ab"), ("title", "a" * 121),
                                         ("title", "bad\x00title"), ("title", "bad\u202etitle"),
                                         ("description", "short"), ("description", "x" * 5001),
                                         ("description", "description\x00"), ("description", "description\u2066"),
                                         ("condition", "broken"), ("condition", True), ("city_slug", "Qingdao"),
                                         ("category_slug", "../catalog")])
def test_server_validation_boundaries(world, field, value):
    assert world[0].post(OWN, headers=headers(world[2]), json=body(**{field: value})).status_code == 422


def test_unicode_normalization_sql_and_html_shaped_text_stays_plain(world):
    created = create(world, title="  Cafe\u0301   桌子 😀 ", description="<script>alert('x')</script>\n' OR 1=1 --")
    assert created["title"] == "Café 桌子 😀"
    assert created["description"] == "<script>alert('x')</script>\n' OR 1=1 --"
    assert len(world[0].get(OWN, headers=headers(world[2])).json()["items"]) == 1


@pytest.mark.parametrize("field", ["title", "description", "price", "condition", "city_slug", "category_slug"])
def test_explicit_null_patch_rejected_and_omitted_fields_preserved(world, field):
    slug = create(world)["public_slug"]
    assert world[0].patch(OWN + "/" + slug, headers=headers(world[2]), json={field: None}).status_code == 422
    assert world[0].patch(OWN + "/" + slug, headers=headers(world[2]), json={}).status_code == 422


@pytest.mark.parametrize("state", ["DRAFT", "PUBLISHED", "PAUSED", "ARCHIVED"])
@pytest.mark.parametrize("operation", ["publish", "pause", "archive", "edit"])
def test_state_machine_all_combinations(world, state, operation):
    client, _, owner, _, _ = world
    slug = create(world)["public_slug"]
    if state in {"PUBLISHED", "PAUSED"}:
        assert action(world, slug, "publish").status_code == 200
    if state == "PAUSED":
        assert action(world, slug, "pause").status_code == 200
    if state == "ARCHIVED":
        assert action(world, slug, "archive").status_code == 200
    allowed = {"publish": {"DRAFT", "PAUSED"}, "pause": {"PUBLISHED"},
               "archive": {"DRAFT", "PUBLISHED", "PAUSED"}, "edit": {"DRAFT", "PUBLISHED", "PAUSED"}}
    result = (client.patch(OWN + "/" + slug, headers=headers(owner), json={"title": "Changed title"})
              if operation == "edit" else action(world, slug, operation))
    assert result.status_code == (200 if state in allowed[operation] else 409)


def lose_eligibility(db, owner, state):
    if state in {"email", "phone"}:
        setattr(owner, state + "_verified", False)
    elif state in AccountStatus.__members__:
        owner.account_status = AccountStatus[state]
    elif state == "onboarding":
        db.scalar(select(UserProfile).where(UserProfile.user_id == owner.id)).onboarding_completed = False
    elif state == "invalid-profile":
        db.scalar(select(UserProfile).where(UserProfile.user_id == owner.id)).display_name = None
    elif state == "profile":
        db.delete(db.scalar(select(UserProfile).where(UserProfile.user_id == owner.id)))
    else:
        attempt = db.scalar(select(SellerVerification).where(SellerVerification.user_id == owner.id))
        if state == "unverified":
            db.delete(attempt)
        elif state in {"pending", "under-review"}:
            attempt.status = VerificationStatus.PENDING if state == "pending" else VerificationStatus.UNDER_REVIEW
            attempt.reviewed_at = None
            if state == "pending":
                attempt.submitted_at = None
        else:
            attempt.status = VerificationStatus.REJECTED
            attempt.rejection_reason = "Synthetic revocation"
    db.commit()


@pytest.mark.parametrize("state", ["email", "phone", "onboarding", "profile", "unverified", "rejected",
                                   "pending", "under-review", "invalid-profile",
                                   "SUSPENDED", "BANNED", "DELETED"])
def test_current_eligibility_public_hiding_and_owner_cleanup(world, state):
    client, db, owner, _, _ = world
    slug = create(world)["public_slug"]
    assert action(world, slug, "publish").status_code == 200
    lose_eligibility(db, owner, state)
    expected = 401 if state in AccountStatus.__members__ else 403
    assert client.get(PUBLIC + slug).status_code == 404
    assert client.post(OWN, headers=headers(owner), json=body()).status_code == expected
    assert client.patch(OWN + "/" + slug, headers=headers(owner), json={"title": "Changed title"}).status_code == expected
    own = client.get(OWN + "/" + slug, headers=headers(owner))
    assert own.status_code == (401 if expected == 401 else 200)
    paused = action(world, slug, "pause")
    assert paused.status_code == (401 if expected == 401 else 200)
    assert action(world, slug, "publish").status_code == expected
    assert action(world, slug, "archive").status_code == (401 if expected == 401 else 200)


@pytest.mark.parametrize("kind", ["city", "category", "parent"])
def test_catalog_retirement_hides_public_preserves_history_and_can_repair(world, kind):
    client, db, owner, _, category = world
    if kind == "parent":
        parent = Category(slug="test-parent-category", name_en="Parent", name_zh="父分类")
        db.add(parent)
        db.flush()
        category.parent_id, category.parent_level, category.level = parent.id, 1, 2
        db.commit()
    slug = create(world)["public_slug"]
    assert action(world, slug, "publish").status_code == 200
    target = (db.scalar(select(City).where(City.slug == "qingdao")) if kind == "city" else
              parent if kind == "parent" else category)
    target.is_active = False
    db.commit()
    assert client.get(PUBLIC + slug).status_code == 404
    assert client.get(OWN + "/" + slug, headers=headers(owner)).status_code == 200
    assert client.patch(OWN + "/" + slug, headers=headers(owner), json={"title": "Repaired text"}).status_code == 200
    assert action(world, slug, "pause").status_code == 200
    assert action(world, slug, "publish").status_code == 422
    assert action(world, slug, "archive").status_code == 200


def test_slug_collision_is_bounded_and_only_unique_reference_is_retried(world, monkeypatch):
    first = create(world)
    monkeypatch.setattr("app.repositories.product_repository.generate_product_slug", lambda: first["public_slug"])
    failure = world[0].post(OWN, headers=headers(world[2]), json=body())
    assert failure.status_code == 503 and "SQL" not in failure.text
    choices = iter([first["public_slug"], "item-" + "a" * 24])
    monkeypatch.setattr("app.repositories.product_repository.generate_product_slug", lambda: next(choices))
    assert create(world)["public_slug"] == "item-" + "a" * 24


def test_failure_after_mutation_rolls_back_all_changes(world, monkeypatch):
    client, db, owner, _, _ = world
    slug = create(world)["public_slug"]
    def fail(*args):
        raise RuntimeError("SYNTHETIC PRIVATE DATABASE ERROR")
    monkeypatch.setattr(ProductRepository, "owned_view", fail)
    response = client.patch(OWN + "/" + slug, headers=headers(owner), json={"title": "Should roll back"})
    assert response.status_code == 503 and "SYNTHETIC" not in response.text
    db.expire_all()
    assert db.scalar(select(ProductListing.title).where(ProductListing.public_slug == slug)) == body()["title"]


def test_owner_query_budget_bounded_pagination_and_stable_ties(world):
    client, db, owner, _, _ = world
    for _ in range(4):
        create(world)
    statements = []
    connection = db.connection()
    def count(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().lower().startswith("select") and "FROM product_listings" in statement:
            statements.append(statement)
    event.listen(connection, "before_cursor_execute", count)
    try:
        first = ProductService().list_owned(db, owner.id, 2, 0)
    finally:
        event.remove(connection, "before_cursor_execute", count)
    assert len(first.items) == 2 and first.next_offset == 2 and len(statements) == 1
    second = client.get(OWN + "?limit=2&offset=2", headers=headers(owner)).json()
    assert second["next_offset"] is None and len(second["items"]) == 2
    assert not {p.public_slug for p in first.items} & {p["public_slug"] for p in second["items"]}
    for query in ("limit=0", "limit=101", "offset=-1", "offset=100001"):
        assert client.get(OWN + "?" + query, headers=headers(owner)).status_code == 422


@pytest.mark.parametrize("field,value", [("price", Decimal("0")), ("currency", "USD"), ("condition", "unknown"),
                                         ("status", "SOLD"), ("title", "a"), ("description", "short")])
def test_database_constraints_are_real_mysql(world, field, value):
    db, owner, category = world[1], world[2], world[4]
    city_id = db.scalar(select(City.id).where(City.slug == "qingdao"))
    values = dict(seller_user_id=owner.id, title="Database test", description="Database constraints test.",
                  price=Decimal("12.34"), currency="CNY", condition="good", status="DRAFT",
                  city_id=city_id, category_id=category.id)
    values[field] = value
    with pytest.raises(OperationalError) as failure, db.begin_nested():
        db.add(ProductListing(**values))
        db.flush()
    assert failure.value.orig.args[0] == 3819


def test_immutable_orm_identity_and_foreign_keys_restrict(world):
    slug = create(world)["public_slug"]
    db, owner, other, category = world[1:]
    row = db.scalar(select(ProductListing).where(ProductListing.public_slug == slug))
    db.expire(row)
    with pytest.raises(ValueError):
        row.public_slug = "item-" + "a" * 24
    with pytest.raises(ValueError):
        row.seller_user_id = other.id
    for target in (owner, category):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.delete(target)
            db.flush()


def test_malformed_json_consumes_preparse_peer_budget_and_never_echoes(world):
    client = world[0]
    for _ in range(90):
        response = client.post(OWN, content='{"PRIVATE_MALFORMED"', headers={"Content-Type": "application/json"})
        assert response.status_code == 422 and "PRIVATE_MALFORMED" not in response.text
    rejected = client.post(OWN, json=body(), headers=headers(world[2]))
    assert rejected.status_code == 429 and rejected.headers["Retry-After"]


def test_byte_limit_content_type_and_scope_boundaries(world):
    client, _, owner, _, _ = world
    assert client.post(OWN, content="x" * 32769, headers={**headers(owner), "Content-Type": "application/json"}).status_code == 413
    assert client.post(OWN, content="{}", headers={**headers(owner), "Content-Type": "text/plain"}).status_code == 415
    assert client.get("/api/v1/products").status_code == 404
    slug = create(world)["public_slug"]
    assert client.delete(OWN + "/" + slug, headers=headers(owner)).status_code == 405
    assert client.get(PUBLIC + "item-%61" + "a" * 23).status_code == 404
    assert client.post(OWN + "/" + slug + "/images", json={}).status_code == 401
    assert client.post(OWN + "/" + slug + "/images", json={}, headers=headers(owner)).status_code == 415
    for suffix in ("upload", "favorites", "chat", "deal", "search"):
        assert client.post(OWN + "/" + slug + "/" + suffix, json={}).status_code == 404


@pytest.mark.parametrize("action_name", ["publish", "pause", "archive"])
def test_action_body_cannot_assign_fields(world, action_name):
    slug = create(world)["public_slug"]
    assert world[0].post(OWN + "/" + slug + "/" + action_name, headers=headers(world[2]),
                         json={"status": "PUBLISHED"}).status_code == 422


def test_chunked_body_and_forged_auth_fail_closed(world):
    client = world[0]
    assert client.post(OWN, content=iter([b"x" * 17000, b"x" * 17000]),
                       headers={"Content-Type": "application/json"}).status_code == 413
    assert client.get(OWN, headers={"Authorization": "Bearer forged-role-token"}).status_code == 401


def test_public_peer_budget_cannot_be_spoofed(world):
    client = world[0]
    path = PUBLIC + "item-" + "0" * 24
    for _ in range(180):
        assert client.get(path).status_code == 404
    response = client.get(path, headers={"Forwarded": "for=198.51.100.1", "X-Forwarded-For": "198.51.100.2"})
    assert response.status_code == 429
