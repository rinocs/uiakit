"""Per-run step, tool-call, token and context-window budgets."""
from dataclasses import dataclass, field

from uai_core.capabilities import ModelDefinition
from uai_core.configuration import ExecutionLimits
from .token_usage import UsageAccumulator, estimate_tokens

DEFAULT_MAX_STEPS = 4
DEFAULT_MAX_TOOL_CALLS = 8
DEFAULT_MAX_TOKENS = 8192


class BudgetExceeded(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _effective(value: int, default: int) -> int:
    return value if value and value > 0 else default


@dataclass
class RunBudget:
    max_steps: int
    max_tool_calls: int
    max_tokens: int
    model: ModelDefinition | None = None
    steps: int = field(default=0, init=False)
    tool_calls: int = field(default=0, init=False)

    @classmethod
    def from_limits(cls, limits: ExecutionLimits, model: ModelDefinition | None = None) -> 'RunBudget':
        return cls(max_steps=_effective(limits.max_steps, DEFAULT_MAX_STEPS),
                   max_tool_calls=_effective(limits.max_tool_calls, DEFAULT_MAX_TOOL_CALLS),
                   max_tokens=_effective(limits.max_tokens, DEFAULT_MAX_TOKENS), model=model)

    def start_step(self) -> None:
        if self.steps >= self.max_steps:
            raise BudgetExceeded('step_limit')
        self.steps += 1

    def consume_tool_calls(self, count: int) -> None:
        if self.tool_calls + count > self.max_tool_calls:
            raise BudgetExceeded('tool_call_limit')
        self.tool_calls += count

    def check_tokens(self, usage: UsageAccumulator) -> None:
        if usage.budget_tokens() > self.max_tokens:
            raise BudgetExceeded('token_limit')

    def check_context(self, *parts: str, output_tokens: int | None = None) -> None:
        window = self.model.context_window if self.model is not None else None
        if not window:
            return
        output = output_tokens
        if output is None:
            output = self.model.max_output_tokens if self.model.max_output_tokens else self.max_tokens
        estimated = estimate_tokens(''.join(parts)) + output
        if estimated > window:
            raise BudgetExceeded('context_window')
