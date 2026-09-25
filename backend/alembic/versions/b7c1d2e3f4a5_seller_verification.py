"""Phase 7 private seller verification; additive, no existing authentication data changes."""
from alembic import op
import sqlalchemy as sa

revision = "b7c1d2e3f4a5"
down_revision = "a61b2c3d4e5f"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("id", sa.CHAR(36), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table(
        "seller_verifications",
        *timestamps(),
        sa.Column("user_id", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_reference", sa.String(32), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "UNDER_REVIEW", "VERIFIED", "REJECTED",
                                    name="seller_verification_status"), nullable=False),
        sa.Column("active_slot", sa.Integer(),
                  sa.Computed("CASE WHEN status <> 'REJECTED' THEN 1 ELSE NULL END", persisted=True)),
        sa.Column("handwritten_challenge", sa.String(12), nullable=False),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("reviewed_by", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("review_reference", name="uq_seller_review_reference"),
        sa.UniqueConstraint("user_id", "active_slot", name="uq_seller_active_user"),
        sa.CheckConstraint("(status = 'PENDING' AND submitted_at IS NULL AND reviewed_at IS NULL) OR "
                           "(status = 'UNDER_REVIEW' AND submitted_at IS NOT NULL AND reviewed_at IS NULL) OR "
                           "(status IN ('VERIFIED','REJECTED') AND submitted_at IS NOT NULL AND reviewed_at IS NOT NULL)",
                           name="ck_seller_transition_dates"),
        sa.CheckConstraint("(status = 'REJECTED' AND rejection_reason IS NOT NULL) OR "
                           "(status <> 'REJECTED' AND rejection_reason IS NULL)", name="ck_seller_rejection"),
    )
    op.create_index("ix_seller_verifications_user_id", "seller_verifications", ["user_id"])
    op.create_index("ix_seller_verifications_status", "seller_verifications", ["status"])
    op.create_table(
        "seller_evidence", *timestamps(),
        sa.Column("verification_id", sa.CHAR(36),
                  sa.ForeignKey("seller_verifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_type", sa.Enum("SELFIE", "WECHAT_PROOF", "HANDWRITTEN_CODE",
                                        name="seller_evidence_type"), nullable=False),
        sa.Column("storage_key", sa.String(64), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(32), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.UniqueConstraint("verification_id", "evidence_type", name="uq_seller_evidence_type"),
        sa.UniqueConstraint("storage_key", name="uq_seller_evidence_storage"),
        sa.CheckConstraint("size > 0 AND size <= 5242880", name="ck_seller_evidence_size"),
        sa.CheckConstraint("mime_type IN ('image/jpeg','image/png')", name="ck_seller_evidence_mime"),
    )
    op.create_index("ix_seller_evidence_verification_id", "seller_evidence", ["verification_id"])
    op.create_table(
        "seller_verification_audit",
        sa.Column("id", sa.CHAR(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verification_id", sa.CHAR(36),
                  sa.ForeignKey("seller_verifications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.CHAR(36), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event", sa.String(32), nullable=False),
    )
    op.create_index("ix_seller_verification_audit_verification_id", "seller_verification_audit", ["verification_id"])


def downgrade():
    # Explicitly removes only Phase 7 data. Never run on populated dev/prod without a reviewed backup.
    op.drop_table("seller_verification_audit")
    op.drop_table("seller_evidence")
    op.drop_table("seller_verifications")
