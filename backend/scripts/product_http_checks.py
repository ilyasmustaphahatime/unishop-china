"""Phase 9 extension to the existing synthetic-only live HTTP gate."""
from sqlalchemy import delete
from app.models import Category, AdminCatalogAudit


def product_category(marker):
    return "audit-product-" + marker


def run_product_checks(owner, other, check, marker):
    category = product_category(marker)
    base = "/api/v1/seller/products"
    response = other.post("/api/v1/admin/categories", json={"slug": category, "name_en": "Synthetic Listing Category",
                                                           "name_zh": "测试商品分类"})
    check(response.status_code == 201, "product-category-create")
    response = owner.post(base, json={"title": "Synthetic study desk", "description": "This is a synthetic listing test.",
                                      "price": "123.45", "condition": "good", "city_slug": "qingdao", "category_slug": category})
    check(response.status_code == 201, "product-draft-create")
    slug = response.json()["public_slug"]
    path = base + "/" + slug
    public = "/api/v1/products/" + slug
    check(response.json()["status"] == "DRAFT" and response.json()["price"] == "123.45", "product-draft-decimal")
    check(owner.patch(path, json={"title": "Synthetic updated desk"}).status_code == 200, "product-edit")
    check(other.get(public).status_code == 404, "product-draft-hidden")
    browse = other.get("/api/v1/products", params={"category": category})
    check(browse.status_code == 200 and browse.json()["items"] == [], "browse-draft-hidden")
    check(owner.post(path + "/publish", json={}).status_code == 200, "product-publish")
    detail = other.get(public)
    check(detail.status_code == 200 and detail.headers.get("cache-control") == "no-store", "product-public-detail")
    check(set(detail.json()["seller"]) == {"public_handle", "display_name", "seller_verified"}, "product-minimal-seller")
    check(not {"id", "seller_user_id", "city_id", "category_id", "email", "phone", "storage_key"} & detail.json().keys(),
          "product-public-privacy")
    browse = other.get("/api/v1/products", params={"category": category, "q": "Synthetic", "limit": 1})
    check(browse.status_code == 200 and browse.headers.get("cache-control") == "no-store" and
          [item["public_slug"] for item in browse.json()["items"]] == [slug], "browse-live-search")
    check("storage_key" not in browse.text and "seller_user_id" not in browse.text,
          "browse-live-privacy")
    check(other.get("/api/v1/products", params={"cursor": "tampered"}).status_code == 400,
          "browse-live-cursor-rejected")
    first_publication = detail.json()["published_at"]
    check(other.get(path).status_code == 404, "product-cross-owner-read")
    check(other.patch(path, json={"title": "Cross user edit"}).status_code in {403, 404}, "product-cross-owner-edit")
    check(owner.post(path + "/pause", json={}).status_code == 200, "product-pause")
    check(other.get(public).status_code == 404, "product-paused-hidden")
    check(other.get("/api/v1/products", params={"category": category}).json()["items"] == [],
          "browse-paused-hidden")
    response = owner.post(path + "/publish", json={})
    check(response.status_code == 200 and response.json()["published_at"] == first_publication, "product-republish-stable-timestamp")
    check(owner.post(path + "/archive", json={}).status_code == 200, "product-archive")
    check(other.get(public).status_code == 404, "product-archived-hidden")
    check(other.get("/api/v1/products", params={"category": category}).json()["items"] == [],
          "browse-archived-hidden")
    check(owner.post(path + "/publish", json={}).status_code == 409, "product-terminal-archive")
    check(owner.get(base).status_code == 200, "product-owner-list")


def cleanup_product_catalog(db, marker):
    slug = product_category(marker)
    db.execute(delete(AdminCatalogAudit).where(AdminCatalogAudit.resource_slug == slug))
    db.execute(delete(Category).where(Category.slug == slug))
