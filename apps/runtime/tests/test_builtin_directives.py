import asyncio
from uuid import uuid4

import pytest

from uai_core.builtin.directives import (SystemPromptDirective, ConversationMemoryDirective,
    OutputValidationDirective, ObservabilityDirective, ToolPolicyDirective, install_builtin_directives)
from uai_core.configuration import AssistantConfig
from uai_core.context import ExecutionContext, ExecutionAuthority, ExecutionLimits
from uai_core.directives import Directive, DirectiveRegistry, DirectiveError
from uai_core.models import Message, ModelInput
from uai_core.tools import ToolDefinition


def context(*, memory=True, history=False):
    from test_capabilities import assistant_config
    config = assistant_config()
    config['memory']['conversation'] = memory
    messages = (Message(role='user', content='secret user message'),)
    if history:
        messages = (Message(role='user', content='old authorized question'),
                    Message(role='assistant', content='old authorized answer')) + messages
    return ExecutionContext(run_id=uuid4(), correlation_id=uuid4(),
        authority=ExecutionAuthority(principal_id='operator'), limits=ExecutionLimits(),
        assistant=AssistantConfig(**config), model_input=ModelInput(model='test', system_prompt='Helpful', messages=messages))


def test_operator_prompt_and_approved_history_are_preserved():
    ctx = context(history=True)
    for directive in [SystemPromptDirective(), ConversationMemoryDirective()]:
        result = asyncio.run(directive.before_model(ctx))
        assert result == ctx
    forged = ctx.model_copy(update={'model_input': ctx.model_input.model_copy(update={'system_prompt': 'override'})})
    with pytest.raises(ValueError):
        asyncio.run(SystemPromptDirective().before_model(forged))
    assert ctx.authorized_history == ctx.model_input.messages[:-1]


def test_conversation_memory_only_accepts_authorized_suffix_and_honors_disabled_memory():
    ctx = context(history=True)
    directive = ConversationMemoryDirective()
    trimmed = ctx.with_messages(ctx.model_input.messages[1:])
    assert asyncio.run(directive.before_model(trimmed)) == trimmed
    forged = ctx.with_messages((Message(role='assistant', content='foreign secret history'), ctx.model_input.messages[-1]))
    with pytest.raises(ValueError):
        asyncio.run(directive.before_model(forged))
    disabled = context(memory=False)
    assert asyncio.run(directive.before_model(disabled)) == disabled
    with pytest.raises(ValueError):
        asyncio.run(directive.before_model(disabled.with_messages(ctx.model_input.messages)))


@pytest.mark.parametrize('text', [None, '', ' \n\t ', 'x' * 64001])
def test_output_validation_rejects_nonconforming_completion(text):
    with pytest.raises(ValueError):
        asyncio.run(OutputValidationDirective().after_model(context().model_copy(update={'model_output': text})))


def test_valid_output_and_metadata_only_telemetry(caplog):
    ctx = context(history=True).with_output('secret model response')
    assert asyncio.run(OutputValidationDirective().after_model(ctx)) == ctx
    caplog.set_level('INFO')
    observer = ObservabilityDirective()
    asyncio.run(observer.before_model(ctx))
    asyncio.run(observer.after_model(ctx))
    assert str(ctx.run_id) in caplog.text and str(ctx.correlation_id) in caplog.text
    assert 'message_count=' in caplog.text and 'output_chars=' in caplog.text
    assert all(secret not in caplog.text for secret in ['Helpful', 'secret user', 'secret model', 'old authorized'])


def test_tool_policy_denies_even_granted_ids_and_cannot_disable_approval():
    directive = ToolPolicyDirective()
    ctx = context()
    ctx = ctx.model_copy(update={'authority': ExecutionAuthority(principal_id='admin', scopes={'*'}, allowed_tool_ids={'execute'})})
    tool = ToolDefinition(id='execute', name='Execute', description='', version='1.0.0',
                          input_schema={'type': 'object'}, output_schema={'type': 'object'},
                          permissions={'tools:execute'}, risk_level='read_only')
    with pytest.raises(PermissionError):
        directive.authorize_tool(ctx, tool)
    config = ctx.assistant.model_copy(update={'policy': ctx.assistant.policy.model_copy(update={'require_tool_approval': False})})
    with pytest.raises(ValueError):
        asyncio.run(directive.before_model(ctx.model_copy(update={'assistant': config})))
    selected = ctx.assistant.model_copy(update={'tools': ('execute',)})
    assert asyncio.run(directive.before_model(ctx.model_copy(update={'assistant': selected}))) is not None


def test_guards_cannot_be_removed_replaced_or_bypassed_by_late_middleware():
    registry = DirectiveRegistry()
    install_builtin_directives(registry)
    install_builtin_directives(registry)  # Reusing a host registry must be safe.
    names = set(registry.build(()).names)
    assert names == {'builtin.system_prompt', 'builtin.conversation_memory', 'builtin.output_validation',
                     'builtin.observability', 'builtin.tool_policy'}
    with pytest.raises(ValueError):
        registry.register(Directive(name='builtin.tool_policy'))
    class ForeignHistory(Directive):
        async def before_model(self, ctx):
            return ctx.with_messages((Message(role='assistant', content='unauthorized history'), ctx.model_input.messages[-1]))
    registry.register(ForeignHistory(name='late', priority=999999))
    pipeline = registry.build(('late',))
    assert pipeline.names[0] == 'late'
    with pytest.raises(DirectiveError):
        asyncio.run(pipeline.apply('before_model', context()))
    registry.register(Directive(name='after-guard', depends_on=('builtin.tool_policy',)))
    with pytest.raises(ValueError):
        registry.build(('after-guard',))


def test_guard_cannot_transform_the_context_it_validates():
    class MutatingGuard(Directive):
        async def before_model(self, ctx):
            return ctx.with_messages((Message(role='user', content='changed'),))
    registry = DirectiveRegistry()
    registry.register_guard(MutatingGuard(name='guard', error_policy='continue'))
    with pytest.raises(DirectiveError):
        asyncio.run(registry.build().apply('before_model', context()))


def test_default_runtime_checks_output_and_keeps_guards_with_custom_registry():
    from test_capabilities import send, body
    from uai_runtime.app import create_app
    from uai_core.providers import ModelChunk
    class Whitespace:
        async def stream(self, request):
            yield ModelChunk(text=' \n ')
    response = send(create_app('internal-secret', Whitespace()), '/internal/v1/runs', body())
    assert 'directive_failed' in response.text and 'response.completed' not in response.text
    class ForeignHistory(Directive):
        async def before_model(self, ctx):
            return ctx.with_messages((Message(role='assistant', content='foreign'), ctx.model_input.messages[-1]))
    class Never:
        async def stream(self, request):
            pytest.fail('unauthorized history reached model')
            yield
    registry = DirectiveRegistry()
    registry.register(ForeignHistory(name='late', priority=99999), mandatory=True)
    response = send(create_app('internal-secret', Never(), directive_registry=registry), '/internal/v1/runs', body())
    assert 'directive_failed' in response.text and 'response.completed' not in response.text


def test_history_provenance_cannot_be_rewritten_through_model_copy():
    class Forge(Directive):
        async def before_model(self, ctx):
            forged = (Message(role='assistant', content='foreign'), ctx.model_input.messages[-1])
            return ctx.with_messages(forged).model_copy(update={'authorized_history': forged[:-1]})
    registry = DirectiveRegistry()
    registry.register(Forge(name='forge'))
    install_builtin_directives(registry)
    with pytest.raises(DirectiveError):
        asyncio.run(registry.build(('forge',)).apply('before_model', context()))


def test_custom_registry_cannot_preempt_reserved_builtin_names():
    from uai_runtime.app import create_app
    from test_capabilities import Provider
    registry = DirectiveRegistry()
    registry.register(Directive(name='builtin.tool_policy'))
    with pytest.raises(ValueError, match='duplicate_directive'):
        create_app('internal-secret', Provider(), directive_registry=registry)


def test_builtin_installation_keeps_future_host_registrations_visible():
    from uai_runtime.app import create_app
    from test_capabilities import send
    registry = DirectiveRegistry()
    app = create_app('internal-secret', object(), directive_registry=registry)
    registry.register(Directive(name='later'))
    response = send(app, '/internal/v1/directives/validate', {'directives': ['later']})
    assert response.status_code == 204
    # A second factory using the registry shares the same mandatory guards.
    create_app('internal-secret', object(), directive_registry=registry)
    assert len(registry.build(('later',)).names) == 6
