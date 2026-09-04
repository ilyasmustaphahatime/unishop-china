"""create user profiles

Revision ID: f6a1b2c3d4e5
Revises: d5f0c1e2a3b4
Create Date: 2026-09-04 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f6a1b2c3d4e5"
down_revision: str | None = "d5f0c1e2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.CHAR(length=36), nullable=False),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=50), nullable=True),
        sa.Column("bio", sa.String(length=300), nullable=True),
        sa.Column("city", sa.String(length=32), nullable=True),
        sa.Column(
            "onboarding_completed",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "display_name IS NULL OR "
            "CHAR_LENGTH(TRIM(display_name)) BETWEEN 2 AND 50",
            name="ck_user_profiles_display_name_length",
        ),
        sa.CheckConstraint(
            "bio IS NULL OR CHAR_LENGTH(bio) <= 300",
            name="ck_user_profiles_bio_length",
        ),
        sa.CheckConstraint(
            "city IS NULL OR city IN "
            "('Qingdao','Beijing','Shanghai','Shenzhen','Guangzhou','Hangzhou')",
            name="ck_user_profiles_supported_city",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_user_profiles_public_id"),
        sa.UniqueConstraint("user_id", name="uq_user_profiles_user_id"),
    )


def downgrade() -> None:
    op.drop_table("user_profiles")
