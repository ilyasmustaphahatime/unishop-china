"""Explicit private consent operations. Contact material is returned only by GET."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.chat_dependencies import chat_actor, safe_chat_operation
from app.core.database import get_db
from app.integrations.wechat_cipher import WeChatCipher
from app.schemas.conversation import CHAT_ERROR_RESPONSES, ConversationRef
from app.schemas.wechat_share import HandoffResponse, WeChatApproval
from app.services.wechat_service import WeChatHandoffService

router = APIRouter(tags=["private WeChat handoff"], responses=CHAT_ERROR_RESPONSES)


def _service(db, request):
    config = request.app.state.settings
    return WeChatHandoffService(db, WeChatCipher(config), config=config)


@router.get("/{conversation_ref}/wechat", response_model=HandoffResponse,
            description="Private status and approved contact for active participants only. "
                        "Contact is absent unless explicitly approved and both accounts are active.")
def get_handoff(conversation_ref: ConversationRef, request: Request,
                actor_id: str = Depends(chat_actor), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return _service(db, request).get(actor_id, conversation_ref)


@router.post("/{conversation_ref}/wechat/request", response_model=HandoffResponse,
             description="Buyer-only request. Pending/approved retries return current state; "
                         "denied/revoked requests conflict and never reopen.")
def request_handoff(conversation_ref: ConversationRef, request: Request,
                    actor_id: str = Depends(chat_actor), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return _service(db, request).request(actor_id, conversation_ref)


@router.post("/{conversation_ref}/wechat/approve", response_model=HandoffResponse,
             description="Seller-only approval of a pending request using a WeChat ID. "
                         "Identical approval retries are idempotent; a different value conflicts.")
def approve_handoff(conversation_ref: ConversationRef, body: WeChatApproval, request: Request,
                    actor_id: str = Depends(chat_actor), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return _service(db, request).approve(actor_id, conversation_ref, body.contact)


@router.post("/{conversation_ref}/wechat/deny", response_model=HandoffResponse,
             description="Seller-only terminal denial of a pending request. Repeated denial is idempotent.")
def deny_handoff(conversation_ref: ConversationRef, request: Request,
                 actor_id: str = Depends(chat_actor), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return _service(db, request).deny(actor_id, conversation_ref)


@router.post("/{conversation_ref}/wechat/revoke", response_model=HandoffResponse,
             description="Seller-only terminal revocation of pending or approved consent, "
                         "including when the buyer is inactive. Clears stored contact; "
                         "cannot erase copies already received by the buyer.")
def revoke_handoff(conversation_ref: ConversationRef, request: Request,
                   actor_id: str = Depends(chat_actor), db: Session = Depends(get_db)):
    with safe_chat_operation():
        return _service(db, request).revoke(actor_id, conversation_ref)
