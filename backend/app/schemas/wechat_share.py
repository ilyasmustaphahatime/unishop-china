"""Private WeChat ID consent contracts, independent of any external WeChat API."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from app.common.wechat import validate_wechat_contact
from app.schemas.conversation import ChatModel

Contact = Annotated[str, Field(strict=True, min_length=6, max_length=20),
                    AfterValidator(validate_wechat_contact)]


class WeChatApproval(ChatModel):
    contact: Contact = Field(repr=False)


class HandoffResponse(ChatModel):
    status: Literal["NONE", "PENDING", "APPROVED", "DENIED", "REVOKED"]
    requested_at: datetime | None
    decided_at: datetime | None
    revoked_at: datetime | None
    contact: Contact | None = Field(default=None, repr=False)
