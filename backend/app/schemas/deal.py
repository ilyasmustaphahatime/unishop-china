"""Private immutable agreement projection, not an order or fulfillment contract."""
from datetime import datetime
from typing import Literal

from pydantic import Field
from app.common.product_slugs import ProductSlug
from app.schemas.conversation import ConversationRef
from app.schemas.offer import DealRef, OfferRef, OfferModel, Role


class DealResponse(OfferModel):
    deal_ref: DealRef
    accepted_offer_ref: OfferRef
    conversation_ref: ConversationRef
    product_slug: ProductSlug
    role: Role
    amount: str
    currency: Literal["CNY"]
    status: Literal["AGREED"] = "AGREED"
    agreed_at: datetime
    product_title_snapshot: str
    product_condition_snapshot: Literal["new", "like_new", "good", "fair"]


class DealPage(OfferModel):
    items: list[DealResponse] = Field(max_length=50)
    next_cursor: str | None = Field(max_length=512)
