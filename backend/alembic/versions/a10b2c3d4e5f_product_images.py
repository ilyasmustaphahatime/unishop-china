"""Phase 10 product-media metadata; no bytes, seeds or earlier-row changes."""
from alembic import op
import sqlalchemy as sa

revision = "a10b2c3d4e5f"
down_revision = "f9a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("product_images",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("product_listing_id", sa.CHAR(36), nullable=False),
        sa.Column("public_ref", sa.String(36, collation="ascii_bin"), nullable=False),
        sa.Column("storage_key", sa.String(78, collation="ascii_bin"), nullable=False),
        sa.Column("mime_type", sa.String(16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_listing_id"], ["product_listings.id"],
                                name="fk_product_images_listing", ondelete="RESTRICT"),
        sa.UniqueConstraint("public_ref", name="uq_product_images_public_ref"),
        sa.UniqueConstraint("storage_key", name="uq_product_images_storage_key"),
        sa.UniqueConstraint("product_listing_id", "position", name="uq_product_images_listing_position"),
        sa.CheckConstraint("REGEXP_LIKE(public_ref, '^img-[0-9a-f]{32}$', 'c')", name="ck_product_images_ref"),
        sa.CheckConstraint("REGEXP_LIKE(storage_key, '^product-media/[0-9a-f]{64}$', 'c')", name="ck_product_images_key"),
        sa.CheckConstraint("mime_type IN ('image/jpeg','image/png','image/webp')", name="ck_product_images_mime"),
        sa.CheckConstraint("width BETWEEN 1 AND 6000 AND height BETWEEN 1 AND 6000", name="ck_product_images_dimensions"),
        sa.CheckConstraint("width * height <= 30000000", name="ck_product_images_pixels"),
        sa.CheckConstraint("file_size BETWEEN 1 AND 10485760", name="ck_product_images_size"),
        sa.CheckConstraint("position BETWEEN 0 AND 15", name="ck_product_images_position"))


def downgrade():
    # Disposable gate only: drops Phase 10 metadata, not physical objects.
    op.drop_table("product_images")
