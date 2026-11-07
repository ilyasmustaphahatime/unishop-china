"""Durable message writes and bounded participant-authorized history queries."""
from datetime import datetime

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.common.chat import CursorPosition
from app.models import Conversation, Message
from app.repositories.conversation_repository import ConversationRepository


class MessageRepository:
    def by_client_id(self, db: Session, conversation_id: str, sender_id: str, client_id: str):
        return db.scalar(select(Message).where(
            Message.conversation_id == conversation_id,
            Message.sender_user_id == sender_id,
            Message.client_message_id == client_id,
        ).with_for_update().execution_options(populate_existing=True))

    def create(self, db: Session, conversation_id: str, sender_id: str, client_id: str,
               content: str, at: datetime) -> Message:
        row = Message(conversation_id=conversation_id, sender_user_id=sender_id,
                      client_message_id=client_id, content=content, created_at=at)
        db.add(row)
        db.flush()
        return row

    def page_statement(self, actor_id: str, reference: str, limit: int,
                       position: CursorPosition | None):
        statement = (select(
            Message.public_ref.label("message_ref"),
            Conversation.public_ref.label("conversation_ref"),
            case((Message.sender_user_id == Conversation.buyer_user_id, "buyer"),
                 else_="seller").label("sender_role"),
            Message.client_message_id, Message.content, Message.created_at,
        ).join(Conversation, Conversation.id == Message.conversation_id)
         .where(Conversation.public_ref == reference, ConversationRepository.membership(actor_id)))
        if position is not None:
            statement = statement.where(or_(
                Message.created_at < position.value,
                and_(Message.created_at == position.value, Message.public_ref < position.reference),
            ))
        return statement.order_by(Message.created_at.desc(), Message.public_ref.desc()).limit(limit + 1)

    def page(self, db: Session, actor_id: str, reference: str, limit: int,
             position: CursorPosition | None):
        return db.execute(self.page_statement(actor_id, reference, limit, position)).mappings().all()
