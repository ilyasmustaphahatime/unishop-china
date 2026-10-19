"""Explicit private history writes, monotone timestamps and bounded retention."""
from app.core.authorization import lock_active_user
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.repositories.recently_viewed_repository import RecentlyViewedRepository
from app.schemas.product_personalization import (
    PersonalListKind, RecentlyViewedItem, RecentlyViewedPage,
)
from app.services.personalization_cursor import PersonalizationPosition
from app.services.personalization_errors import PersonalizationError
from app.services.product_card import serialize_product_card


class RecentlyViewedService:
    def __init__(self, *, codec, api_prefix="/api/v1", retention=100,
                 repository=None, clock=utc_now):
        self.codec, self.api_prefix, self.retention = codec, api_prefix, retention
        self.repo = repository or RecentlyViewedRepository()
        self.clock = clock

    @retry_deadlock
    def record(self, db, user_id, slug):
        observed_at = self.clock()
        with transaction(db):
            lock_active_user(db, user_id)
            product_id = self.repo.public_product_id(db, slug)
            if product_id is None:
                raise PersonalizationError("Listing not found.", 404)
            self.repo.upsert(db, user_id, product_id, observed_at)
            entries = self.repo.entries_for_update(db, user_id)
            self.repo.remove_entries(db, user_id,
                                     [row.product_listing_id for row in entries[self.retention:]])

    @retry_deadlock
    def remove(self, db, user_id, slug):
        with transaction(db):
            lock_active_user(db, user_id)
            self.repo.remove(db, user_id, slug)

    @retry_deadlock
    def clear(self, db, user_id):
        with transaction(db):
            lock_active_user(db, user_id)
            self.repo.clear(db, user_id)

    def list(self, db, user_id, query):
        kind = PersonalListKind.RECENTLY_VIEWED
        position = (self.codec.decode(query.cursor, user_id, kind, query.limit)
                    if query.cursor is not None else None)
        rows = self.repo.page(db, user_id, query.limit, position)
        emitted, has_more = rows[:query.limit], len(rows) > query.limit
        cursor = (self.codec.encode(user_id, kind, query.limit,
                  PersonalizationPosition(emitted[-1].associated_at, emitted[-1].public_slug))
                  if has_more else None)
        return RecentlyViewedPage(items=[RecentlyViewedItem(
            product=serialize_product_card(row, self.api_prefix), last_viewed_at=row.associated_at)
            for row in emitted], next_cursor=cursor, has_more=has_more)
