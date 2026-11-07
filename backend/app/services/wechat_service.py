"""Explicit, terminal seller consent. Contacts leave this service only on private GET."""
from sqlalchemy.orm import Session

from app.common.chat import ChatError, HandoffView
from app.common.datetime_utils import as_utc
from app.common.wechat import validate_wechat_contact
from app.core.chat_limits import consume_chat_limit
from app.core.config import Settings, settings
from app.core.transactions import retry_deadlock, transaction
from app.models.base import utc_now
from app.repositories.wechat_share_repository import WeChatShareRepository
from app.services.chat_authorization import lock_owned_conversation, require_active_actor


def handoff_view(row, contact: str | None = None) -> HandoffView:
    if row is None:
        return HandoffView("NONE", None, None, None)
    return HandoffView(
        status=row.status, requested_at=as_utc(row.requested_at),
        decided_at=as_utc(row.decided_at) if row.decided_at is not None else None,
        revoked_at=as_utc(row.revoked_at) if row.revoked_at is not None else None,
        contact=contact,
    )


class WeChatHandoffService:
    def __init__(self, db: Session, cipher, config: Settings = settings):
        self.db, self.cipher, self.config = db, cipher, config
        self.repo = WeChatShareRepository()

    def _prepare(self, actor_id: str, *, read: bool = False) -> None:
        require_active_actor(self.db, actor_id)
        consume_chat_limit("read" if read else "handoff", actor_id)

    def request(self, actor_id: str, conversation_ref: str) -> HandoffView:
        self._prepare(actor_id)
        return self._mutate(self.db, actor_id, conversation_ref, "request")

    def approve(self, actor_id: str, conversation_ref: str, contact: str) -> HandoffView:
        self._prepare(actor_id)
        try:
            validate_wechat_contact(contact)
        except ValueError:
            raise ChatError("Invalid WeChat ID.", 422, "chat_validation") from None
        return self._mutate(self.db, actor_id, conversation_ref, "approve", contact)

    def deny(self, actor_id: str, conversation_ref: str) -> HandoffView:
        self._prepare(actor_id)
        return self._mutate(self.db, actor_id, conversation_ref, "deny")

    def revoke(self, actor_id: str, conversation_ref: str) -> HandoffView:
        self._prepare(actor_id)
        return self._mutate(self.db, actor_id, conversation_ref, "revoke")

    @retry_deadlock
    def _mutate(self, db: Session, actor_id: str, reference: str, action: str,
                contact: str | None = None) -> HandoffView:
        with transaction(db):
            conversation, _ = lock_owned_conversation(
                db, actor_id, reference, require_counterparty_active=action != "revoke",
            )
            allowed_id = (conversation.buyer_user_id if action == "request"
                          else conversation.seller_user_id)
            if actor_id != allowed_id:
                raise ChatError("This action is not permitted.", 403, "chat_forbidden")
            row = self.repo.for_update(db, conversation.id)
            if action == "request":
                if row is None:
                    row = self.repo.create(db, conversation.id, utc_now().replace(tzinfo=None))
                elif row.status in {"DENIED", "REVOKED"}:
                    raise ChatError("Handoff request is closed.", 409, "chat_handoff_state")
            elif row is None:
                raise ChatError("No handoff request exists.", 409, "chat_handoff_state")
            else:
                self._transition(row, action, reference, contact)
            result = handoff_view(row)
        return result

    def _transition(self, row, action: str, reference: str, contact: str | None) -> None:
        at = utc_now().replace(tzinfo=None)
        if action == "revoke":
            if row.status == "REVOKED":
                return
            if row.status not in {"PENDING", "APPROVED"}:
                raise ChatError("Handoff state does not permit this action.", 409, "chat_handoff_state")
            row.status, row.contact_ciphertext, row.revoked_at = "REVOKED", None, at
            return
        if action == "deny" and row.status == "DENIED":
            return
        if action == "approve" and row.status == "APPROVED":
            if self.cipher.decrypt(row.contact_ciphertext, reference) != contact:
                raise ChatError("Handoff is already approved.", 409, "chat_handoff_state")
            return
        if row.status != "PENDING":
            raise ChatError("Handoff state does not permit this action.", 409, "chat_handoff_state")
        if action == "approve":
            row.contact_ciphertext = self.cipher.encrypt(contact, reference)
            row.status = "APPROVED"
        else:
            row.status = "DENIED"
        row.decided_at = at

    def get(self, actor_id: str, conversation_ref: str) -> HandoffView:
        self._prepare(actor_id, read=True)
        return self._get(self.db, actor_id, conversation_ref)

    @retry_deadlock
    def _get(self, db: Session, actor_id: str, reference: str) -> HandoffView:
        # Serialize the authorization/consent read with revocation. No mutation;
        # the inevitable network-after-read race cannot un-send a copied contact.
        with transaction(db):
            conversation, _ = lock_owned_conversation(db, actor_id, reference)
            row = self.repo.for_update(db, conversation.id)
            contact = (self.cipher.decrypt(row.contact_ciphertext, reference)
                       if row is not None and row.status == "APPROVED" else None)
            result = handoff_view(row, contact)
        return result
