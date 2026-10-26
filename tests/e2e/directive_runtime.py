"""Trusted directive fixture for Docker E2E only; never imported by production."""
import os
from pathlib import Path

from uai_runtime.hooks import HookRegistry, HookSubscriber
from uai_core.directives import Directive, DirectiveRegistry
from uai_core.models import Message
from pydantic import BaseModel, ConfigDict, Field
from uai_core.tools import ToolDefinition
from uai_runtime.app import from_env as runtime_from_env
from uai_runtime.tool_registry import default_tool_registry
from uai_runtime.tools.connectors import ConnectorDefinition, ConnectorRegistry
from uai_runtime.tools.http import HTTPToolBinding, HTTPToolExecutor

PREFIX = 'E2E directive: '


class PrefixDirective(Directive):
    async def before_model(self, context):
        last = context.model_input.messages[-1]
        return context.with_messages(context.model_input.messages[:-1] + (
            Message(role=last.role, content=PREFIX + last.content),))

    async def after_model(self, context):
        if PREFIX not in context.model_output:
            raise ValueError('fixture transformation missing from provider output')
        return context


class RejectOutputDirective(Directive):
    async def after_model(self, context):
        raise ValueError('private fixture diagnostic')


class ForeignHistoryDirective(Directive):
    async def before_model(self, context):
        return context.with_messages((Message(role='assistant', content='unauthorized fixture history'),
                                      context.model_input.messages[-1]))


async def trace_observation(event):
    # Test-only metadata sink in the runtime tmpfs; never stores model contents.
    path = Path(os.environ.get('UAI_E2E_TRACE_PATH', '/tmp/uai-e2e-trace.jsonl'))
    with path.open('a') as stream:
        stream.write(event.model_dump_json() + '\n')


class MockReadInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    q: str = Field(max_length=200)


class MockReadOutput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    result: str


def mock_tool_registry():
    tools = default_tool_registry()
    connector = ConnectorDefinition(id='mocktool', base_url='http://mock-tool:9100',
                                    methods={'GET'}, paths=('/read',), timeout=2,
                                    max_response_bytes=4096,
                                    private_networks=('172.16.0.0/12', '10.0.0.0/8'))
    definition = ToolDefinition(
        id='mocktool.read', name='Mock read', description='Read from the mock tool server',
        version='1.0.0', input_schema=MockReadInput.model_json_schema(),
        output_schema=MockReadOutput.model_json_schema(),
        permissions={'tools:execute', 'connector:mocktool'}, risk_level='read_only',
        timeout=2, retry_policy='never', executor='http')
    HTTPToolExecutor(ConnectorRegistry([connector])).register(
        tools, definition,
        binding=HTTPToolBinding(connector='mocktool', method='GET', path='/read'),
        input_model=MockReadInput, output_model=MockReadOutput)
    return tools


def from_env():
    registry = DirectiveRegistry()
    registry.register(PrefixDirective(name='e2e.prefix'))
    registry.register(RejectOutputDirective(name='e2e.reject', depends_on=('e2e.prefix',)))
    registry.register(ForeignHistoryDirective(name='e2e.foreign_history', priority=999999))
    hooks = HookRegistry()
    hooks.register(HookSubscriber(name='e2e.trace', callback=trace_observation))
    return runtime_from_env(directive_registry=registry, hook_registry=hooks,
                            tool_registry=mock_tool_registry())
