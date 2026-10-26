"""Versioned HTTP DTO; shared execution types live in uai-core."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from uai_core.context import ExecutionAuthority
from uai_core.capabilities import ModelDefinition
from uai_core.configuration import AssistantConfig, DirectiveNames
from uai_core.embeddings import EmbeddingModel
from uai_core.events import (CompletedPayload, FailedPayload, RuntimeEvent,
                             RuntimeEventType, StartedPayload, TextPayload)
from uai_core.models import Message
from uai_core.retrieval import IndexTarget


class DirectiveSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    directives: DirectiveNames


class RetrievalTargetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    knowledge_base_id: UUID
    collection: str = Field(pattern=r'^[a-z0-9][a-z0-9_-]{0,63}$')
    index_version: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_provider: Literal['ollama', 'openai-compatible']
    embedding_model: str = Field(min_length=1, max_length=200)
    embedding_version: str = Field(min_length=1, max_length=200)
    embedding_dimension: int = Field(ge=1, le=8192)

    def to_index_target(self) -> IndexTarget:
        return IndexTarget(
            knowledge_base_id=str(self.knowledge_base_id), collection=self.collection,
            index_version=self.index_version,
            embedding=EmbeddingModel(id=self.embedding_model, provider=self.embedding_provider,
                                     dimension=self.embedding_dimension,
                                     version=self.embedding_version))


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_id: UUID
    correlation_id: UUID
    model: str = Field(min_length=1, max_length=200)
    system_prompt: str = Field(max_length=16000)
    messages: list[Message] = Field(min_length=1, max_length=100)
    assistant: AssistantConfig | None = None
    model_snapshot: ModelDefinition | None = None
    retrieval_targets: list[RetrievalTargetInput] = Field(default_factory=list, max_length=64)
    authority: ExecutionAuthority = Field(default_factory=lambda: ExecutionAuthority(principal_id="bootstrap-operator"))


# Compatibility imports for existing runtime clients; definitions live only in core.
__all__ = ['DirectiveSelection', 'RetrievalTargetInput', 'RunRequest', 'Message', 'RuntimeEvent',
           'RuntimeEventType', 'StartedPayload', 'TextPayload', 'CompletedPayload', 'FailedPayload']
