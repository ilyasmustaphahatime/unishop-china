"""Immutable raster identity/metadata, never bytes or original filenames."""
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.common.product_image_rules import validate_image_ref
from app.core.database import Base
from app.models.base import UUIDTimestampMixin


class ProductImage(UUIDTimestampMixin, Base):
    __tablename__ = "product_images"
    __table_args__ = (
        UniqueConstraint("public_ref", name="uq_product_images_public_ref"),
        UniqueConstraint("storage_key", name="uq_product_images_storage_key"),
        UniqueConstraint("product_listing_id", "position", name="uq_product_images_listing_position"),
        CheckConstraint("REGEXP_LIKE(public_ref, '^img-[0-9a-f]{32}$', 'c')", name="ck_product_images_ref"),
        CheckConstraint("REGEXP_LIKE(storage_key, '^product-media/[0-9a-f]{64}$', 'c')", name="ck_product_images_key"),
        CheckConstraint("mime_type IN ('image/jpeg','image/png','image/webp')", name="ck_product_images_mime"),
        CheckConstraint("width BETWEEN 1 AND 6000 AND height BETWEEN 1 AND 6000", name="ck_product_images_dimensions"),
        CheckConstraint("width * height <= 30000000", name="ck_product_images_pixels"),
        CheckConstraint("file_size BETWEEN 1 AND 10485760", name="ck_product_images_size"),
        # 8..15 are reserved for transaction-local, uniqueness-safe reordering.
        CheckConstraint("position BETWEEN 0 AND 15", name="ck_product_images_position"),
    )
    product_listing_id: Mapped[str] = mapped_column(ForeignKey("product_listings.id",
        name="fk_product_images_listing", ondelete="RESTRICT"), nullable=False, active_history=True)
    public_ref: Mapped[str] = mapped_column(String(36, collation="ascii_bin"), nullable=False, active_history=True)
    storage_key: Mapped[str] = mapped_column(String(78, collation="ascii_bin"), nullable=False, active_history=True)
    mime_type: Mapped[str] = mapped_column(String(16), nullable=False, active_history=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False, active_history=True)
    height: Mapped[int] = mapped_column(Integer, nullable=False, active_history=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, active_history=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    @validates("public_ref", "storage_key", "product_listing_id", "mime_type", "width", "height", "file_size")
    def immutable_content(self, key, value):
        if key == "public_ref":
            value = validate_image_ref(value)
        previous = self.__dict__.get(key)
        if previous is not None and previous != value:
            raise ValueError("Image identity and content cannot be changed.")
        return value
