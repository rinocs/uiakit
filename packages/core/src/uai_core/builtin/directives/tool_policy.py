"""Host-owned effective tool authorization and the text-agent profile guard."""
from ...directives import Directive
from ...tools import ToolDefinition


class ToolPolicyDirective(Directive):
    """Intersect every authority owner before an effect can be authorized.

    The text-only BasicAgent keeps rejecting tool-enabled assistant snapshots in
    ``before_model``. The same object also owns the executor's authorization so a
    future tool loop cannot introduce a second, weaker policy path.
    """

    def __init__(self, *, allowed_connectors: frozenset[str] = frozenset()):
        super().__init__(name='builtin.tool_policy', priority=2)
        self.allowed_connectors = frozenset(allowed_connectors)

    async def before_model(self, context):
        if context.assistant is not None and not context.assistant.policy.require_tool_approval:
            raise ValueError('tool_approval_required')
        return context

    def authorize_tool(self, context, definition: ToolDefinition) -> None:
        connector_permissions = {permission for permission in definition.permissions
                                 if permission.startswith('connector:')}
        # Connector access is an administrative host allowlist, not a principal
        # scope: gateway principals receive tools:execute, while the deployment
        # decides which connectors may be reached.
        required = (definition.permissions - connector_permissions) | {'tools:execute'}
        if (definition.id not in context.authority.allowed_tool_ids
                or not required <= context.authority.scopes
                or (context.assistant is not None and definition.id not in context.assistant.tools)
                or not connector_permissions <= self._approved_connector_permissions()):
            raise PermissionError('forbidden')
        # The caller granted the tool, but effects still need approval (M4-04).
        if definition.risk_level != 'read_only':
            raise PermissionError('approval_required')

    def _approved_connector_permissions(self) -> frozenset[str]:
        return frozenset(f'connector:{connector}' for connector in self.allowed_connectors)
