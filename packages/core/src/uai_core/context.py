"""Authority belongs to the caller, contents to the model input, state to the run."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .configuration import AssistantConfig, ExecutionLimits
from .capabilities import ModelDefinition
from .memory import WorkingMemory
from .retrieval import IndexTarget
from .models import Message, ModelInput


class ExecutionAuthority(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    principal_id: str = Field(min_length=1, max_length=200)
    scopes: frozenset[str] = frozenset()
    allowed_tool_ids: frozenset[str] = frozenset()


class ExecutionContext(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, arbitrary_types_allowed=True)
    run_id: UUID
    correlation_id: UUID
    authority: ExecutionAuthority
    limits: ExecutionLimits
    model_input: ModelInput
    authorized_history: tuple[Message, ...] | None = None
    model_output: str | None = None
    assistant: AssistantConfig | None = None
    model_definition: ModelDefinition | None = None
    retrieval_targets: tuple[IndexTarget, ...] = ()
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory, exclude=True)

    @model_validator(mode='after')
    def capture_authorized_history(self):
        if self.authorized_history is None:
            # Capture once at the trusted run boundary, never from middleware output.
            object.__setattr__(self, 'authorized_history', self.model_input.messages[:-1])
        return self

    def with_messages(self, messages: tuple[Message, ...]) -> 'ExecutionContext':
        """Replace model contents without granting a route to policy/prompt changes."""
        new_input = ModelInput(model=self.model_input.model,
                               system_prompt=self.model_input.system_prompt, messages=messages,
                               tools=self.model_input.tools)
        return ExecutionContext(run_id=self.run_id, correlation_id=self.correlation_id,
                                authority=self.authority, limits=self.limits,
                                model_input=new_input, working_memory=self.working_memory,
                                assistant=self.assistant, model_definition=self.model_definition,
                                model_output=self.model_output, authorized_history=self.authorized_history,
                                retrieval_targets=self.retrieval_targets)

    def with_output(self, text: str) -> 'ExecutionContext':
        """Attach immutable generated output for after-model validation."""
        return ExecutionContext(run_id=self.run_id, correlation_id=self.correlation_id,
                                authority=self.authority, limits=self.limits,
                                model_input=self.model_input, working_memory=self.working_memory,
                                assistant=self.assistant, model_definition=self.model_definition,
                                model_output=text, authorized_history=self.authorized_history,
                                retrieval_targets=self.retrieval_targets)
