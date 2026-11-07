"""Private conversation HTTP transport; writes and authorization belong to services."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.chat_dependencies import chat_actor, chat_query, safe_chat_operation
from app.core.database import get_db
from app.schemas.conversation import (
    CHAT_ERROR_RESPONSES, ChatListQuery, ConversationCreate, ConversationPage,
    ConversationRef, ConversationResponse,
)
from app.schemas.message import MessagePage
from app.services.chat_service import ConversationService
from app.services.message_service import MessageService

router = APIRouter(tags=["private chat"], responses=CHAT_ERROR_RESPONSES)


@router.post("", response_model=ConversationResponse,
             description="Create or reuse the unique buyer/seller/product conversation. "
                         "Seller identity is derived by the server; 200 for both cases.")
def create_conversation(body: ConversationCreate, request: Request,
                        actor_id: str = Depends(chat_actor), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return ConversationService(db, config=request.app.state.settings).create(actor_id, body.product_slug)


@router.get("", response_model=ConversationPage,
            description="Participant-only recent-activity keysets, newest first. "
                        "Opaque cursor is bound to the account and page size.")
def list_conversations(request: Request, actor_id: str = Depends(chat_actor),
                       query: ChatListQuery = Depends(chat_query), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return ConversationService(db, config=request.app.state.settings).list(
            actor_id, limit=query.limit, cursor=query.cursor)


@router.get("/{conversation_ref}", response_model=ConversationResponse,
            description="Active participants retain history access after a product is paused or archived.")
def get_conversation(conversation_ref: ConversationRef, request: Request,
                      actor_id: str = Depends(chat_actor), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return ConversationService(db, config=request.app.state.settings).get(actor_id, conversation_ref)


@router.get("/{conversation_ref}/messages", response_model=MessagePage,
            description="Newest-first durable message history; cursor is bound to account, "
                        "conversation and page size. Render content as plain text, never trusted HTML.")
def message_history(conversation_ref: ConversationRef, request: Request,
                    actor_id: str = Depends(chat_actor), query: ChatListQuery = Depends(chat_query),
                    db: Session = Depends(get_db)):
    with safe_chat_operation():
        return MessageService(db, config=request.app.state.settings).history(
            actor_id, conversation_ref, limit=query.limit, cursor=query.cursor)
