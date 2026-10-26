"""Trusted, bounded middleware. This is an API boundary, not a Python sandbox."""
import asyncio
import logging
import math
import re
from dataclasses import dataclass
from typing import Literal

from .context import ExecutionContext

logger = logging.getLogger(__name__)
Phase = Literal['before_model', 'after_model']


class DirectiveError(Exception):
    """Safe terminal error; plugin exception details must not reach clients."""


@dataclass(frozen=True)
class Directive:
    name: str
    priority: int = 0
    depends_on: tuple[str, ...] = ()
    timeout_seconds: float = 5
    error_policy: Literal['fail', 'continue'] = 'fail'

    def __post_init__(self):
        if (not re.fullmatch(r'[a-z][a-z0-9_.-]{0,99}', self.name)
                or not isinstance(self.priority, int)
                or not isinstance(self.depends_on, tuple)
                or not all(isinstance(name, str) for name in self.depends_on)
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0
                or self.error_policy not in ('fail', 'continue')):
            raise ValueError('invalid_directive')

    async def before_model(self, context: ExecutionContext) -> ExecutionContext:
        return context

    async def after_model(self, context: ExecutionContext) -> ExecutionContext:
        """Validate model_output; output is already streamed."""
        return context


class DirectiveRegistry:
    """Host-owned registration. Mandatory entries cannot be replaced or deselected."""
    def __init__(self):
        self._entries: dict[str, tuple[Directive, bool, bool]] = {}

    def clone(self) -> "DirectiveRegistry":
        """Detach registration membership; existing executions retain their selection."""
        result = DirectiveRegistry()
        result._entries = self._entries.copy()
        return result

    def contains(self, name: str) -> bool:
        return name in self._entries


    def register(self, directive: Directive, *, mandatory: bool = False) -> None:
        if directive.name in self._entries:
            raise ValueError('duplicate_directive')
        self._entries[directive.name] = (directive, mandatory, False)

    def register_guard(self, directive: Directive) -> None:
        """Host validators run after middleware and cannot transform messages."""
        existing = self._entries.get(directive.name)
        if existing is not None:
            if existing[0] is directive and existing[1:] == (True, True):
                return
            raise ValueError('duplicate_directive')
        self._entries[directive.name] = (directive, True, True)

    def build(self, selected: tuple[str, ...] = ()) -> 'DirectivePipeline':
        if len(set(selected)) != len(selected):
            raise ValueError('duplicate_directive')
        pending = set(selected) | {name for name, (_, mandatory, _) in self._entries.items() if mandatory}
        if not pending <= self._entries.keys():
            raise ValueError('unknown_directive')
        if any(not set(self._entries[name][0].depends_on) <= pending for name in pending):
            raise ValueError('missing_directive_dependency')
        middleware = {name for name in pending if not self._entries[name][2]}
        dependencies = {name: set(self._entries[name][0].depends_on)
                        | (middleware if self._entries[name][2] else set()) for name in pending}
        ordered = []
        done = set()
        while pending:
            ready = [name for name in pending if dependencies[name] <= done]
            if not ready:
                raise ValueError('directive_cycle')
            name = min(ready, key=lambda name: (self._entries[name][0].priority, name))
            ordered.append(self._entries[name])
            done.add(name)
            pending.remove(name)
        return DirectivePipeline(tuple(ordered))


@dataclass(frozen=True)
class DirectivePipeline:
    entries: tuple[tuple[Directive, bool, bool], ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(directive.name for directive, _, _ in self.entries)

    async def apply(self, phase: Phase, context: ExecutionContext) -> ExecutionContext:
        if phase not in ('before_model', 'after_model'):
            raise ValueError('invalid_directive_phase')
        # Compare Pydantic data, not JSON: set/frozenset field order is not stable when serialized.
        protected = context.model_dump(exclude={'model_input'})
        model = context.model_input.model
        prompt = context.model_input.system_prompt
        memory = context.working_memory
        messages = context.model_input.messages
        for directive, mandatory, guard in self.entries:
            previous_messages = context.model_input.messages
            try:
                async with asyncio.timeout(directive.timeout_seconds):
                    result = await getattr(directive, phase)(context)
            except Exception:
                # Log identifiers only: exception text can contain prompts or credentials.
                logger.warning('directive_error name=%s phase=%s', directive.name, phase)
                if mandatory or directive.error_policy == 'fail':
                    raise DirectiveError('directive_failed') from None
                result = context
            try:
                if not isinstance(result, ExecutionContext) or result.working_memory is not memory:
                    raise ValueError('invalid_context')
                # Reconstruct from plain data: model_copy deliberately bypasses Pydantic validation.
                validated = ExecutionContext.model_validate({**result.model_dump(warnings=False), 'working_memory': memory})
                if (validated.model_dump(exclude={'model_input'}) != protected
                        or context.model_dump(exclude={'model_input'}) != protected
                        or validated.model_input.model != model
                        or validated.model_input.system_prompt != prompt
                        or (phase == 'after_model' and validated.model_input.messages != messages)
                        or (guard and validated.model_input.messages != previous_messages)
                        or (phase == 'before_model'
                            and sum(len(m.content) for m in validated.model_input.messages) + len(prompt)
                            > validated.limits.max_input_chars)):
                    raise ValueError('protected_context')
                context = validated
            except Exception:
                # Invalid contexts always fail closed, regardless of optional error policy.
                logger.warning('directive_invalid name=%s phase=%s', directive.name, phase)
                raise DirectiveError('directive_failed') from None
        return context
