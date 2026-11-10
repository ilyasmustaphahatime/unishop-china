"""Existing safe HTTP error shapes shared by documented API contracts."""
from pydantic import BaseModel, ConfigDict


class ErrorCodeDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class ValidationErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    loc: list[str | int]
    msg: str


class SafeErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detail: str | ErrorCodeDetail | list[ValidationErrorDetail]
