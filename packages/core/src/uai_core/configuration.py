"""Immutable assistant version consumed by one run; no secrets or provider URLs."""
import json
import re
from typing import Annotated, Self
from uuid import UUID

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


DirectiveNames = Annotated[tuple[Annotated[str, Field(pattern=r'^[a-z][a-z0-9_.-]{0,99}$')], ...],
                           Field(max_length=64)]


class ExecutionLimits(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    max_input_chars: int = Field(default=64000, gt=0)
    max_output_chars: int = Field(default=64000, gt=0)
    duration_seconds: float = Field(default=120, gt=0)
    # Zero keeps the deployment default for assistants persisted before M4-07.
    max_steps: int = Field(default=4, ge=0, le=16)
    max_tool_calls: int = Field(default=8, ge=0, le=32)
    max_tokens: int = Field(default=8192, ge=0, le=1_000_000)


class MemoryConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    conversation: bool = True
    semantic: bool = False


class AssistantPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    require_tool_approval: bool = True


class AssistantConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: UUID
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=4000)
    model: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(max_length=16000)
    directives: DirectiveNames = ()
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    knowledge_base_ids: tuple[UUID, ...] = ()
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    limits: ExecutionLimits = Field(default_factory=ExecutionLimits)
    policy: AssistantPolicy = Field(default_factory=AssistantPolicy)
    structured_output: dict[str, JsonValue] | None = None

    @model_validator(mode='after')
    def reject_unimplemented_features(self) -> Self:
        if self.skills or self.memory.semantic or not self.policy.require_tool_approval:
            raise ValueError('unsupported_assistant_feature')
        if len(set(self.knowledge_base_ids)) != len(self.knowledge_base_ids):
            raise ValueError('duplicate_knowledge_base')
        if len(set(self.tools)) != len(self.tools) or any(
                not isinstance(tool, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}', tool)
                for tool in self.tools):
            raise ValueError('invalid_tool_selection')
        if self.structured_output is not None:
            if not self.structured_output:
                raise ValueError('invalid_structured_output_schema')
            try:
                encoded = json.dumps(self.structured_output, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')
            except (TypeError, ValueError):
                raise ValueError('invalid_structured_output_schema') from None
            if len(encoded) > 16384:
                raise ValueError('invalid_structured_output_schema')
            try:
                Draft202012Validator.check_schema(self.structured_output)
            except Exception:
                raise ValueError('invalid_structured_output_schema') from None
        return self
