"""Independent real MySQL transactions; exact synthetic cleanup, no process mutex."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session
from app.common.enums import AccountStatus, UserRoleType
from app.core.authorization import AuthorizationError, lock_active_user
from app.core.database import engine
from app.models import ProductListing, User, UserRole, Category, City, AdminCatalogAudit, SellerVerification, UserProfile
from app.models.seller_verification import VerificationStatus
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.catalog_service import CityService, CategoryService, CatalogError
from app.services.product_service import ProductService, ProductError
from tests.integration.test_product_listings import eligible_user


@pytest.fixture
def world():
    prefix = "p9-" + uuid4().hex
    users = []
    with Session(engine) as db, db.begin():
        for _ in range(3):
            users.append(eligible_user(db).id)
        db.add(UserRole(user_id=users[2], role=UserRoleType.ADMIN))
        db.add(City(slug=prefix, name_en="Synthetic Product City", name_zh="测试城市", province_en="Test"))
        db.add(Category(slug=prefix, name_en="Synthetic Product Category", name_zh="测试分类"))
    request = ProductCreate(title="Synthetic study desk", description="Only a synthetic test listing.",
                            price="123.45", condition="good", city_slug=prefix, category_slug=prefix)
    try:
        yield prefix, users, request
    finally:
        with Session(engine) as db, db.begin():
            db.execute(delete(ProductListing).where(ProductListing.seller_user_id.in_(users)))
            db.execute(delete(AdminCatalogAudit).where(AdminCatalogAudit.actor_id.in_(users)))
            db.execute(delete(User).where(User.id.in_(users)))
            db.execute(delete(Category).where(Category.slug == prefix))
            db.execute(delete(City).where(City.slug == prefix))


def call(operation):
    with Session(engine) as db:
        try:
            return operation(db)
        except (ProductError, CatalogError, AuthorizationError) as error:
            return error.status


def race(*operations):
    barrier = Barrier(len(operations))
    def worker(operation):
        barrier.wait(timeout=10)
        return call(operation)
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        futures = [pool.submit(worker, op) for op in operations]
        return [f.result(timeout=25) for f in futures]


@pytest.mark.parametrize("first,second,initial", [
    ("publish", "publish", "DRAFT"), ("publish", "pause", "DRAFT"),
    ("publish", "archive", "DRAFT"), ("pause", "archive", "PUBLISHED"),
    ("edit", "archive", "DRAFT"), ("publish", "pause", "PAUSED"),
])
def test_lifecycle_races_have_only_valid_serial_outcomes(world, first, second, initial):
    _, users, request = world
    owner = users[0]
    service = ProductService()
    slug = call(lambda db: service.create(db, owner, request)).public_slug
    if initial in {"PUBLISHED", "PAUSED"}:
        call(lambda db: service.transition(db, owner, slug, "publish"))
    if initial == "PAUSED":
        call(lambda db: service.transition(db, owner, slug, "pause"))
    def operation(action):
        return (lambda db: service.update(db, owner, slug, ProductUpdate(title="Concurrent edited title"))) if action == "edit" else (
            lambda db: service.transition(db, owner, slug, action))
    outcomes = race(operation(first), operation(second))
    assert all(not isinstance(value, int) or value == 409 for value in outcomes)
    if first == second:
        assert outcomes.count(409) == 1
    with Session(engine) as db:
        row = db.scalar(select(ProductListing).where(ProductListing.public_slug == slug))
        assert row.status in {"PUBLISHED", "PAUSED", "ARCHIVED"}
        if "archive" in (first, second):
            assert row.status == "ARCHIVED"
        if row.status in {"PUBLISHED", "PAUSED"}:
            assert row.published_at is not None


@pytest.mark.parametrize("kind", ["city", "category"])
def test_catalog_deactivation_vs_publish_is_current_and_publicly_hidden(world, kind):
    prefix, (owner, _, admin), request = world
    slug = call(lambda db: ProductService().create(db, owner, request)).public_slug
    catalog = CityService() if kind == "city" else CategoryService()
    outcomes = race(lambda db: ProductService().transition(db, owner, slug, "publish"),
                    lambda db: catalog.set_active(db, admin, prefix, False))
    assert not isinstance(outcomes[1], int)
    assert not isinstance(outcomes[0], int) or outcomes[0] == 422
    assert call(lambda db: ProductService().get_public(db, slug)) == 404
    with Session(engine) as db:
        row = db.scalar(select(ProductListing).where(ProductListing.public_slug == slug))
        assert row.status == ("DRAFT" if outcomes[0] == 422 else "PUBLISHED")


def test_slug_collision_across_distinct_sellers_retries_database_constraint(world, monkeypatch):
    _, (first, second, _), request = world
    shared = "item-" + "c" * 24
    from app.common.product_slugs import generate_product_slug
    from threading import local
    thread = local()
    def slug():
        count = getattr(thread, "count", 0)
        thread.count = count + 1
        return shared if count == 0 else generate_product_slug()
    monkeypatch.setattr("app.repositories.product_repository.generate_product_slug", slug)
    outcomes = race(lambda db: ProductService().create(db, first, request),
                    lambda db: ProductService().create(db, second, request))
    assert all(not isinstance(value, int) for value in outcomes)
    assert len({value.public_slug for value in outcomes}) == 2
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ProductListing).where(
            ProductListing.seller_user_id.in_([first, second]))) == 2


@pytest.mark.parametrize("kind", ["city", "category", "eligibility"])
def test_preexisting_repeatable_read_snapshot_cannot_authorize_stale_assignment(world, kind):
    prefix, (owner, _, admin), request = world
    with Session(engine) as stale:
        stale.scalar(select(User).where(User.id == owner))
        stale.scalar(select(City).where(City.slug == prefix))
        stale.scalar(select(Category).where(Category.slug == prefix))
        if kind == "eligibility":
            with Session(engine) as current, current.begin():
                lock_active_user(current, owner).email_verified = False
        else:
            catalog = CityService() if kind == "city" else CategoryService()
            call(lambda db: catalog.set_active(db, admin, prefix, False))
        with pytest.raises(AuthorizationError if kind == "eligibility" else CatalogError) as denied:
            ProductService().create(stale, owner, request)
        assert denied.value.status == (403 if kind == "eligibility" else 422)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ProductListing).where(ProductListing.seller_user_id == owner)) == 0


def test_disjoint_partial_edits_preserve_both_fields(world):
    _, (owner, _, _), request = world
    slug = call(lambda db: ProductService().create(db, owner, request)).public_slug
    results = race(lambda db: ProductService().update(db, owner, slug, ProductUpdate(title="New title from race")),
                   lambda db: ProductService().update(db, owner, slug, ProductUpdate(price="88.88")))
    assert all(not isinstance(value, int) for value in results)
    current = call(lambda db: ProductService().get_owned(db, owner, slug))
    assert current.title == "New title from race" and current.price == "88.88"


@pytest.mark.parametrize("kind", ["account", "verification", "onboarding", "city", "category"])
def test_stale_identity_map_cannot_publish_existing_draft(world, kind):
    prefix, (owner, _, admin), request = world
    slug = call(lambda db: ProductService().create(db, owner, request)).public_slug
    with Session(engine) as stale:
        # Retain actual ORM objects and a REPEATABLE READ snapshot before revocation.
        cached = [stale.scalar(select(model).where(predicate)) for model, predicate in (
            (User, User.id == owner), (SellerVerification, SellerVerification.user_id == owner),
            (UserProfile, UserProfile.user_id == owner), (City, City.slug == prefix),
            (Category, Category.slug == prefix), (ProductListing, ProductListing.public_slug == slug),
        )]
        assert all(cached)
        if kind in {"city", "category"}:
            catalog = CityService() if kind == "city" else CategoryService()
            call(lambda db: catalog.set_active(db, admin, prefix, False))
        else:
            with Session(engine) as current, current.begin():
                if kind == "account":
                    current.get(User, owner).account_status = AccountStatus.SUSPENDED
                elif kind == "verification":
                    row = current.scalar(select(SellerVerification).where(SellerVerification.user_id == owner))
                    row.status = VerificationStatus.REJECTED
                    row.rejection_reason = "Synthetic audit revocation"
                else:
                    current.scalar(select(UserProfile).where(UserProfile.user_id == owner)).onboarding_completed = False
        with pytest.raises((AuthorizationError, ProductError, CatalogError)) as denied:
            ProductService().transition(stale, owner, slug, "publish")
        assert denied.value.status == (401 if kind == "account" else 422 if kind in {"city", "category"} else 403)
    with Session(engine) as db:
        row = db.scalar(select(ProductListing).where(ProductListing.public_slug == slug))
        assert row.status == "DRAFT" and row.published_at is None
    assert call(lambda db: ProductService().get_public(db, slug)) == 404


def test_edit_vs_publish_preserves_both_content_and_publication(world):
    _, (owner, _, _), request = world
    slug = call(lambda db: ProductService().create(db, owner, request)).public_slug
    results = race(lambda db: ProductService().update(db, owner, slug, ProductUpdate(title="Edited during publication")),
                   lambda db: ProductService().transition(db, owner, slug, "publish"))
    assert all(not isinstance(value, int) for value in results)
    current = call(lambda db: ProductService().get_owned(db, owner, slug))
    assert current.status == "PUBLISHED" and current.published_at is not None
    assert current.title == "Edited during publication"
