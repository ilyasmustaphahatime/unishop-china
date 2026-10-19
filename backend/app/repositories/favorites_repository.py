"""User-scoped favorite SQL; callers own account locking and transactions."""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.models import ProductFavorite, ProductListing
from app.repositories.product_card_projection import (
    public_product_card_statement, public_product_identity_statement,
)

if TYPE_CHECKING:
    from app.services.personalization_cursor import PersonalizationPosition


class FavoritesRepository:
    def public_product_id(self, db: Session, slug: str) -> str | None:
        return db.scalar(public_product_identity_statement().where(
            ProductListing.public_slug == slug,
        ))

    def entries_for_update(self, db: Session, user_id: str):
        """A current read, including after waiting for the caller's User row lock.

        Unlike COUNT's consistent read, this cannot see a stale authentication
        snapshot under MySQL REPEATABLE READ. The service owns the 500-row cap;
        one overflow row is enough to enforce it without unbounded materializing.
        """
        return db.execute(
            select(ProductFavorite.product_listing_id,
                   ProductFavorite.favorited_at.label("associated_at"))
            .where(ProductFavorite.user_id == user_id)
            .order_by(ProductFavorite.favorited_at.desc(),
                      ProductFavorite.product_listing_id.desc())
            .limit(501).with_for_update()
        ).mappings().all()

    def add(self, db: Session, user_id: str, product_id: str, at: datetime) -> ProductFavorite:
        favorite = ProductFavorite(
            user_id=user_id, product_listing_id=product_id, favorited_at=at,
        )
        db.add(favorite)
        return favorite

    def remove(self, db: Session, user_id: str, slug: str) -> None:
        # Deliberately no public-visibility check: hidden products remain removable.
        product_id = select(ProductListing.id).where(ProductListing.public_slug == slug)
        db.execute(delete(ProductFavorite).where(
            ProductFavorite.user_id == user_id,
            ProductFavorite.product_listing_id.in_(product_id),
        ).execution_options(synchronize_session=False))

    def page_statement(
        self, user_id: str, limit: int, position: "PersonalizationPosition | None",
    ):
        association_join = ProductFavorite.__table__.join(
            ProductListing.__table__,
            ProductListing.id == ProductFavorite.product_listing_id,
        )
        statement = (
            public_product_card_statement(from_clause=association_join)
            .add_columns(ProductFavorite.favorited_at.label("associated_at"))
            .where(ProductFavorite.user_id == user_id)
        )
        if position is not None:
            statement = statement.where(or_(
                ProductFavorite.favorited_at < position.value,
                and_(ProductFavorite.favorited_at == position.value,
                     ProductListing.public_slug < position.slug),
            ))
        return statement.order_by(
            ProductFavorite.favorited_at.desc(), ProductListing.public_slug.desc(),
        ).limit(limit + 1)

    def page(
        self, db: Session, user_id: str, limit: int,
        position: "PersonalizationPosition | None",
    ):
        return db.execute(self.page_statement(user_id, limit, position)).mappings().all()

    def lookup(self, db: Session, user_id: str, slugs: list[str]) -> set[str]:
        if not slugs:
            return set()
        statement = (
            public_product_identity_statement()
            .with_only_columns(ProductListing.public_slug, maintain_column_froms=True)
            .join(ProductFavorite, ProductFavorite.product_listing_id == ProductListing.id)
            .where(ProductFavorite.user_id == user_id, ProductListing.public_slug.in_(slugs))
        )
        return set(db.scalars(statement).all())
