"""Only the gateway-authorized conversation prefix can enter the model history."""
from ...directives import Directive


class ConversationMemoryDirective(Directive):
    def __init__(self):
        super().__init__(name='builtin.conversation_memory', priority=1)

    async def before_model(self, context):
        messages = context.model_input.messages
        if messages[-1].role != 'user':
            raise ValueError('missing_current_user_message')
        history = messages[:-1]
        if context.assistant is not None and not context.assistant.memory.conversation:
            if history:
                raise ValueError('conversation_memory_disabled')
        else:
            authorized = context.authorized_history or ()
            if len(history) > len(authorized) or (history and history != authorized[-len(history):]):
                raise ValueError('unauthorized_conversation_history')
        return context
