"""Immutable model input: no service credentials, policy or execution authority."""
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, json_schema_extra={
        'allOf': [{'if': {'properties': {'role': {'const': 'user'}}},
                   'then': {'properties': {'content': {'maxLength': 32000}}}}]
    })
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=64000)

    @model_validator(mode='after')
    def validate_user_limit(self) -> Self:
        if self.role == 'user' and len(self.content) > 32000:
            raise ValueError('user_message_limit')
        return self


class ModelInput(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    model: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(max_length=16000)
    messages: tuple[Message, ...] = Field(min_length=1, max_length=100)
    provider_messages: tuple[dict[str, JsonValue], ...] = Field(default=(), max_length=200)
    tools: tuple[dict[str, JsonValue], ...] = Field(default=(), max_length=64)
    structured_output: dict[str, JsonValue] | None = None
