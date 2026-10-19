"""Phase 12 private favorites/history; additive and without development data rewrites."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "c12d3e4f5a6b"
down_revision = "b11b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_favorites",
        sa.Column("user_id", sa.CHAR(36), nullable=False),
        sa.Column("product_listing_id", sa.CHAR(36), nullable=False),
        sa.Column("favorited_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "product_listing_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_product_favorites_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_listing_id"], ["product_listings.id"],
                                name="fk_product_favorites_listing", ondelete="CASCADE"),
    )
    op.create_index("ix_product_favorites_user_time", "product_favorites",
                    ["user_id", "favorited_at", "product_listing_id"])
    op.create_index("ix_product_favorites_listing", "product_favorites", ["product_listing_id"])
    op.create_table(
        "product_recent_views",
        sa.Column("user_id", sa.CHAR(36), nullable=False),
        sa.Column("product_listing_id", sa.CHAR(36), nullable=False),
        sa.Column("last_viewed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "product_listing_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_product_recent_views_user", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_listing_id"], ["product_listings.id"],
                                name="fk_product_recent_views_listing", ondelete="CASCADE"),
    )
    op.create_index("ix_product_recent_views_user_time", "product_recent_views",
                    ["user_id", "last_viewed_at", "product_listing_id"])
    op.create_index("ix_product_recent_views_listing", "product_recent_views", ["product_listing_id"])


def downgrade():
    # Disposable migration-test databases only; never downgrade development data.
    op.drop_table("product_recent_views")
    op.drop_table("product_favorites")
