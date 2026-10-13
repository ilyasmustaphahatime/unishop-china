"""Metadata persistence; no storage calls, authorization or workflow commits."""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.product_image_rules import generate_image_ref, MAX_IMAGES
from app.models.product_image import ProductImage


class ProductImageRepository:
    def list_for_product(self, db, product_id, *, locked=False):
        query = select(ProductImage).where(ProductImage.product_listing_id == product_id).order_by(ProductImage.position)
        if locked:
            query = query.with_for_update().execution_options(populate_existing=True)
        return list(db.scalars(query))

    def create(self, db, **values):
        for _ in range(8):
            try:
                with db.begin_nested():
                    row = ProductImage(public_ref=generate_image_ref(), **values)
                    db.add(row)
                    db.flush()
                return row
            except IntegrityError as error:
                if getattr(error.orig, "args", (None,))[0] != 1062 or "uq_product_images_public_ref" not in str(error.orig):
                    raise
        raise RuntimeError("Image reference generation unavailable.")

    def resequence(self, db, ordered):
        # All current images are locked by the service through the parent listing.
        for index, image in enumerate(ordered):
            image.position = MAX_IMAGES + index
        db.flush()
        for index, image in enumerate(ordered):
            image.position = index
        db.flush()

    def inventory(self, db):
        return db.execute(select(ProductImage.public_ref, ProductImage.storage_key)).all()
