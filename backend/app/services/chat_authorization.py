"""One account/membership policy shared by HTTP, socket and handoff services."""
from sqlalchemy.orm import Session

from app.common.chat import ChatError, validate_conversation_ref
from app.common.enums import AccountStatus
from app.core.authorization import AuthorizationError, lock_active_user
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.user_repository import UserRepository


def require_active_actor(db: Session, actor_id: str) -> None:
    state = ConversationRepository().account_state(db, actor_id)
    if state is None or state.account_status != AccountStatus.ACTIVE:
        raise ChatError("Account unavailable.", 401, "chat_authentication")


def require_owned_conversation(db: Session, actor_id: str, reference: str):
    try:
        validate_conversation_ref(reference)
    except ValueError:
        raise ChatError("Invalid conversation reference.", 422, "chat_validation") from None
    found = ConversationRepository().owned(db, actor_id, reference)
    if found is None:
        raise ChatError("Conversation not found.")
    return found


def lock_participants(db: Session, actor_id: str, buyer_id: str, seller_id: str,
                      *, eligible_buyer: bool = False,
                      require_counterparty_active: bool = True) -> None:
    # Stable order across both directions of a conversation avoids A->B/B->A
    # account-lock cycles. Account transitions elsewhere use these same User locks.
    for user_id in sorted((buyer_id, seller_id)):
        if user_id != actor_id and not require_counterparty_active:
            if UserRepository().get_by_id_for_update(db, user_id) is None:
                raise ChatError("Conversation unavailable.", 409, "chat_participant_unavailable")
            continue
        try:
            lock_active_user(db, user_id, eligible=eligible_buyer and user_id == buyer_id)
        except AuthorizationError as error:
            if user_id == actor_id:
                message = ("Verify both email and phone before continuing."
                           if error.status == 403 else "Account unavailable.")
                raise ChatError(message, error.status, "chat_authentication") from None
            raise ChatError("Conversation unavailable.", 409, "chat_participant_unavailable") from None


def lock_owned_conversation(db: Session, actor_id: str, reference: str,
                            *, require_counterparty_active: bool = True):
    found = require_owned_conversation(db, actor_id, reference)
    conversation = found[0]
    lock_participants(db, actor_id, conversation.buyer_user_id, conversation.seller_user_id,
                      require_counterparty_active=require_counterparty_active)
    current = ConversationRepository().owned(db, actor_id, reference, for_update=True)
    if current is None:
        raise ChatError("Conversation not found.")
    return current
