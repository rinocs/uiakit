"""Validate text completion without rewriting already streamed SSE deltas."""
import json

from jsonschema import Draft202012Validator

from ...directives import Directive


def _reject_constant(value: str):
    raise ValueError('non_finite_output')


class OutputValidationDirective(Directive):
    def __init__(self):
        super().__init__(name='builtin.output_validation', priority=3)

    async def after_model(self, context):
        output = context.model_output
        if not isinstance(output, str) or not output.strip() or len(output) > context.limits.max_output_chars:
            raise ValueError('invalid_output')
        schema = context.assistant.structured_output if context.assistant is not None else None
        if schema is not None:
            if context.model_definition is None or 'structured_output' not in context.model_definition.capabilities:
                raise ValueError('structured_output_unsupported')
            try:
                value = json.loads(output, parse_constant=_reject_constant)
                Draft202012Validator(schema).validate(value)
            except Exception:
                raise ValueError('invalid_structured_output') from None
        return context
