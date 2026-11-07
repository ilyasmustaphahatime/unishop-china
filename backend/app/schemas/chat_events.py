"""Strict versioned client events; transport never accepts a client-selected owner."""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, TypeAdapter, field_validator

from app.common.chat import validate_client_message_id, validate_message_content

MAX_EVENT_BYTES = 16384
ConversationReference = Annotated[str, Field(strict=True, pattern=r"^cv-[0-9a-f]{32}$", max_length=35)]


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    v: Literal[1]

    @field_validator("v", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int:
            raise ValueError("Invalid protocol version.")
        return value


class AuthenticateEvent(Event):
    type: Literal["authenticate"]
    access_token: SecretStr = Field(min_length=1, max_length=4096)


class SubscribeEvent(Event):
    type: Literal["subscribe"]
    conversation_ref: ConversationReference


class SendMessageEvent(Event):
    type: Literal["message.send"]
    conversation_ref: ConversationReference
    client_message_id: str = Field(min_length=36, max_length=36)
    content: str = Field(min_length=1, max_length=2000)

    _client_id = field_validator("client_message_id")(validate_client_message_id)
    _content = field_validator("content")(validate_message_content)


class PingEvent(Event):
    type: Literal["ping"]


ClientEvent = Annotated[AuthenticateEvent | SubscribeEvent | SendMessageEvent | PingEvent,
                        Field(discriminator="type")]
EVENT_ADAPTER = TypeAdapter(ClientEvent)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate event field.")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("Invalid JSON constant.")


def parse_event(value: str) -> ClientEvent:
    if len(value.encode("utf-8")) > MAX_EVENT_BYTES:
        raise ValueError("Event too large.")
    return EVENT_ADAPTER.validate_python(json.loads(value, object_pairs_hook=_unique_object,
                                                     parse_constant=_invalid_constant))
