"""Parent-locked media policy, metadata transactions and storage compensation."""
import hashlib
import logging

from app.common.product_image_rules import MAX_IMAGES, generate_storage_key
from app.core.authorization import lock_active_user
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.models.product import ProductStatus
from app.repositories.product_image_repository import ProductImageRepository
from app.schemas.product_image import OwnProductImage
from app.services.product_service import ProductService, ProductError
from app.services.product_image_sanitizer import (
    bounded_image_read, sanitize_product_image, UnsafeProductImage, ImageProcessingBusy,
)

logger = logging.getLogger(__name__)


class ProductImageError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class ProductImageService:
    def __init__(self, storage, *, repository=None, api_prefix="/api/v1"):
        self.storage = storage
        self.repo = repository or ProductImageRepository()
        self.products = ProductService(api_prefix=api_prefix)
        self.api_prefix = api_prefix

    def owned(self, db, user_id, slug, *, selling=False):
        if selling:
            self.products.eligible(db, user_id)
        else:
            lock_active_user(db, user_id)
        product = self.products.owned(db, user_id, slug)
        if selling and product.status == ProductStatus.ARCHIVED:
            raise ProductImageError("Archived listings cannot receive or reorder images.")
        return product

    def response(self, product, image):
        return OwnProductImage(ref=image.public_ref, position=image.position,
            url=f"{self.api_prefix}/seller/products/{product.public_slug}/images/{image.public_ref}",
            mime_type=image.mime_type, width=image.width, height=image.height,
            file_size=image.file_size, created_at=image.created_at)

    def list_owned(self, db, user_id, slug):
        with transaction(db):
            product = self.owned(db, user_id, slug)
            return [self.response(product, image) for image in self.repo.list_for_product(db, product.id, locked=True)]

    def _upload_context(self, db, user_id, slug):
        product = self.owned(db, user_id, slug, selling=True)
        images = self.repo.list_for_product(db, product.id, locked=True)
        if len(images) >= MAX_IMAGES:
            raise ProductImageError("A listing can have at most eight images.")
        return product, images

    @retry_deadlock
    def preflight_upload(self, db, user_id, slug):
        # Cheap read-only admission; release all locks/connections before slow
        # HTTP input. Upload and final metadata still reacquire/recheck rules.
        with transaction(db):
            self._upload_context(db, user_id, slug)

    def upload(self, db, user_id, slug, stream):
        key, saved, ref = None, False, None
        try:
            with transaction(db):
                self._upload_context(db, user_id, slug)
                try:
                    clean = sanitize_product_image(bounded_image_read(stream))
                except UnsafeProductImage:
                    raise ProductImageError("Use a safe static JPEG, PNG or WebP within image limits.", 422) from None
                except ImageProcessingBusy:
                    raise ProductImageError("Image processing is temporarily unavailable.", 503) from None
                key = generate_storage_key()
                self.storage.save(key, clean.data)
                saved = True
            # Storage is never retried. Reacquire/recheck authority and quota in
            # a separate pure-DB transaction; InnoDB can deadlock unique inserts
            # even across different products. The private object has no public
            # authority until this final metadata commit succeeds.
            result = self._insert_metadata(db, user_id, slug, key, clean)
            ref = result.ref
            return result
        except Exception:
            # The adapter owns incomplete-save cleanup. Do not delete a pre-existing
            # key if an exclusive save failed (e.g. a random-key collision).
            if saved:
                try:
                    self.storage.delete(key)
                except Exception:
                    logger.error("PRODUCT_IMAGE_UPLOAD_COMPENSATION_FAILED ref=%s", ref or "unassigned")
            raise

    @retry_deadlock
    def _insert_metadata(self, db, user_id, slug, key, clean):
        with transaction(db):
            product, images = self._upload_context(db, user_id, slug)
            image = self.repo.create(db, product_listing_id=product.id, storage_key=key,
                mime_type=clean.mime_type, width=clean.width, height=clean.height,
                file_size=len(clean.data), position=len(images))
            product.updated_at = utc_now()
            return self.response(product, image)

    @retry_deadlock
    def reorder(self, db, user_id, slug, body):
        with transaction(db):
            product = self.owned(db, user_id, slug, selling=True)
            images = self.repo.list_for_product(db, product.id, locked=True)
            by_ref = {image.public_ref: image for image in images}
            if len(body.images) != len(images) or set(body.images) != set(by_ref):
                raise ProductImageError("Send exactly the current image references.", 409)
            ordered = [by_ref[ref] for ref in body.images]
            self.repo.resequence(db, ordered)
            product.updated_at = utc_now()
            return [self.response(product, image) for image in ordered]

    @retry_deadlock
    def _delete_metadata(self, db, user_id, slug, ref):
        with transaction(db):
            product = self.owned(db, user_id, slug)
            images = self.repo.list_for_product(db, product.id, locked=True)
            image = next((image for image in images if image.public_ref == ref), None)
            if image is None:
                raise ProductImageError("Image not found.", 404)
            key = image.storage_key
            remaining = [row for row in images if row is not image]
            db.delete(image)
            db.flush()
            self.repo.resequence(db, remaining)
            product.updated_at = utc_now()
            return key

    def delete(self, db, user_id, slug, ref):
        key = self._delete_metadata(db, user_id, slug, ref)
        try:
            self.storage.delete(key)
        except Exception:
            # Metadata is committed: never restore visibility to compensate cleanup.
            logger.error("PRODUCT_IMAGE_DELETE_CLEANUP_FAILED ref=%s", ref)

    def _bytes(self, image):
        try:
            data = self.storage.read(image.storage_key)
        except FileNotFoundError:
            raise ProductImageError("Image not found.", 404) from None
        if len(data) != image.file_size:
            raise ProductImageError("Image temporarily unavailable.", 503)
        return data, image.mime_type

    def read_owned(self, db, user_id, slug, ref):
        with transaction(db):
            product = self.owned(db, user_id, slug)
            image = next((row for row in self.repo.list_for_product(db, product.id, locked=True)
                          if row.public_ref == ref), None)
            if image is None:
                raise ProductImageError("Image not found.", 404)
            return self._bytes(image)

    def read_public(self, db, slug, ref):
        try:
            view = self.products.public_view(db, slug)
        except ProductError as error:
            if error.status == 404:
                raise ProductImageError("Image not found.", 404) from None
            raise
        image = next((row for row in self.repo.list_for_product(db, view[0].id)
                      if row.public_ref == ref), None)
        if image is None:
            raise ProductImageError("Image not found.", 404)
        return self._bytes(image)

    def audit(self, db):
        """Report only. Do not mutate DB/files or print internal keys/paths."""
        rows = self.repo.inventory(db)
        expected = {key for _, key in rows}
        issues = []
        for ref, key in rows:
            try:
                if not self.storage.exists(key):
                    issues.append({"ref": ref, "problem": "missing_object"})
            except OSError:
                issues.append({"ref": ref, "problem": "unreadable_object"})
        for key in self.storage.keys():
            if key not in expected:
                issues.append({"object_fingerprint": hashlib.sha256(key.encode()).hexdigest()[:16],
                               "problem": "orphan_object"})
        return {"image_rows": len(rows), "issues": issues, "report_only": True}
