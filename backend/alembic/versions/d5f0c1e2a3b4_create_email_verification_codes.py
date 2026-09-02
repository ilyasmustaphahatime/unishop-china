"""create email verification codes

Revision ID: d5f0c1e2a3b4
Revises: aca2dda0ef53
Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d5f0c1e2a3b4"
down_revision: str | None = "aca2dda0ef53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add isolated, durable email-verification challenges."""
    op.create_table(
        "email_verification_codes",
        sa.Column("user_id", sa.CHAR(length=36), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_email_verification_codes_attempts_non_negative",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_email_verification_codes_user_id"),
        "email_verification_codes",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_email_verification_codes_expires_at"),
        "email_verification_codes",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove only Phase 5D email-verification challenge storage."""
    op.drop_table("email_verification_codes")
