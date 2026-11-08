"""Strict proposals and explicit private views: no ORM identity serialization."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.common.offers import validate_client_id
from app.schemas.conversation import ConversationRef
from app.common.product_slugs import ProductSlug
from app.schemas.product import Price

OfferRef = Annotated[str, Field(strict=True, pattern=r"^of-[0-9a-f]{32}$", max_length=35)]
DealRef = Annotated[str, Field(strict=True, pattern=r"^dl-[0-9a-f]{32}$", max_length=35)]
OfferStatus = Literal["PENDING", "ACCEPTED", "REJECTED", "WITHDRAWN", "COUNTERED", "EXPIRED", "CANCELLED"]
Role = Literal["buyer", "seller"]


class OfferModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CounterOffer(OfferModel):
    amount: Price
    client_offer_id: str = Field(strict=True, min_length=36, max_length=36)
    _client_id = field_validator("client_offer_id")(validate_client_id)


class OfferCreate(CounterOffer):
    conversation_ref: ConversationRef


class OfferResponse(OfferModel):
    offer_ref: OfferRef
    conversation_ref: ConversationRef
    product_slug: ProductSlug
    role: Role
    proposer_role: Role
    amount: str
    currency: Literal["CNY"]
    status: OfferStatus
    created_at: datetime
    expires_at: datetime
    closed_at: datetime | None
    closed_by_role: Role | None
    closure_reason: Literal["EXPIRED", "PRODUCT_UNAVAILABLE"] | None
    parent_offer_ref: OfferRef | None
    counteroffer_ref: OfferRef | None
    deal_ref: DealRef | None


class DealListQuery(OfferModel):
    limit: int = Field(default=20, strict=True, ge=1, le=50)
    cursor: str | None = Field(default=None, strict=True, min_length=1, max_length=512)
    conversation_ref: ConversationRef | None = None
    role: Role | None = None


class OfferListQuery(DealListQuery):
    status: OfferStatus | None = None


class OfferPage(OfferModel):
    items: list[OfferResponse] = Field(max_length=50)
    next_cursor: str | None = Field(max_length=512)


class OfferErrorResponse(OfferModel):
    detail: str


class ValidationItem(OfferModel):
    type: str
    loc: list[str | int]
    msg: str


class OfferValidationResponse(OfferModel):
    detail: str | list[ValidationItem]


OFFER_ERRORS = {
    code: {"model": OfferErrorResponse, "description": description}
    for code, description in {
        400: "Invalid or incorrectly scoped cursor.",
        401: "Valid bearer authentication and active account required.",
        403: "Forbidden participant role, verification or Origin.",
        404: "Missing resource or not a participant.",
        408: "Input deadline exceeded.",
        409: "State, expiry, availability or idempotency conflict.",
        413: "Actual body or query byte limit exceeded.",
        415: "JSON body requires application/json.",
        429: "Peer/account budget exceeded; Retry-After provided.",
        500: "Unexpected failure without private details.",
        503: "Persistence, authentication or pagination unavailable.",
    }.items()
}
OFFER_ERRORS[422] = {"model": OfferValidationResponse, "description": "Strict validation; submitted values are not echoed."}
