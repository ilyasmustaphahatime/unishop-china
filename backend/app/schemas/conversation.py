"""Explicit private projections; never serialize chat ORM rows directly."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.product_slugs import ProductSlug

ConversationRef = Annotated[str, Field(strict=True, pattern=r"^cv-[0-9a-f]{32}$", max_length=35)]


class ChatModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ConversationCreate(ChatModel):
    product_slug: ProductSlug


class ConversationResponse(ChatModel):
    conversation_ref: ConversationRef
    product_slug: ProductSlug
    role: Literal["buyer", "seller"]
    created_at: datetime
    activity_at: datetime


class ConversationPage(ChatModel):
    items: list[ConversationResponse] = Field(max_length=50)
    next_cursor: str | None = Field(max_length=512)


class ChatListQuery(ChatModel):
    limit: int = Field(default=20, ge=1, le=50, strict=True)
    cursor: str | None = Field(default=None, max_length=512, strict=True)


class ChatErrorResponse(ChatModel):
    detail: str


class ChatValidationItem(ChatModel):
    type: str
    loc: list[str | int]
    msg: str


class ChatValidationResponse(ChatModel):
    detail: str | list[ChatValidationItem]


CHAT_ERROR_RESPONSES = {
    code: {"model": ChatErrorResponse, "description": description}
    for code, description in {
        400: "Invalid or incorrectly scoped pagination cursor.",
        401: "Valid access authentication and an active account are required.",
        403: "Operation forbidden by account, Origin or participant-role policy.",
        404: "Resource unavailable or not visible to the current participant.",
        408: "Request input deadline exceeded.",
        409: "Operation conflicts with the current conversation or consent state.",
        413: "Request exceeds the actual-byte or query-size limit.",
        415: "Use application/json for a request with a JSON body.",
        429: "Peer or account budget exhausted; Retry-After is provided.",
        500: "Unexpected failure; no internal error details are returned.",
        503: "Chat persistence, pagination or contact encryption unavailable.",
    }.items()
}
CHAT_ERROR_RESPONSES[422] = {
    "model": ChatValidationResponse,
    "description": "Strict input validation failed; input values are never echoed.",
}
