"""Private history SQL, serialized per user by the service's account row lock."""
from collections.abc import Sequence
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import Session

from app.models import ProductListing, ProductRecentView
from app.repositories.product_card_projection import (
    public_product_card_statement, public_product_identity_statement,
)

if TYPE_CHECKING:
    from app.services.personalization_cursor import PersonalizationPosition


class RecentlyViewedRepository:
    def public_product_id(self, db: Session, slug: str) -> str | None:
        return db.scalar(public_product_identity_statement().where(
            ProductListing.public_slug == slug,
        ))

    def entries_for_update(self, db: Session, user_id: str):
        """Read committed history state after actor locking, including one overflow."""
        return db.execute(
            select(ProductRecentView.product_listing_id,
                   ProductRecentView.last_viewed_at.label("associated_at"))
            .where(ProductRecentView.user_id == user_id)
            .order_by(ProductRecentView.last_viewed_at.desc(),
                      ProductRecentView.product_listing_id.desc())
            .limit(101).with_for_update()
        ).mappings().all()

    def upsert(self, db: Session, user_id: str, product_id: str, at: datetime) -> None:
        statement = insert(ProductRecentView).values(
            user_id=user_id, product_listing_id=product_id, last_viewed_at=at,
        )
        # Preserve monotonic history even if a timestamp source moves backwards.
        db.execute(statement.on_duplicate_key_update(last_viewed_at=func.greatest(
            ProductRecentView.last_viewed_at, statement.inserted.last_viewed_at,
        )))

    def remove_entries(self, db: Session, user_id: str, product_ids: Sequence[str]) -> None:
        if product_ids:
            db.execute(delete(ProductRecentView).where(
                ProductRecentView.user_id == user_id,
                ProductRecentView.product_listing_id.in_(product_ids),
            ).execution_options(synchronize_session=False))

    def remove(self, db: Session, user_id: str, slug: str) -> None:
        product_id = select(ProductListing.id).where(ProductListing.public_slug == slug)
        db.execute(delete(ProductRecentView).where(
            ProductRecentView.user_id == user_id,
            ProductRecentView.product_listing_id.in_(product_id),
        ).execution_options(synchronize_session=False))

    def clear(self, db: Session, user_id: str) -> None:
        db.execute(delete(ProductRecentView).where(
            ProductRecentView.user_id == user_id,
        ).execution_options(synchronize_session=False))

    def page_statement(
        self, user_id: str, limit: int, position: "PersonalizationPosition | None",
    ):
        association_join = ProductRecentView.__table__.join(
            ProductListing.__table__,
            ProductListing.id == ProductRecentView.product_listing_id,
        )
        statement = (
            public_product_card_statement(from_clause=association_join)
            .add_columns(ProductRecentView.last_viewed_at.label("associated_at"))
            .where(ProductRecentView.user_id == user_id)
        )
        if position is not None:
            statement = statement.where(or_(
                ProductRecentView.last_viewed_at < position.value,
                and_(ProductRecentView.last_viewed_at == position.value,
                     ProductListing.public_slug < position.slug),
            ))
        return statement.order_by(
            ProductRecentView.last_viewed_at.desc(), ProductListing.public_slug.desc(),
        ).limit(limit + 1)

    def page(
        self, db: Session, user_id: str, limit: int,
        position: "PersonalizationPosition | None",
    ):
        return db.execute(self.page_statement(user_id, limit, position)).mappings().all()
