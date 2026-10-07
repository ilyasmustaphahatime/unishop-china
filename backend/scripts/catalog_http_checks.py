"""Phase 8 addition to the existing synthetic-only live HTTP audit."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import City, Category, AdminCatalogAudit


def resource_slugs(marker):
    return ("audit-city-" + marker, "audit-root-" + marker, "audit-child-" + marker)


def assert_catalog_namespace_unused(engine, marker):
    city, root, child = resource_slugs(marker)
    with Session(engine) as db:
        assert db.scalar(select(City.id).where(City.slug == city)) is None
        assert db.scalar(select(Category.id).where(Category.slug.in_([root, child]))) is None
        assert db.scalar(select(AdminCatalogAudit.id).where(AdminCatalogAudit.resource_slug.in_([city, root, child]))) is None


def run_catalog_checks(member, admin, check, engine, marker, admin_id):
    city, root, child = resource_slugs(marker)
    api = "/api/v1/"
    check(admin.post(api + "admin/cities", json={"slug": city, "name_en": "Synthetic City",
        "name_zh": "测试城市", "province_en": "Synthetic Province"}).status_code == 201, "catalog-city-create")
    check(city in {row["slug"] for row in member.get(api + "cities").json()["items"]}, "catalog-city-public-list")
    check(member.patch(api + "profile/me", json={"city": city}).status_code == 200, "catalog-profile-city-assign")
    check(member.post(api + "profile/onboarding/complete", json={}).status_code == 200, "catalog-onboarding")
    for slug, parent in ((root, None), (child, root)):
        response = admin.post(api + "admin/categories", json={"slug": slug, "name_en": "Synthetic Category",
            "name_zh": "测试分类", "parent_slug": parent})
        check(response.status_code == 201, "catalog-category-create:" + ("root" if parent is None else "child"))
    tree = member.get(api + "categories").json()["items"]
    check(any(row["slug"] == root and row["children"][0]["slug"] == child for row in tree), "catalog-two-level-tree")
    check(admin.post(api + "admin/cities/" + city + "/deactivate", json={}).status_code == 200, "catalog-city-deactivate")
    check(member.patch(api + "profile/me", json={"city": city}).status_code == 422, "catalog-inactive-assignment-denied")
    profile = member.get(api + "profile/me").json()
    check(profile["city_slug"] == city and not profile["city_active"] and profile["onboarding_completed"], "catalog-historical-profile-preserved")
    check(member.get(api + "cities/" + city).status_code == 404, "catalog-inactive-city-hidden")
    for slug in (child, root):
        check(admin.post(api + "admin/categories/" + slug + "/deactivate", json={}).status_code == 200,
              "catalog-category-deactivate:" + ("child" if slug == child else "root"))
    check(not any(row["slug"] == root for row in member.get(api + "categories").json()["items"]), "catalog-inactive-tree-hidden")
    with Session(engine) as db:
        events = list(db.scalars(select(AdminCatalogAudit).where(AdminCatalogAudit.resource_slug.in_([city, root, child]))))
        check(len(events) == 6 and all(row.actor_id == admin_id for row in events), "catalog-authoritative-audit-events")


def cleanup_catalog_synthetic(db, marker):
    """Called only after removing this audit's users/profiles, never legitimate rows."""
    city, root, child = resource_slugs(marker)
    db.execute(delete(AdminCatalogAudit).where(AdminCatalogAudit.resource_slug.in_([city, root, child])))
    db.execute(delete(Category).where(Category.slug == child))
    db.execute(delete(Category).where(Category.slug == root))
    db.execute(delete(City).where(City.slug == city))
