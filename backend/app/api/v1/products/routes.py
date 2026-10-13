from typing import Annotated
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.api.v1.products.dependencies import listing_user, safe_product_operation
from app.common.product_slugs import ProductSlug
from app.core.database import get_db
from app.schemas.catalog import StrictBody
from app.schemas.product import ProductCreate, ProductUpdate, OwnProduct, OwnProductList, PublicProduct
from app.services.product_service import ProductService

router = APIRouter(tags=["products"])
seller_router = APIRouter(tags=["seller-products"])


@router.get("/{slug}", response_model=PublicProduct)
def public_product(slug: ProductSlug, request: Request, db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService(api_prefix=request.app.state.settings.api_v1_prefix).get_public(db, slug)


@seller_router.post("", response_model=OwnProduct, status_code=201)
def create_product(body: ProductCreate, user=Depends(listing_user), db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService().create(db, user.id, body)


@seller_router.get("", response_model=OwnProductList)
def own_products(limit: Annotated[int, Query(ge=1, le=100)] = 20,
                 offset: Annotated[int, Query(ge=0, le=100000)] = 0,
                 user=Depends(listing_user), db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService().list_owned(db, user.id, limit, offset)


@seller_router.get("/{slug}", response_model=OwnProduct)
def own_product(slug: ProductSlug, user=Depends(listing_user), db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService().get_owned(db, user.id, slug)


@seller_router.patch("/{slug}", response_model=OwnProduct)
def edit_product(slug: ProductSlug, body: ProductUpdate, user=Depends(listing_user), db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService().update(db, user.id, slug, body)


@seller_router.post("/{slug}/publish", response_model=OwnProduct)
def publish_product(slug: ProductSlug, body: StrictBody, user=Depends(listing_user), db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService().transition(db, user.id, slug, "publish")


@seller_router.post("/{slug}/pause", response_model=OwnProduct)
def pause_product(slug: ProductSlug, body: StrictBody, user=Depends(listing_user), db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService().transition(db, user.id, slug, "pause")


@seller_router.post("/{slug}/archive", response_model=OwnProduct)
def archive_product(slug: ProductSlug, body: StrictBody, user=Depends(listing_user), db: Session = Depends(get_db)):
    with safe_product_operation():
        return ProductService().transition(db, user.id, slug, "archive")
