from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.products.dependencies import listing_user
from app.api.v1.products.image_dependencies import image_file, image_service, safe_image_operation
from app.common.product_image_rules import ImageRef
from app.common.product_slugs import ProductSlug
from app.core.database import get_db
from app.schemas.product_image import OwnProductImage, ProductImageOrder

public_router = APIRouter(tags=["product-images"])
owner_router = APIRouter(tags=["seller-product-images"])

MEDIA_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache",
                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
MULTIPART_SCHEMA = {"requestBody": {"required": True, "content": {"multipart/form-data": {
    "schema": {"type": "object", "additionalProperties": False, "required": ["file"],
               "properties": {"file": {"type": "string", "format": "binary"}}}}}}}


@owner_router.post("/{slug}/images", response_model=OwnProductImage, status_code=201,
                   openapi_extra=MULTIPART_SCHEMA)
def upload_image(slug: ProductSlug, file=Depends(image_file, scope="function"), user=Depends(listing_user),
                 service=Depends(image_service), db: Session = Depends(get_db)):
    with safe_image_operation():
        return service.upload(db, user.id, slug, file)


@owner_router.get("/{slug}/images", response_model=list[OwnProductImage])
def list_images(slug: ProductSlug, user=Depends(listing_user), service=Depends(image_service),
                db: Session = Depends(get_db)):
    with safe_image_operation():
        return service.list_owned(db, user.id, slug)


@owner_router.patch("/{slug}/images/order", response_model=list[OwnProductImage])
def reorder_images(slug: ProductSlug, body: ProductImageOrder, user=Depends(listing_user),
                   service=Depends(image_service), db: Session = Depends(get_db)):
    with safe_image_operation():
        return service.reorder(db, user.id, slug, body)


@owner_router.delete("/{slug}/images/{image_ref}", status_code=204)
def delete_image(slug: ProductSlug, image_ref: ImageRef, user=Depends(listing_user),
                 service=Depends(image_service), db: Session = Depends(get_db)):
    with safe_image_operation():
        service.delete(db, user.id, slug, image_ref)
    return Response(status_code=204, headers=MEDIA_HEADERS)


@owner_router.get("/{slug}/images/{image_ref}", responses={200: {
    "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "image/png", "image/webp")}}}, response_class=Response)
def owner_image(slug: ProductSlug, image_ref: ImageRef, user=Depends(listing_user),
                service=Depends(image_service), db: Session = Depends(get_db)):
    with safe_image_operation():
        data, mime = service.read_owned(db, user.id, slug, image_ref)
    return Response(content=data, media_type=mime, headers=MEDIA_HEADERS)


@public_router.get("/{slug}/images/{image_ref}", responses={200: {
    "content": {mime: {"schema": {"type": "string", "format": "binary"}}
                for mime in ("image/jpeg", "image/png", "image/webp")}}}, response_class=Response)
def public_image(slug: ProductSlug, image_ref: ImageRef, service=Depends(image_service),
                 db: Session = Depends(get_db)):
    with safe_image_operation():
        data, mime = service.read_public(db, slug, image_ref)
    return Response(content=data, media_type=mime, headers=MEDIA_HEADERS)
