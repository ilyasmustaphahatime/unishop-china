"""add refresh session fields

Revision ID: c91e4a7b2d6f
Revises: a75289cfd4a9
Create Date: 2026-08-06
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c91e4a7b2d6f"
down_revision: str | None = "a75289cfd4a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("family_id", sa.CHAR(36), nullable=False))
    op.add_column(
        "refresh_tokens",
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("family_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("revocation_reason", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("replaced_by_token_id", sa.CHAR(36), nullable=True),
    )
    op.create_check_constraint(
        "ck_refresh_tokens_revocation_reason",
        "refresh_tokens",
        "revocation_reason IS NULL OR revocation_reason IN "
        "('rotated', 'logout', 'logout_all', 'reuse_detected', "
        "'inactive_account', 'session_limit', 'expired_cleanup')",
    )
    op.create_foreign_key(
        "fk_refresh_tokens_replaced_by_token_id",
        "refresh_tokens",
        "refresh_tokens",
        ["replaced_by_token_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"])
    op.create_index(
        "ix_refresh_tokens_family_expires_at", "refresh_tokens", ["family_expires_at"]
    )
    op.create_index("ix_refresh_tokens_revoked_at", "refresh_tokens", ["revoked_at"])
    op.create_index(
        "ix_refresh_tokens_replaced_by_token_id",
        "refresh_tokens",
        ["replaced_by_token_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_replaced_by_token_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_revoked_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_family_id", table_name="refresh_tokens")
    op.drop_constraint(
        "fk_refresh_tokens_replaced_by_token_id",
        "refresh_tokens",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_refresh_tokens_revocation_reason",
        "refresh_tokens",
        type_="check",
    )
    op.drop_column("refresh_tokens", "replaced_by_token_id")
    op.drop_column("refresh_tokens", "revocation_reason")
    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "family_expires_at")
    op.drop_column("refresh_tokens", "csrf_token_hash")
    op.drop_column("refresh_tokens", "family_id")
