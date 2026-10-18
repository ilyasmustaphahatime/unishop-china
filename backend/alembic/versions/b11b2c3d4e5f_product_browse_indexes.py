"""Additive Phase 11B browse and Unicode-search indexes; no data rewrite."""
from alembic import op

revision = "b11b2c3d4e5f"
down_revision = "a10b2c3d4e5f"
branch_labels = None
depends_on = None
TABLE = "product_listings"


def upgrade():
    op.create_index("ix_product_listings_browse_newest", TABLE,
                    ["status", "published_at", "public_slug"])
    op.create_index("ix_product_listings_browse_price", TABLE,
                    ["status", "price", "public_slug"])
    op.create_index("ix_product_listings_city_newest", TABLE,
                    ["status", "city_id", "published_at", "public_slug"])
    op.create_index("ix_product_listings_city_price", TABLE,
                    ["status", "city_id", "price", "public_slug"])
    op.create_index("ix_product_listings_category_newest", TABLE,
                    ["status", "category_id", "published_at", "public_slug"])
    op.create_index("ix_product_listings_category_price", TABLE,
                    ["status", "category_id", "price", "public_slug"])
    op.create_index("ix_product_listings_search_ngram", TABLE,
                    ["title", "description"], mysql_prefix="FULLTEXT", mysql_with_parser="ngram")


def downgrade():
    # Never run against the development database; isolated migration tests only.
    op.drop_index("ix_product_listings_search_ngram", table_name=TABLE)
    op.drop_index("ix_product_listings_category_price", table_name=TABLE)
    op.drop_index("ix_product_listings_category_newest", table_name=TABLE)
    op.drop_index("ix_product_listings_city_price", table_name=TABLE)
    op.drop_index("ix_product_listings_city_newest", table_name=TABLE)
    op.drop_index("ix_product_listings_browse_price", table_name=TABLE)
    op.drop_index("ix_product_listings_browse_newest", table_name=TABLE)
