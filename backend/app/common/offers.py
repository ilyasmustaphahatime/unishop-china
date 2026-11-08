"""Transport-independent offer policy and opaque pagination positions."""
from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID
from pydantic import ValidationError

STATUSES = ("PENDING", "ACCEPTED", "REJECTED", "WITHDRAWN", "COUNTERED", "EXPIRED", "CANCELLED")


def validate_input(body, model):
    try:
        return model.model_validate(body.model_dump() if isinstance(body, model) else body)
    except (ValidationError, ValueError, TypeError):
        raise OfferError("Invalid offer input.", 422) from None


class OfferError(Exception):
    def __init__(self, message="Resource not found.", status=404):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class OfferPosition:
    value: datetime
    reference: str


def validate_ref(value, kind):
    if not isinstance(value, str) or not re.fullmatch(kind + r"-[0-9a-f]{32}", value):
        raise ValueError("Invalid reference.")
    return value


def validate_client_id(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid client offer identifier.")
    return value


def effective_status(offer, now):
    return "EXPIRED" if offer.status == "PENDING" and offer.expires_at <= now else offer.status


def close_offer(offer, status, now, role=None):
    offer.status = status
    offer.closed_at = offer.expires_at if status == "EXPIRED" else now
    offer.closed_by_role = role
    offer.closure_reason = ("EXPIRED" if status == "EXPIRED" else
                            "PRODUCT_UNAVAILABLE" if status == "CANCELLED" else None)


def unique_pairs(pairs):
    """Reject ambiguous duplicate keys in bounded JSON and cursor payloads."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result
