"""Public-safe model metadata. Missing capabilities are unsupported, never guessed."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

Capability = Literal['chat', 'streaming', 'tool_calling', 'structured_output',
                     'embeddings', 'reranking', 'vision']
ProviderKind = Literal['openai-compatible', 'ollama']


class ModelDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=200)
    provider: ProviderKind = 'openai-compatible'
    capabilities: frozenset[Capability]
    max_output_tokens: int | None = Field(default=None, gt=0)
    context_window: int | None = Field(default=None, gt=0)

    def require(self, *capabilities: Capability) -> None:
        if not set(capabilities).issubset(self.capabilities):
            raise ValueError('unsupported_capability')

    @field_serializer('capabilities')
    def serialize_capabilities(self, capabilities: frozenset[Capability]) -> list[str]:
        return sorted(capabilities)

