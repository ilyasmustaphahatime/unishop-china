"""Real MySQL authorization, input, lifecycle and audit rollback tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, delete, event
from sqlalchemy.exc import DBAPIError
from uuid import uuid4

from app.api.v1.catalog.dependencies import admin_peer_limiter, admin_user_limiter
from app.api.v1.profiles.dependencies import profile_write_ip_limiter, profile_write_user_limiter
from app.common.enums import AccountStatus
from app.core.config import settings
from app.core.database import get_db
from app.main import create_app
from app.models import City, Category, AdminCatalogAudit, UserRole, UserProfile
from app.repositories.catalog_repository import CatalogAuditRepository
from tests.integration.test_seller_verification import make_user, headers

PUBLIC = "/api/v1/"
ADMIN = PUBLIC + "admin/"


@pytest.fixture
def world(db_session):
    for limiter in (admin_peer_limiter, admin_user_limiter, profile_write_ip_limiter, profile_write_user_limiter):
        limiter.clear()
    owner, admin = make_user(db_session), make_user(db_session, admin=True)
    # Commit the fixture savepoint, not the outer isolation transaction. Request
    # rollback must not erase the accounts used by the following request.
    db_session.commit()
    app = create_app(settings.model_copy(update={"app_debug": False}))
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db_session, owner, admin


def body(kind, slug="test-resource", **changes):
    value = {"slug": slug, "name_en": "Test Place", "name_zh": "测试"}
    if kind == "cities":
        value.update(province_en="Test Province", province_zh="测试省")
    return {**value, **changes}


def create(world, kind, slug="test-resource", **changes):
    client, _, _, admin = world
    response = client.post(ADMIN + kind, headers=headers(admin), json=body(kind, slug, **changes))
    assert response.status_code == 201, response.json()
    return response.json()


@pytest.mark.parametrize("kind", ["cities", "categories"])
def test_catalog_lifecycle_safe_contract_order_and_all_audits(world, kind):
    client, db, _, admin = world
    created = create(world, kind)
    assert not {"id", "created_at", "actor_id", "parent_id"} & created.keys()
    route = ADMIN + kind + "/test-resource"
    assert client.patch(route, headers=headers(admin), json={"name_en": "Changed 中文"}).status_code == 200
    public = client.get(PUBLIC + kind + "/test-resource")
    assert public.status_code == 200 and public.json()["name_en"] == "Changed 中文"
    assert not {"id", "sort_order", "is_active", "created_at"} & public.json().keys()
    for action in ("deactivate", "activate"):
        response = client.post(route + "/" + action, headers=headers(admin), json={})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert client.get(PUBLIC + kind + "/test-resource").status_code == (404 if action == "deactivate" else 200)
    assert client.get(PUBLIC + kind + "/unknown-resource").status_code == 404
    assert client.post(ADMIN + kind, headers=headers(admin), json=body(kind)).status_code == 409
    assert client.patch(route, headers=headers(admin), json={"slug": "rename-attempt"}).status_code == 422
    assert client.delete(route, headers=headers(admin)).status_code == 405
    events = list(db.scalars(select(AdminCatalogAudit).where(AdminCatalogAudit.resource_slug == "test-resource")))
    prefix = "CITY" if kind == "cities" else "CATEGORY"
    assert {e.action for e in events} == {prefix + suffix for suffix in ("_CREATED", "_UPDATED", "_ACTIVATED", "_DEACTIVATED")}
    assert all(e.actor_id == admin.id and e.created_at is not None for e in events)
    assert all(set(e.details) == {"fields"} for e in events)


@pytest.mark.parametrize("kind", ["cities", "categories"])
@pytest.mark.parametrize("slug", ["../qingdao", "/qingdao", "QINGDAO", "qing dao", "青岛", "admin?token=x",
                                    "%2Fadmin", "admin", "api", "a" * 64, "emoji-😀", "123", "two--dashes"])
def test_invalid_or_reserved_slug_rejected(world, kind, slug):
    client, _, _, admin = world
    response = client.post(ADMIN + kind, headers=headers(admin), json=body(kind, slug))
    assert response.status_code == 422
    assert slug not in response.text


@pytest.mark.parametrize("kind", ["cities", "categories"])
@pytest.mark.parametrize("field", ["id", "created_at", "updated_at", "created_by", "is_system", "role",
                                     "permissions", "parent_id", "admin_user_id", "actor", "action", "is_active"])
def test_catalog_mass_assignment_denied(world, kind, field):
    client, _, _, admin = world
    assert client.post(ADMIN + kind, headers=headers(admin), json={**body(kind), field: "forged"}).status_code == 422


@pytest.mark.parametrize("name", [" ", "x" * 81, "safe\x00name", "safe\u202ename", "safe\u200bname"])
def test_catalog_names_reject_unsafe_unicode(world, name):
    client, _, _, admin = world
    assert client.post(ADMIN + "cities", headers=headers(admin), json=body("cities", name_en=name)).status_code == 422


def test_catalog_names_are_parameterized_plain_text_and_china_only(world):
    client, _, _, admin = world
    assert client.post(ADMIN + "cities", headers=headers(admin), json=body("cities", country_code="US")).status_code == 422
    payload = "' OR 1=1 -- <script>"
    created = create(world, "cities", name_en=payload)
    assert created["name_en"] == payload
    assert len(client.get(PUBLIC + "cities").json()["items"]) == 7


@pytest.mark.parametrize("kind", ["cities", "categories"])
@pytest.mark.parametrize("state", ["normal", "anonymous", "revoked", "SUSPENDED", "BANNED", "DELETED"])
def test_catalog_admin_authority_comes_from_current_database(world, kind, state):
    client, db, owner, admin = world
    auth = headers(owner if state == "normal" else admin)
    if state == "anonymous":
        auth = {}
    elif state == "revoked":
        db.execute(delete(UserRole).where(UserRole.user_id == admin.id))
    elif state in AccountStatus.__members__:
        admin.account_status = AccountStatus[state]
    db.flush()
    db.commit()
    expected = 403 if state in {"normal", "revoked"} else 401
    response = client.post(ADMIN + kind, headers=auth, json=body(kind))
    assert response.status_code == expected
    listed = client.get(ADMIN + kind, headers=auth)
    assert listed.status_code == expected


@pytest.mark.parametrize("kind", ["cities", "categories"])
@pytest.mark.parametrize("action", ["create", "update", "activate", "deactivate"])
def test_every_mutation_rolls_back_when_audit_insert_fails(world, monkeypatch, kind, action):
    client, db, _, admin = world
    if action != "create":
        create(world, kind)
    model = City if kind == "cities" else Category
    before = list(db.execute(select(model.id, model.name_en, model.is_active).order_by(model.id)))
    audit_count = db.scalar(select(func.count()).select_from(AdminCatalogAudit))
    original = CatalogAuditRepository.record
    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("raw-payload-must-not-leak")
    monkeypatch.setattr(CatalogAuditRepository, "record", fail)
    path = ADMIN + kind
    if action == "create":
        response = client.post(path, headers=headers(admin), json=body(kind))
    elif action == "update":
        response = client.patch(path + "/test-resource", headers=headers(admin), json={"name_en": "Changed"})
    else:
        response = client.post(path + "/test-resource/" + action, headers=headers(admin), json={})
    assert response.status_code == 503 and "raw-payload" not in response.text
    assert list(db.execute(select(model.id, model.name_en, model.is_active).order_by(model.id))) == before
    assert db.scalar(select(func.count()).select_from(AdminCatalogAudit)) == audit_count


def test_hierarchy_depth_cycles_parent_activation_and_reparent_audit(world):
    client, db, _, admin = world
    create(world, "categories", "root-one")
    create(world, "categories", "root-two")
    create(world, "categories", "child-one", parent_slug="root-one")
    auth = headers(admin)
    assert client.post(ADMIN + "categories", headers=auth, json=body("categories", "third-level", parent_slug="child-one")).status_code == 409
    assert client.patch(ADMIN + "categories/root-one", headers=auth, json={"parent_slug": "root-one"}).status_code == 409
    assert client.patch(ADMIN + "categories/root-one", headers=auth, json={"parent_slug": "child-one"}).status_code == 409
    assert client.patch(ADMIN + "categories/child-one", headers=auth, json={"parent_slug": "unknown-parent"}).status_code == 404
    assert client.patch(ADMIN + "categories/child-one", headers=auth, json={"parent_slug": "root-two"}).status_code == 200
    assert db.scalar(select(func.count()).select_from(AdminCatalogAudit).where(AdminCatalogAudit.action == "CATEGORY_REPARENTED")) == 1
    assert client.post(ADMIN + "categories/root-two/deactivate", headers=auth, json={}).status_code == 409
    assert client.post(ADMIN + "categories/child-one/deactivate", headers=auth, json={}).status_code == 200
    assert client.post(ADMIN + "categories/root-two/deactivate", headers=auth, json={}).status_code == 200
    assert client.post(ADMIN + "categories/child-one/activate", headers=auth, json={}).status_code == 409
    assert client.get(PUBLIC + "categories/child-one").status_code == 404
    assert {row["slug"] for row in client.get(PUBLIC + "categories").json()["items"]} == {"root-one"}


def test_database_itself_rejects_third_level_and_self_cycle(world):
    _, db, *_ = world
    create(world, "categories", "root-one")
    create(world, "categories", "child-one", parent_slug="root-one")
    child = db.scalar(select(Category).where(Category.slug == "child-one"))
    with pytest.raises(DBAPIError), db.begin_nested():
        db.add(Category(slug="grandchild", name_en="Grandchild", name_zh="子", parent_id=child.id,
                        parent_level=1, level=2))
        db.flush()
    root = db.scalar(select(Category).where(Category.slug == "root-one"))
    with pytest.raises(DBAPIError), db.begin_nested():
        root.parent_id, root.parent_level, root.level = root.id, 1, 2
        db.flush()


def test_database_rejects_incomplete_composite_parent_reference(world):
    _, db, *_ = world
    with pytest.raises(DBAPIError), db.begin_nested():
        db.add(Category(slug="orphan-bypass", name_en="Invalid", name_zh="测试",
                        parent_id=str(uuid4()), parent_level=None, level=2))
        db.flush()


def test_dynamic_profile_city_and_deactivation_preserve_completed_onboarding(world):
    client, db, owner, admin = world
    create(world, "cities", "new-city")
    auth = headers(owner)
    profile = client.patch(PUBLIC + "profile/me", headers=auth, json={"display_name": "Member", "city": "new-city"})
    assert profile.status_code == 200 and profile.json()["city_slug"] == "new-city"
    assert client.post(PUBLIC + "profile/onboarding/complete", headers=auth, json={}).status_code == 200
    assert client.post(ADMIN + "cities/new-city/deactivate", headers=headers(admin), json={}).status_code == 200
    historical = client.get(PUBLIC + "profile/me", headers=auth).json()
    assert historical["city"] == "Test Place" and historical["city_slug"] == "new-city"
    assert historical["city_active"] is False and historical["onboarding_completed"] is True
    assert client.patch(PUBLIC + "profile/me", headers=auth, json={"bio": "Still valid"}).status_code == 200
    assert client.patch(PUBLIC + "profile/me", headers=auth, json={"city": "new-city"}).status_code == 422
    assert client.patch(PUBLIC + "profile/me", headers=auth, json={"city": "unknown-city"}).status_code == 422
    assert client.post(PUBLIC + "profile/onboarding/complete", headers=auth, json={}).status_code == 200
    assert client.get(PUBLIC + "profiles/by-handle/" + historical["public_handle"]).json()["city"] == "Test Place"
    assert db.scalar(select(UserProfile.city_id).where(UserProfile.user_id == owner.id)) is not None


@pytest.mark.parametrize("kind", ["cities", "categories"])
def test_invalid_json_and_spoofed_forwarding_cannot_bypass_peer_budget(world, kind):
    client, _, _, admin = world
    for _ in range(90):
        assert client.post(ADMIN + kind, content=b"{", headers={**headers(admin), "Content-Type": "application/json"}).status_code == 422
    response = client.post(ADMIN + kind, content=b"{", headers={**headers(admin), "Content-Type": "application/json", "X-Forwarded-For": "198.51.100.42"})
    assert response.status_code == 429 and response.headers["cache-control"] == "no-store"
    assert int(response.headers["retry-after"]) > 0


def test_public_catalog_query_counts_are_constant_and_order_is_stable(world):
    client, db, *_ = world
    create(world, "categories", "root-two", sort_order=20)
    create(world, "categories", "root-one", sort_order=10)
    create(world, "categories", "child-one", parent_slug="root-one")
    queries = []
    connection = db.get_bind()
    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            queries.append(statement)
    event.listen(connection, "before_cursor_execute", capture)
    try:
        tree = client.get(PUBLIC + "categories").json()["items"]
        assert len(queries) == 1
        assert [row["slug"] for row in tree] == ["root-one", "root-two"]
        assert tree[0]["children"][0]["slug"] == "child-one"
        queries.clear()
        assert len(client.get(PUBLIC + "cities").json()["items"]) == 6
        assert len(queries) == 1
    finally:
        event.remove(connection, "before_cursor_execute", capture)


@pytest.mark.parametrize("kind", ["cities", "categories"])
def test_audit_commit_failure_rolls_back_catalog_mutation(world, monkeypatch, kind):
    client, db, _, admin = world
    create(world, kind)
    def fail():
        raise RuntimeError("commit detail must not escape")
    monkeypatch.setattr(db, "commit", fail)
    response = client.patch(ADMIN + kind + "/test-resource", headers=headers(admin), json={"name_en": "Lost"})
    assert response.status_code == 503
    model = City if kind == "cities" else Category
    assert db.scalar(select(model.name_en).where(model.slug == "test-resource")) == "Test Place"
    assert db.scalar(select(func.count()).select_from(AdminCatalogAudit)) == 1


def test_reparent_audit_failure_rolls_back_relationship(world, monkeypatch):
    client, db, _, admin = world
    create(world, "categories", "root-one")
    create(world, "categories", "root-two")
    create(world, "categories", "child-one", parent_slug="root-one")
    original = db.scalar(select(Category.parent_id).where(Category.slug == "child-one"))
    def fail(*_args, **_kwargs):
        raise RuntimeError("controlled audit failure")
    monkeypatch.setattr(CatalogAuditRepository, "record", fail)
    response = client.patch(ADMIN + "categories/child-one", headers=headers(admin), json={"parent_slug": "root-two"})
    assert response.status_code == 503
    assert db.scalar(select(Category.parent_id).where(Category.slug == "child-one")) == original


def test_first_onboarding_completion_rejects_inactive_city_but_retains_data(world):
    client, _, owner, admin = world
    create(world, "cities", "new-city")
    assigned = client.patch(PUBLIC + "profile/me", headers=headers(owner), json={"display_name": "New User", "city": "new-city"})
    assert assigned.status_code == 200
    retired = client.post(ADMIN + "cities/new-city/deactivate", headers=headers(admin), json={})
    assert retired.status_code == 200
    response = client.post(PUBLIC + "profile/onboarding/complete", headers=headers(owner), json={})
    assert response.status_code == 409
    current = client.get(PUBLIC + "profile/me", headers=headers(owner)).json()
    assert current["city_slug"] == "new-city" and not current["onboarding_completed"]


@pytest.mark.parametrize("kind", ["cities", "categories"])
def test_encoded_paths_and_oversized_chunked_bodies_fail_closed(world, kind):
    client, _, _, admin = world
    response = client.get(PUBLIC + kind + "/%61dmin")
    assert response.status_code == 404
    response = client.post(ADMIN + kind, content=iter([b"x" * 9000, b"x" * 9000]),
                           headers={**headers(admin), "Content-Type": "application/json"})
    assert response.status_code == 413 and response.headers["cache-control"] == "no-store"


def test_public_peer_budget_cannot_be_spoofed(world):
    client, *_ = world
    for _ in range(180):
        assert client.get(PUBLIC + "cities").status_code == 200
    response = client.get(PUBLIC + "categories", headers={"Forwarded": "for=198.51.100.1"})
    assert response.status_code == 429
