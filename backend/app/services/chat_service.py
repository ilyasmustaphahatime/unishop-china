"""Conversation lifecycle and private historical access; no transport dependencies."""
from sqlalchemy.orm import Session

from app.common.chat import (
    ChatCursorCodec, ChatError, ConversationView, CursorPosition, Page, validate_page_limit,
)
from app.common.datetime_utils import as_utc
from app.common.product_slugs import validate_product_slug
from app.core.chat_limits import consume_chat_limit
from app.core.config import Settings, settings
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.repositories.conversation_repository import ConversationRepository
from app.services.chat_authorization import (
    lock_participants, require_active_actor, require_owned_conversation,
)


def conversation_view(row, slug: str, actor_id: str) -> ConversationView:
    return ConversationView(
        conversation_ref=row.public_ref, product_slug=slug,
        role="buyer" if row.buyer_user_id == actor_id else "seller",
        created_at=as_utc(row.created_at), activity_at=as_utc(row.activity_at),
    )


class ConversationService:
    def __init__(self, db: Session, config: Settings = settings):
        self.db, self.config = db, config
        self.repo = ConversationRepository()

    def authenticate(self, actor_id: str) -> None:
        require_active_actor(self.db, actor_id)

    def authorize(self, actor_id: str, conversation_ref: str) -> None:
        self.authenticate(actor_id)
        require_owned_conversation(self.db, actor_id, conversation_ref)

    def create(self, actor_id: str, product_slug: str) -> ConversationView:
        self.authenticate(actor_id)
        consume_chat_limit("create", actor_id)
        try:
            validate_product_slug(product_slug)
        except ValueError:
            raise ChatError("Invalid listing reference.", 422, "chat_validation") from None
        return self._create(self.db, actor_id, product_slug)

    @retry_deadlock
    def _create(self, db: Session, actor_id: str, slug: str) -> ConversationView:
        with transaction(db):
            product = self.repo.public_product(db, slug)
            if product is None:
                raise ChatError("Listing not found.")
            if product.seller_user_id == actor_id:
                raise ChatError("You cannot start a conversation with yourself.", 409, "chat_self")
            lock_participants(db, actor_id, actor_id, product.seller_user_id, eligible_buyer=True)
            # Locks turn this eligibility check into a current read after a wait,
            # including a separate current check for the verification EXISTS.
            if (not self.repo.seller_verified_current(db, product.seller_user_id)
                    or self.repo.public_product(db, slug, current=True) is None):
                raise ChatError("Listing not found.")
            row = self.repo.existing_for_update(db, actor_id, product.seller_user_id, product.id)
            if row is None:
                row = self.repo.create(db, actor_id, product.seller_user_id, product.id,
                                       utc_now().replace(tzinfo=None))
            result = conversation_view(row, slug, actor_id)
        return result

    def get(self, actor_id: str, conversation_ref: str) -> ConversationView:
        self.authenticate(actor_id)
        consume_chat_limit("read", actor_id)
        row, slug = require_owned_conversation(self.db, actor_id, conversation_ref)
        return conversation_view(row, slug, actor_id)

    def list(self, actor_id: str, limit: int = 20, cursor: str | None = None) -> Page[ConversationView]:
        self.authenticate(actor_id)
        consume_chat_limit("read", actor_id)
        validate_page_limit(limit)
        codec = ChatCursorCodec(self.config)
        position = codec.decode(cursor, actor_id, "conversations", None, limit) if cursor else None
        if cursor is not None and not cursor:
            raise ChatError("Invalid cursor.", 400, "chat_cursor")
        rows = self.repo.page(self.db, actor_id, limit, position)
        emitted = rows[:limit]
        next_cursor = (codec.encode(actor_id, "conversations", None, limit,
                       CursorPosition(emitted[-1].activity_at, emitted[-1].conversation_ref))
                       if len(rows) > limit else None)
        return Page([ConversationView(
            conversation_ref=row.conversation_ref, product_slug=row.product_slug, role=row.role,
            created_at=as_utc(row.created_at), activity_at=as_utc(row.activity_at),
        ) for row in emitted], next_cursor)
