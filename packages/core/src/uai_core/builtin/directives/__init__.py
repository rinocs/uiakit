"""Host-installed validators; assistant selections cannot disable these guards."""
from ...directives import DirectiveRegistry
from .system_prompt import SystemPromptDirective
from .conversation_memory import ConversationMemoryDirective
from .output_validation import OutputValidationDirective
from .observability import ObservabilityDirective
from .tool_policy import ToolPolicyDirective

_GUARDS = (SystemPromptDirective(), ConversationMemoryDirective(), ToolPolicyDirective(),
           OutputValidationDirective(), ObservabilityDirective())


def install_builtin_directives(registry: DirectiveRegistry) -> None:
    for directive in _GUARDS:
        registry.register_guard(directive)


__all__ = ['SystemPromptDirective', 'ConversationMemoryDirective', 'OutputValidationDirective',
           'ObservabilityDirective', 'ToolPolicyDirective', 'install_builtin_directives']
