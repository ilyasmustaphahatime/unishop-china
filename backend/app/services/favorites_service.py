"""Idempotent, quota-bound favorites; services own the entire write transaction."""
from app.core.authorization import lock_active_user
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.repositories.favorites_repository import FavoritesRepository
from app.schemas.product_personalization import (
    FavoriteItem, FavoriteStatus, FavoritesLookupResponse, FavoritesPage, PersonalListKind,
)
from app.services.personalization_cursor import PersonalizationPosition
from app.services.personalization_errors import PersonalizationError
from app.services.product_card import serialize_product_card


class FavoritesService:
    def __init__(self, *, codec, api_prefix="/api/v1", quota=500, repository=None, clock=utc_now):
        self.codec, self.api_prefix, self.quota = codec, api_prefix, quota
        self.repo = repository or FavoritesRepository()
        self.clock = clock

    @retry_deadlock
    def add(self, db, user_id, slug):
        with transaction(db):
            lock_active_user(db, user_id)
            product_id = self.repo.public_product_id(db, slug)
            if product_id is None:
                raise PersonalizationError("Listing not found.", 404)
            entries = self.repo.entries_for_update(db, user_id)
            if not any(row.product_listing_id == product_id for row in entries):
                if len(entries) >= self.quota:
                    raise PersonalizationError("Saved listing limit reached.", 409)
                self.repo.add(db, user_id, product_id, self.clock())
        return FavoriteStatus(favorited=True)

    @retry_deadlock
    def remove(self, db, user_id, slug):
        with transaction(db):
            lock_active_user(db, user_id)
            self.repo.remove(db, user_id, slug)

    def list(self, db, user_id, query):
        kind = PersonalListKind.FAVORITES
        position = (self.codec.decode(query.cursor, user_id, kind, query.limit)
                    if query.cursor is not None else None)
        rows = self.repo.page(db, user_id, query.limit, position)
        emitted, has_more = rows[:query.limit], len(rows) > query.limit
        cursor = (self.codec.encode(user_id, kind, query.limit,
                  PersonalizationPosition(emitted[-1].associated_at, emitted[-1].public_slug))
                  if has_more else None)
        return FavoritesPage(items=[FavoriteItem(product=serialize_product_card(row, self.api_prefix),
                             favorited_at=row.associated_at) for row in emitted],
                             next_cursor=cursor, has_more=has_more)

    def lookup(self, db, user_id, slugs):
        affirmative = self.repo.lookup(db, user_id, slugs)
        return FavoritesLookupResponse(favorites={slug: slug in affirmative for slug in slugs})
