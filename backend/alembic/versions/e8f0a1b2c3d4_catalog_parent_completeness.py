"""Close SQL UNKNOWN semantics for nullable composite category parent keys."""
from alembic import op

revision = "e8f0a1b2c3d4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    # SQL CHECK accepts UNKNOWN and composite FKs skip partial NULL keys.
    # Add a separate explicit presence invariant without rewriting applied DDL.
    op.create_check_constraint("ck_categories_parent_complete", "categories",
                               "parent_id IS NULL OR parent_level IS NOT NULL")


def downgrade():
    op.drop_constraint("ck_categories_parent_complete", "categories", type_="check")
