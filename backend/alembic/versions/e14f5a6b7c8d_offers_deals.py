"""Phase 14 immutable offers and accepted agreements; forward-only development."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "e14f5a6b7c8d"
down_revision = "d13e4f5a6b7c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_conversations_id_product', 'conversations', ['id', 'product_listing_id'])
    op.create_table('offers',
    sa.Column('public_ref', sa.String(length=35, collation='ascii_bin'), nullable=False),
    sa.Column('conversation_id', sa.CHAR(length=36), nullable=False),
    sa.Column('product_listing_id', sa.CHAR(length=36), nullable=False),
    sa.Column('parent_offer_id', sa.CHAR(length=36), nullable=True),
    sa.Column('proposer_role', sa.String(length=6), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('client_offer_id', sa.String(length=36, collation='ascii_bin'), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('expires_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('closed_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=True),
    sa.Column('closed_by_role', sa.String(length=6), nullable=True),
    sa.Column('closure_reason', sa.String(length=32), nullable=True),
    sa.Column('active_slot', sa.Integer(), sa.Computed("CASE WHEN status = 'PENDING' THEN 1 ELSE NULL END", persisted=True), nullable=True),
    sa.Column('id', sa.CHAR(length=36), nullable=False),
    sa.CheckConstraint("(status = 'PENDING' AND closed_at IS NULL AND closed_by_role IS NULL AND closure_reason IS NULL) OR (status IN ('ACCEPTED','REJECTED','COUNTERED','WITHDRAWN') AND closed_at IS NOT NULL AND closed_at < expires_at AND closed_by_role IS NOT NULL AND closed_by_role IN ('BUYER','SELLER') AND closure_reason IS NULL AND ((status = 'WITHDRAWN' AND closed_by_role = proposer_role) OR (status <> 'WITHDRAWN' AND closed_by_role <> proposer_role))) OR (status = 'EXPIRED' AND closed_at IS NOT NULL AND closed_at = expires_at AND closed_by_role IS NULL AND closure_reason IS NOT NULL AND closure_reason = 'EXPIRED') OR (status = 'CANCELLED' AND closed_at IS NOT NULL AND closed_by_role IS NULL AND closure_reason IS NOT NULL AND closure_reason = 'PRODUCT_UNAVAILABLE')", name='ck_offers_closure'),
    sa.CheckConstraint("REGEXP_LIKE(client_offer_id, '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', 'c')", name='ck_offers_client'),
    sa.CheckConstraint("REGEXP_LIKE(public_ref, '^of-[0-9a-f]{32}$', 'c')", name='ck_offers_ref'),
    sa.CheckConstraint("amount > 0 AND amount <= 9999999999.99 AND currency = 'CNY'", name='ck_offers_money'),
    sa.CheckConstraint("proposer_role IN ('BUYER','SELLER') AND (parent_offer_id IS NOT NULL OR proposer_role = 'BUYER')", name='ck_offers_role'),
    sa.CheckConstraint("status IN ('PENDING','ACCEPTED','REJECTED','WITHDRAWN','COUNTERED','EXPIRED','CANCELLED')", name='ck_offers_status'),
    sa.CheckConstraint('TIMESTAMPDIFF(MICROSECOND, created_at, expires_at) = 86400000000 AND (closed_at IS NULL OR closed_at >= created_at)', name='ck_offers_dates'),
    sa.CheckConstraint('parent_offer_id IS NULL OR parent_offer_id <> id', name='ck_offers_parent'),
    sa.ForeignKeyConstraint(['conversation_id', 'product_listing_id'], ['conversations.id', 'conversations.product_listing_id'], name='fk_offers_conversation_product', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['parent_offer_id', 'conversation_id'], ['offers.id', 'offers.conversation_id'], name='fk_offers_parent_conversation', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_listing_id'], ['product_listings.id'], name='fk_offers_product', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', 'active_slot', name='uq_offers_pending'),
    sa.UniqueConstraint('conversation_id', 'proposer_role', 'client_offer_id', name='uq_offers_client_id'),
    sa.UniqueConstraint('id', 'conversation_id', name='uq_offers_id_conversation'),
    sa.UniqueConstraint('id', 'product_listing_id', name='uq_offers_id_product'),
    sa.UniqueConstraint('parent_offer_id', name='uq_offers_parent'),
    sa.UniqueConstraint('public_ref', name='uq_offers_public_ref')
    )
    op.create_index('ix_offers_conversation_created', 'offers', ['conversation_id', 'created_at', 'public_ref'], unique=False)
    op.create_index('ix_offers_created', 'offers', ['created_at', 'public_ref'], unique=False)
    op.create_index('ix_offers_product_status', 'offers', ['product_listing_id', 'status', 'public_ref'], unique=False)
    op.create_table('deals',
    sa.Column('public_ref', sa.String(length=35, collation='ascii_bin'), nullable=False),
    sa.Column('accepted_offer_id', sa.CHAR(length=36), nullable=False),
    sa.Column('product_listing_id', sa.CHAR(length=36), nullable=False),
    sa.Column('agreed_at', sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql'), nullable=False),
    sa.Column('product_title_snapshot', sa.String(length=120), nullable=False),
    sa.Column('product_condition_snapshot', sa.String(length=16), nullable=False),
    sa.Column('id', sa.CHAR(length=36), nullable=False),
    sa.CheckConstraint("REGEXP_LIKE(public_ref, '^dl-[0-9a-f]{32}$', 'c')", name='ck_deals_ref'),
    sa.CheckConstraint("product_condition_snapshot IN ('new','like_new','good','fair')", name='ck_deals_condition'),
    sa.CheckConstraint('CHAR_LENGTH(TRIM(product_title_snapshot)) BETWEEN 3 AND 120', name='ck_deals_title'),
    sa.ForeignKeyConstraint(['accepted_offer_id', 'product_listing_id'], ['offers.id', 'offers.product_listing_id'], name='fk_deals_offer_product', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['product_listing_id'], ['product_listings.id'], name='fk_deals_product', ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('accepted_offer_id', name='uq_deals_offer'),
    sa.UniqueConstraint('product_listing_id', name='uq_deals_product'),
    sa.UniqueConstraint('public_ref', name='uq_deals_public_ref')
    )
    op.create_index('ix_deals_agreed', 'deals', ['agreed_at', 'public_ref'], unique=False)


def downgrade():
    # Isolated migration-verification databases only; never development.
    op.drop_table("deals")
    op.drop_table("offers")
    op.drop_constraint("uq_conversations_id_product", "conversations", type_="unique")
