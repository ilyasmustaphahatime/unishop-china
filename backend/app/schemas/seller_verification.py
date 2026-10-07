from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.models.seller_verification import EvidenceType, VerificationStatus
from app.common.plain_text import normalize_plain_text


class StartOrSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start", "submit", "renew_challenge"]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RejectRequest(ReviewRequest):
    rejection_reason: str = Field(min_length=3, max_length=500, strict=True)

    @field_validator("rejection_reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        value = normalize_plain_text(value, field_name="Reason", maximum=500, allow_newlines=False)
        if len(value) < 3:
            raise ValueError("A reason is required.")
        return value


class EvidenceAccessRequest(ReviewRequest):
    review_reference: str = Field(pattern=r"^[a-f0-9]{32}$", strict=True)
    evidence_type: EvidenceType


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_type: EvidenceType
    mime_type: str
    size: int


class VerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_reference: str
    status: VerificationStatus
    handwritten_challenge: str
    challenge_expires_at: datetime
    rejection_reason: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime
    evidence: list[EvidenceSummary]


class SignedEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    ticket: str
    expires_in: int
