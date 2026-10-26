"""The operator prompt belongs to the immutable assistant snapshot."""
from ...directives import Directive


class SystemPromptDirective(Directive):
    def __init__(self):
        super().__init__(name='builtin.system_prompt', priority=0)

    async def before_model(self, context):
        if context.assistant is not None and context.model_input.system_prompt != context.assistant.system_prompt:
            raise ValueError('assistant_prompt_mismatch')
        return context
