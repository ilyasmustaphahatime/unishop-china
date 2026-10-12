"""Phase 9 listing core; no existing rows are rewritten or seeded."""
from alembic import op
import sqlalchemy as sa

revision = "f9a1b2c3d4e5"
down_revision = "e8f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("product_listings",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("seller_user_id", sa.CHAR(36), nullable=False),
        sa.Column("public_slug", sa.String(29, collation="ascii_bin"), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="CNY", nullable=False),
        sa.Column("condition", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="DRAFT", nullable=False),
        sa.Column("city_id", sa.CHAR(36), nullable=False),
        sa.Column("category_id", sa.CHAR(36), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["seller_user_id"], ["users.id"], name="fk_product_listings_seller", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"], name="fk_product_listings_city", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], name="fk_product_listings_category", ondelete="RESTRICT"),
        sa.UniqueConstraint("public_slug", name="uq_product_listings_public_slug"),
        sa.CheckConstraint("REGEXP_LIKE(public_slug, '^item-[0-9a-f]{24}$', 'c')", name="ck_product_listing_slug"),
        sa.CheckConstraint("CHAR_LENGTH(TRIM(title)) BETWEEN 3 AND 120", name="ck_product_listing_title"),
        sa.CheckConstraint("CHAR_LENGTH(TRIM(description)) BETWEEN 10 AND 5000", name="ck_product_listing_description"),
        sa.CheckConstraint("price > 0 AND price <= 9999999999.99", name="ck_product_listing_price"),
        sa.CheckConstraint("currency = 'CNY'", name="ck_product_listing_currency"),
        sa.CheckConstraint("`condition` IN ('new','like_new','good','fair')", name="ck_product_listing_condition"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','PAUSED','ARCHIVED')", name="ck_product_listing_status"),
        sa.CheckConstraint("(status = 'DRAFT' AND published_at IS NULL) OR "
                           "(status IN ('PUBLISHED','PAUSED') AND published_at IS NOT NULL) OR status = 'ARCHIVED'",
                           name="ck_product_listing_publication"))
    op.create_index("ix_product_listings_owner_updated", "product_listings", ["seller_user_id", "updated_at", "id"])
    op.create_index("ix_product_listings_city", "product_listings", ["city_id"])
    op.create_index("ix_product_listings_category", "product_listings", ["category_id"])


def downgrade():
    # Destructive for Phase 9 listings only. Exercise solely in an isolated DB.
    op.drop_table("product_listings")
