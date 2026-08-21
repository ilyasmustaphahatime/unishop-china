"""add password reset attempts

Revision ID: aca2dda0ef53
Revises: c91e4a7b2d6f
Create Date: 2026-08-21 17:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aca2dda0ef53"
down_revision: str | None = "c91e4a7b2d6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add durable incorrect-attempt tracking for password-reset challenges."""
    op.add_column(
        "password_reset_codes",
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_password_reset_codes_attempts_non_negative",
        "password_reset_codes",
        "attempts >= 0",
    )


def downgrade() -> None:
    """Remove password-reset incorrect-attempt tracking."""
    op.drop_constraint(
        "ck_password_reset_codes_attempts_non_negative",
        "password_reset_codes",
        type_="check",
    )
    op.drop_column("password_reset_codes", "attempts")
