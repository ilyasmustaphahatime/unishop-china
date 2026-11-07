"""Phase 13 conversations, durable messages and encrypted seller-consent state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "d13e4f5a6b7c"
down_revision = "c12d3e4f5a6b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("public_ref", sa.String(35, collation="ascii_bin"), nullable=False),
        sa.Column("buyer_user_id", sa.CHAR(36), nullable=False),
        sa.Column("seller_user_id", sa.CHAR(36), nullable=False),
        sa.Column("product_listing_id", sa.CHAR(36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("activity_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_ref", name="uq_conversations_public_ref"),
        sa.UniqueConstraint("buyer_user_id", "seller_user_id", "product_listing_id",
                            name="uq_conversations_participants_product"),
        sa.CheckConstraint("buyer_user_id <> seller_user_id", name="ck_conversations_distinct_users"),
        sa.CheckConstraint("REGEXP_LIKE(public_ref, '^cv-[0-9a-f]{32}$', 'c')",
                           name="ck_conversations_public_ref"),
        sa.ForeignKeyConstraint(["buyer_user_id"], ["users.id"],
                                name="fk_conversations_buyer", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["seller_user_id"], ["users.id"],
                                name="fk_conversations_seller", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_listing_id"], ["product_listings.id"],
                                name="fk_conversations_product", ondelete="RESTRICT"),
    )
    op.create_index("ix_conversations_buyer_activity", "conversations",
                    ["buyer_user_id", "activity_at", "public_ref"])
    op.create_index("ix_conversations_seller_activity", "conversations",
                    ["seller_user_id", "activity_at", "public_ref"])
    op.create_index("ix_conversations_product", "conversations", ["product_listing_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.CHAR(36), nullable=False),
        sa.Column("public_ref", sa.String(36, collation="ascii_bin"), nullable=False),
        sa.Column("conversation_id", sa.CHAR(36), nullable=False),
        sa.Column("sender_user_id", sa.CHAR(36), nullable=False),
        sa.Column("client_message_id", sa.String(36, collation="ascii_bin"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_ref", name="uq_messages_public_ref"),
        sa.UniqueConstraint("conversation_id", "sender_user_id", "client_message_id",
                            name="uq_messages_client_id"),
        sa.CheckConstraint("REGEXP_LIKE(public_ref, '^msg-[0-9a-f]{32}$', 'c')",
                           name="ck_messages_public_ref"),
        sa.CheckConstraint("REGEXP_LIKE(client_message_id, "
                           "'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 'c')",
                           name="ck_messages_client_id"),
        sa.CheckConstraint("CHAR_LENGTH(content) BETWEEN 1 AND 2000 AND OCTET_LENGTH(content) <= 8000",
                           name="ck_messages_content_size"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                name="fk_messages_conversation", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"],
                                name="fk_messages_sender", ondelete="RESTRICT"),
    )
    op.create_index("ix_messages_conversation_time", "messages",
                    ["conversation_id", "created_at", "public_ref"])
    op.create_index("ix_messages_sender", "messages", ["sender_user_id"])
    op.create_table(
        "wechat_share_requests",
        sa.Column("conversation_id", sa.CHAR(36), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("decided_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("contact_ciphertext", sa.String(2048), nullable=True),
        sa.PrimaryKeyConstraint("conversation_id"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"],
                                name="fk_wechat_shares_conversation", ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','DENIED','REVOKED')",
                           name="ck_wechat_shares_status"),
        sa.CheckConstraint("(status = 'APPROVED' AND contact_ciphertext IS NOT NULL) OR "
                           "(status <> 'APPROVED' AND contact_ciphertext IS NULL)",
                           name="ck_wechat_shares_ciphertext"),
        sa.CheckConstraint("(status = 'PENDING' AND decided_at IS NULL AND revoked_at IS NULL) OR "
                           "(status IN ('APPROVED','DENIED') AND decided_at IS NOT NULL "
                           "AND revoked_at IS NULL) OR (status = 'REVOKED' AND revoked_at IS NOT NULL)",
                           name="ck_wechat_shares_timestamps"),
    )


def downgrade():
    # Disposable migration-verification databases only; never downgrade development.
    op.drop_table("wechat_share_requests")
    op.drop_table("messages")
    op.drop_table("conversations")
