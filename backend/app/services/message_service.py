"""Persist-before-return message operations shared by HTTP and WebSocket transport."""
from sqlalchemy.orm import Session

from app.common.chat import (
    ChatCursorCodec, ChatError, CursorPosition, MessageView, Page, SendResult,
    validate_client_message_id, validate_message_content, validate_page_limit,
)
from app.common.datetime_utils import as_utc
from app.core.chat_limits import consume_chat_limit
from app.core.config import Settings, settings
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.repositories.message_repository import MessageRepository
from app.services.chat_authorization import (
    lock_owned_conversation, require_active_actor, require_owned_conversation,
)


def message_view(row, conversation) -> MessageView:
    return MessageView(
        message_ref=row.public_ref, conversation_ref=conversation.public_ref,
        sender_role="buyer" if row.sender_user_id == conversation.buyer_user_id else "seller",
        client_message_id=row.client_message_id, content=row.content, created_at=as_utc(row.created_at),
    )


class MessageService:
    def __init__(self, db: Session, config: Settings = settings):
        self.db, self.config = db, config
        self.repo = MessageRepository()

    def send(self, actor_id: str, conversation_ref: str, client_message_id: str,
             content: str) -> SendResult:
        require_active_actor(self.db, actor_id)
        consume_chat_limit("send", actor_id)
        try:
            validate_client_message_id(client_message_id)
            validate_message_content(content)
        except ValueError:
            raise ChatError("Invalid message payload.", 422, "chat_validation") from None
        return self._send(self.db, actor_id, conversation_ref, client_message_id, content)

    @retry_deadlock
    def _send(self, db: Session, actor_id: str, reference: str, client_id: str,
              content: str) -> SendResult:
        with transaction(db):
            conversation, _ = lock_owned_conversation(db, actor_id, reference)
            existing = self.repo.by_client_id(db, conversation.id, actor_id, client_id)
            if existing is not None:
                if existing.content != content:
                    raise ChatError("Message identifier already used.", 409, "chat_idempotency_conflict")
                result = SendResult(message_view(existing, conversation), False)
            else:
                at = max(utc_now().replace(tzinfo=None),
                         as_utc(conversation.activity_at).replace(tzinfo=None))
                row = self.repo.create(db, conversation.id, actor_id, client_id, content, at)
                conversation.activity_at = at
                result = SendResult(message_view(row, conversation), True)
        # The transaction has committed. Only the caller may now dispatch result;
        # repositories and the retry body never know about network delivery.
        return result

    def history(self, actor_id: str, conversation_ref: str, limit: int = 20,
                cursor: str | None = None) -> Page[MessageView]:
        require_active_actor(self.db, actor_id)
        consume_chat_limit("read", actor_id)
        require_owned_conversation(self.db, actor_id, conversation_ref)
        validate_page_limit(limit)
        codec = ChatCursorCodec(self.config)
        position = (codec.decode(cursor, actor_id, "messages", conversation_ref, limit)
                    if cursor is not None else None)
        rows = self.repo.page(self.db, actor_id, conversation_ref, limit, position)
        emitted = rows[:limit]
        next_cursor = (codec.encode(actor_id, "messages", conversation_ref, limit,
                       CursorPosition(emitted[-1].created_at, emitted[-1].message_ref))
                       if len(rows) > limit else None)
        return Page([MessageView(
            message_ref=row.message_ref, conversation_ref=row.conversation_ref,
            sender_role=row.sender_role, client_message_id=row.client_message_id,
            content=row.content, created_at=as_utc(row.created_at),
        ) for row in emitted], next_cursor)
