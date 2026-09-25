from pydantic import BaseModel, ConfigDict, Field


class FakeSmsLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phone_number: str = Field(min_length=1, max_length=32)


class FakeResetLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=1, max_length=254)


class ConsumeFakeMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
