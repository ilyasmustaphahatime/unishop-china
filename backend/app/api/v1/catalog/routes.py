from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.catalog.dependencies import catalog_admin, safe_catalog_operation
from app.common.catalog_slugs import CatalogSlug
from app.core.database import get_db
from app.schemas.catalog import (
    CityCreate, CityUpdate, PublicCity, AdminCity, CityList, StrictBody,
    CategoryCreate, CategoryUpdate, PublicCategory, AdminCategory, CategoryList,
)
from app.services.catalog_service import CityService, CategoryService

router = APIRouter(tags=["catalog"])
admin_router = APIRouter(tags=["admin-catalog"])


@router.get("/cities", response_model=CityList)
def list_cities(db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CityList(items=CityService().list_public(db))


@router.get("/cities/{slug}", response_model=PublicCity)
def get_city(slug: CatalogSlug, db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CityService().get_public(db, slug)


@router.get("/categories", response_model=CategoryList)
def list_categories(db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CategoryList(items=CategoryService().list_public(db))


@router.get("/categories/{slug}", response_model=PublicCategory)
def get_category(slug: CatalogSlug, db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CategoryService().get_public(db, slug)


@admin_router.get("/cities", response_model=list[AdminCity])
def admin_cities(user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CityService().list_admin(db, user.id)


@admin_router.post("/cities", response_model=AdminCity, status_code=201)
def create_city(body: CityCreate, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CityService().create(db, user.id, body)


@admin_router.patch("/cities/{slug}", response_model=AdminCity)
def update_city(slug: CatalogSlug, body: CityUpdate, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CityService().update(db, user.id, slug, body)


@admin_router.post("/cities/{slug}/activate", response_model=AdminCity)
def activate_city(slug: CatalogSlug, body: StrictBody, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CityService().set_active(db, user.id, slug, True)


@admin_router.post("/cities/{slug}/deactivate", response_model=AdminCity)
def deactivate_city(slug: CatalogSlug, body: StrictBody, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CityService().set_active(db, user.id, slug, False)


@admin_router.get("/categories", response_model=list[AdminCategory])
def admin_categories(user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CategoryService().list_admin(db, user.id)


@admin_router.post("/categories", response_model=AdminCategory, status_code=201)
def create_category(body: CategoryCreate, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CategoryService().create(db, user.id, body)


@admin_router.patch("/categories/{slug}", response_model=AdminCategory)
def update_category(slug: CatalogSlug, body: CategoryUpdate, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CategoryService().update(db, user.id, slug, body)


@admin_router.post("/categories/{slug}/activate", response_model=AdminCategory)
def activate_category(slug: CatalogSlug, body: StrictBody, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CategoryService().set_active(db, user.id, slug, True)


@admin_router.post("/categories/{slug}/deactivate", response_model=AdminCategory)
def deactivate_category(slug: CatalogSlug, body: StrictBody, user=Depends(catalog_admin), db: Session = Depends(get_db)):
    with safe_catalog_operation():
        return CategoryService().set_active(db, user.id, slug, False)
