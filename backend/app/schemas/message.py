"""Private HTTP history contract shared with WebSocket message serialization."""
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.conversation import ChatModel, ConversationRef


class MessageResponse(ChatModel):
    message_ref: str = Field(pattern=r"^msg-[0-9a-f]{32}$", max_length=36)
    conversation_ref: ConversationRef
    sender_role: Literal["buyer", "seller"]
    client_message_id: str = Field(max_length=36)
    content: str = Field(max_length=2000)
    created_at: datetime


class MessagePage(ChatModel):
    items: list[MessageResponse] = Field(max_length=50)
    next_cursor: str | None = Field(max_length=512)
