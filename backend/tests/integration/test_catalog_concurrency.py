"""Independent MySQL transactions; exact synthetic ownership and cleanup."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, func
from sqlalchemy.orm import Session

from app.common.enums import UserRoleType
from app.core.database import engine
from app.models import User, UserRole, UserProfile, City, Category, AdminCatalogAudit
from app.schemas.catalog import CityCreate, CityUpdate, CategoryCreate, CategoryUpdate
from app.schemas.profile import ProfileUpdateRequest
from app.services.catalog_service import CityService, CategoryService, CatalogError
from app.services.profile_service import ProfileService


@pytest.fixture
def world():
    prefix = "p8-" + uuid4().hex
    users = [str(uuid4()) for _ in range(3)]
    with Session(engine) as db, db.begin():
        assert db.scalar(select(City.id).where(City.slug.startswith(prefix))) is None
        assert db.scalar(select(Category.id).where(Category.slug.startswith(prefix))) is None
        for index, user_id in enumerate(users):
            db.add(User(id=user_id, email=f"{prefix}-{index}@example.test", password_hash="unused"))
        db.flush()
        for admin_id in users[:2]:
            db.add(UserRole(user_id=admin_id, role=UserRoleType.ADMIN))
    try:
        yield prefix, users
    finally:
        with Session(engine) as db, db.begin():
            db.execute(delete(AdminCatalogAudit).where(AdminCatalogAudit.actor_id.in_(users)))
            db.execute(delete(User).where(User.id.in_(users)))
            db.execute(delete(Category).where(Category.slug.startswith(prefix), Category.parent_id.is_not(None)))
            db.execute(delete(Category).where(Category.slug.startswith(prefix)))
            db.execute(delete(City).where(City.slug.startswith(prefix)))


def call(operation):
    with Session(engine) as db:
        try:
            return operation(db)
        except CatalogError as exc:
            return exc.status


def race(first, second):
    barrier = Barrier(2)
    def worker(operation):
        barrier.wait(timeout=10)
        return call(operation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, operation) for operation in (first, second)]
        return [future.result(timeout=20) for future in futures]


def city(slug):
    return CityCreate(slug=slug, name_en="Synthetic City", name_zh="测试城市", province_en="Test")


def category(slug, parent=None):
    return CategoryCreate(slug=slug, name_en="Synthetic Category", name_zh="测试分类", parent_slug=parent)


@pytest.mark.parametrize("kind", ["city", "category"])
def test_duplicate_catalog_creation_race_has_one_row_and_audit(world, kind):
    prefix, (first, second, _) = world
    service, model, request = ((CityService(), City, city(prefix)) if kind == "city"
                               else (CategoryService(), Category, category(prefix)))
    outcomes = race(lambda db: service.create(db, first, request), lambda db: service.create(db, second, request))
    assert outcomes.count(409) == 1
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(model).where(model.slug == prefix)) == 1
        assert db.scalar(select(func.count()).select_from(AdminCatalogAudit).where(AdminCatalogAudit.resource_slug == prefix)) == 1


def test_city_deactivation_racing_assignment_serializes_without_corruption(world):
    prefix, (admin, _, owner) = world
    call(lambda db: CityService().create(db, admin, city(prefix)))
    outcomes = race(lambda db: CityService().set_active(db, admin, prefix, False),
                    lambda db: ProfileService().update_own(db, user_id=owner,
                        request=ProfileUpdateRequest(display_name="Test Person", city=prefix)))
    assert not isinstance(outcomes[0], int)
    with Session(engine) as db:
        selected = db.scalar(select(City).where(City.slug == prefix))
        profile = db.scalar(select(UserProfile).where(UserProfile.user_id == owner))
        assert selected.is_active is False
        if outcomes[1] == 422:
            assert profile is None or profile.city_id is None
        else:
            assert profile.city_id == selected.id and profile.city == selected.name_en


def test_opposing_reparent_race_cannot_create_a_cycle(world):
    prefix, (admin, other, _) = world
    a, b = prefix + "-a", prefix + "-b"
    service = CategoryService()
    call(lambda db: service.create(db, admin, category(a)))
    call(lambda db: service.create(db, admin, category(b)))
    outcomes = race(lambda db: service.update(db, admin, a, CategoryUpdate(parent_slug=b)),
                    lambda db: service.update(db, other, b, CategoryUpdate(parent_slug=a)))
    assert outcomes.count(409) == 1
    with Session(engine) as db:
        rows = list(db.scalars(select(Category).where(Category.slug.in_([a, b]))))
        assert sorted(row.level for row in rows) == [1, 2]
        assert sum(row.parent_id is None for row in rows) == 1
        assert db.scalar(select(func.count()).select_from(AdminCatalogAudit).where(
            AdminCatalogAudit.resource_slug.in_([a, b]), AdminCatalogAudit.action == "CATEGORY_REPARENTED")) == 1


def test_category_parent_deactivation_racing_child_creation_has_valid_active_state(world):
    prefix, (admin, other, _) = world
    service = CategoryService()
    call(lambda db: service.create(db, admin, category(prefix)))
    outcomes = race(lambda db: service.set_active(db, admin, prefix, False),
                    lambda db: service.create(db, other, category(prefix + "-child", prefix)))
    assert outcomes.count(409) == 1
    with Session(engine) as db:
        root = db.scalar(select(Category).where(Category.slug == prefix))
        child = db.scalar(select(Category).where(Category.slug == prefix + "-child"))
        assert (root.is_active and child is not None) or (not root.is_active and child is None)


def test_admin_metadata_update_race_preserves_both_disjoint_updates_and_audits(world):
    prefix, (admin, other, _) = world
    service = CityService()
    call(lambda db: service.create(db, admin, city(prefix)))
    outcomes = race(lambda db: service.update(db, admin, prefix, CityUpdate(name_en="Updated City")),
                    lambda db: service.update(db, other, prefix, CityUpdate(province_en="Updated Province")))
    assert all(not isinstance(value, int) for value in outcomes)
    with Session(engine) as db:
        row = db.scalar(select(City).where(City.slug == prefix))
        assert row.name_en == "Updated City" and row.province_en == "Updated Province"
        assert db.scalar(select(func.count()).select_from(AdminCatalogAudit).where(
            AdminCatalogAudit.resource_slug == prefix, AdminCatalogAudit.action == "CITY_UPDATED")) == 2


@pytest.mark.parametrize("service,make_request", [(CityService, city), (CategoryService, category)])
def test_activation_race_is_serialized_and_both_successes_are_audited(world, service, make_request):
    prefix, (admin, other, _) = world
    instance = service()
    call(lambda db: instance.create(db, admin, make_request(prefix)))
    outcomes = race(lambda db: instance.set_active(db, admin, prefix, True),
                    lambda db: instance.set_active(db, other, prefix, False))
    assert all(not isinstance(value, int) for value in outcomes)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AdminCatalogAudit).where(
            AdminCatalogAudit.resource_slug == prefix)) == 3
