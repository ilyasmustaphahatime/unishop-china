"""Add bounded handwritten challenge validity without rewriting the applied Phase 7 revision."""
from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("seller_verifications", sa.Column("challenge_expires_at", sa.DateTime(timezone=True), nullable=True))
    # Preserve old attempts and their evidence. Old pending challenges may already
    # be expired; the owner can explicitly renew them. Submitted reviews stay valid.
    op.execute(sa.text("UPDATE seller_verifications SET challenge_expires_at = DATE_ADD(created_at, INTERVAL 10 MINUTE)"))
    op.alter_column("seller_verifications", "challenge_expires_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    op.drop_column("seller_verifications", "challenge_expires_at")
