"""Agent protocol and execution-state ownership independent of a web framework."""
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Protocol
from uuid import UUID

from .capabilities import ModelDefinition
from .configuration import AssistantConfig
from .context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from .events import RuntimeEvent
from .models import ModelInput
from .retrieval import IndexTarget


class Agent(Protocol):
    def run(self, context: ExecutionContext) -> AsyncIterator[RuntimeEvent]: ...


class AgentRuntime:
    def __init__(self, agent: Agent):
        self._agent = agent

    def run(self, *, run_id: UUID, correlation_id: UUID, authority: ExecutionAuthority,
            limits: ExecutionLimits, model_input: ModelInput, assistant: AssistantConfig | None = None,
            model_definition: ModelDefinition | None = None,
            retrieval_targets: tuple[IndexTarget, ...] = ()) -> AsyncGenerator[RuntimeEvent, None]:
        # A fresh state container even when run identifiers or input are reused.
        context = ExecutionContext(run_id=run_id, correlation_id=correlation_id,
                                   authority=authority, limits=limits, model_input=model_input,
                                   assistant=assistant, model_definition=model_definition,
                                   retrieval_targets=retrieval_targets)
        try:
            events = self._agent.run(context)  # preflight errors happen before HTTP starts streaming
        except BaseException:
            context.working_memory.clear()
            raise

        async def execute() -> AsyncGenerator[RuntimeEvent, None]:
            try:
                async for event in events:
                    yield event
            finally:
                try:
                    close = getattr(events, 'aclose', None)
                    if close is not None:
                        await close()
                finally:
                    context.working_memory.clear()

        return execute()
