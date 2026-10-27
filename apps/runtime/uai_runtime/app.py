"""Private runtime. Only the gateway can submit authorized execution context."""
from contextlib import aclosing, ExitStack, suppress
import asyncio
import hashlib
import hmac
import os
from types import MappingProxyType
from typing import Annotated

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from .telemetry import TelemetryMiddleware
from uai_core.telemetry import get_telemetry
from starlette.background import BackgroundTask
from pydantic import JsonValue
from uai_core.builtin.directives import install_builtin_directives
from uai_core.builtin.directives.rag_retrieval import RAGRetrievalDirective
from uai_core.builtin.directives.tool_policy import ToolPolicyDirective
from uai_core.retrieval import Retriever
from uai_core.storage import BlobNotFound, BlobStore, BlobStoreError
from .plugin_manager import PluginConfiguration, PluginManager, PluginToolExecutor
from .storage import S3BlobStore, filesystem_from_env
from .rag.retriever import retriever_from_env
from .run_state import RunStateRegistry, cancel_aware_events
from .providers import OllamaProvider

from uai_core.directives import DirectiveRegistry
from uai_core.capabilities import ModelDefinition
from uai_core.agent import AgentRuntime
from uai_core.context import ExecutionLimits
from uai_core.models import ModelInput

from .agent import BasicAgent
from .egress import EgressPolicy
from .hooks import HookRegistry
from .secrets import secret_from_env
from .tool_registry import ToolRegistry, default_tool_registry
from .tool_executor import ExecutionJournal, GatewayExecutionJournal
from .audit import AuditLog
from .plugins.http_plugin import IsolatedConfig, isolated_plugin_from_env
from .tool_loop import ToolCallingAgent
from uai_core.tools import ToolDefinition
from .models import DirectiveSelection, RunRequest
from .provider import ModelProvider, OpenAIProvider
from .provider_control import (ActiveProvider, ModelDiscovery, ProviderConfig,
                               ProviderConfigError, ProviderDiscoveryConfig,
                               ProviderModelInput, ProviderRegistry, ProviderState,
                               ProviderValidation, control_loop, discover_models,
                               make_active, state_of)


def create_app(api_key: str, provider: ModelProvider, *, max_output_chars: int = 64000,
               max_input_chars: int = 64000, duration_seconds: float = 120,
               allowed_model: str = 'test', model_definition: ModelDefinition | None = None,
               directive_registry: DirectiveRegistry | None = None,
               hook_registry: HookRegistry | None = None,
               tool_registry: ToolRegistry | None = None, approved_plugins=(),
               blob_store: BlobStore | None = None, retriever: Retriever | None = None,
               tool_policy: ToolPolicyDirective | None = None,
               execution_journal: ExecutionJournal | None = None,
               audit_log: AuditLog | None = None,
               provider_config: ProviderConfig | None = None,
               egress: EgressPolicy | None = None,
               control_plane_url: str | None = None,
               discovery_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    if len(api_key) < 8:
        raise ValueError('Internal API key must contain at least 8 characters')
    expected = hashlib.sha256(f'Bearer {api_key}'.encode()).digest()

    def require_internal(authorization: str) -> None:
        if not hmac.compare_digest(hashlib.sha256(authorization.encode()).digest(), expected):
            raise HTTPException(401, detail='unauthorized')

    async def lifespan(_app: FastAPI):
        task = (asyncio.create_task(control_loop(_app, control_plane_url, api_key))
                if control_plane_url else None)
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title='UAI Internal Runtime', version='0.1.0', docs_url=None,
                  redoc_url=None, lifespan=lifespan)
    app.add_middleware(TelemetryMiddleware)

    limits = ExecutionLimits(max_output_chars=max_output_chars, max_input_chars=max_input_chars,
                             duration_seconds=duration_seconds)
    definition = model_definition or ModelDefinition(id=allowed_model, capabilities={'chat', 'streaming'},
                                                       max_output_tokens=getattr(provider, 'max_tokens', None))
    if definition.id != allowed_model:
        raise ValueError('model_definition_mismatch')
    if provider_config is None:
        provider_config = ProviderConfig(
            revision=0,
            provider=definition.provider,
            base_url=getattr(provider, 'base_url',
                             getattr(provider, '_base_url', 'http://provider.invalid')),
            api_key_ref='',
            max_output_tokens=min(8192, max(1, definition.max_output_tokens
                                            or getattr(provider, 'max_tokens', 1024) or 1024)),
            models=[ProviderModelInput(
                id=definition.id,
                capabilities=frozenset(capability for capability in definition.capabilities
                                       if capability in ('tool_calling', 'structured_output')),
                context_window=definition.context_window,
            )],
        )
    active_provider = ActiveProvider(
        provider=provider,
        definitions=MappingProxyType({definition.id: definition}),
        config=provider_config,
        api_key_configured=bool(getattr(provider, 'api_key', '')),
    )
    app.state.providers = ProviderRegistry(active_provider)
    app.state.egress = egress
    app.state.notified_revision = 0
    app.state.discovery_transport = discovery_transport
    directives = directive_registry if directive_registry is not None else DirectiveRegistry()
    tools = tool_registry if tool_registry is not None else default_tool_registry()
    install_builtin_directives(directives)
    if not directives.contains('builtin.rag'):
        directives.register(RAGRetrievalDirective(retriever))
    manager = PluginManager(approved_plugins, directives=directives, tools=tools, hooks=hook_registry)
    app.state.plugin_manager = manager
    app.state.tool_executor = PluginToolExecutor(manager, policy=tool_policy)
    app.state.blob_store = blob_store
    run_states = RunStateRegistry()
    app.state.run_state = run_states

    @app.get('/internal/v1/health')
    def health():
        return {'status': 'ok', 'version': '0.1.0'}

    @app.get('/internal/v1/models')
    async def models(authorization: Annotated[str, Header()] = '') -> list[ModelDefinition]:
        require_internal(authorization)
        active = app.state.providers.snapshot()
        return [active.definitions[key] for key in sorted(active.definitions)]

    @app.get('/internal/v1/provider/state', response_model=ProviderState)
    async def provider_state(authorization: Annotated[str, Header()] = '') -> ProviderState:
        require_internal(authorization)
        return state_of(app.state.providers.snapshot())

    @app.post('/internal/v1/provider/validate', response_model=ProviderValidation)
    async def validate_provider(
            body: ProviderConfig,
            authorization: Annotated[str, Header()] = '') -> ProviderValidation:
        require_internal(authorization)
        try:
            active = make_active(body, app.state.egress)
        except ProviderConfigError as error:
            raise HTTPException(422, detail=error.code) from None
        return ProviderValidation(api_key_configured=active.api_key_configured)

    @app.post('/internal/v1/provider/apply', response_model=ProviderState)
    async def apply_provider(
            body: ProviderConfig,
            authorization: Annotated[str, Header()] = '') -> ProviderState:
        require_internal(authorization)
        try:
            active = make_active(body, app.state.egress)
        except ProviderConfigError as error:
            raise HTTPException(422, detail=error.code) from None
        current = app.state.providers.replace(active)
        return state_of(current)

    @app.post('/internal/v1/provider/models', response_model=ModelDiscovery)
    async def list_provider_models(
            body: ProviderDiscoveryConfig,
            authorization: Annotated[str, Header()] = '') -> ModelDiscovery:
        require_internal(authorization)
        try:
            found = await discover_models(body, app.state.egress,
                                          transport=app.state.discovery_transport)
        except ProviderConfigError as error:
            raise HTTPException(422, detail=error.code) from None
        return ModelDiscovery(models=found)

    @app.get('/internal/v1/tools')
    async def tool_catalog(authorization: Annotated[str, Header()] = '') -> list[ToolDefinition]:
        if not hmac.compare_digest(hashlib.sha256(authorization.encode()).digest(), expected):
            raise HTTPException(401, detail='unauthorized')
        return manager.snapshot().tools.catalog()

    def authorize(authorization):
        if not hmac.compare_digest(hashlib.sha256(authorization.encode()).digest(), expected):
            raise HTTPException(401, detail='unauthorized')

    @app.get('/internal/v1/plugins')
    async def plugins(authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        return manager.catalog()

    @app.post('/internal/v1/plugins/validate', status_code=204, response_class=Response)
    async def validate_plugins(body: PluginConfiguration, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        try:
            manager.validate_configuration(body.model_dump()['settings'])
        except ValueError:
            raise HTTPException(422, detail='invalid_plugin_configuration') from None
        return Response(status_code=204)

    @app.post('/internal/v1/plugins/reconcile')
    async def reconcile_plugins(body: PluginConfiguration, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        try:
            applied = await manager.reconcile(body.revision, body.model_dump()['settings'])
        except ValueError:
            raise HTTPException(422, detail='invalid_plugin_configuration') from None
        return {'applied': applied, 'revision': manager.applied_revision}

    @app.post('/internal/v1/plugins/{plugin_id}/activate', status_code=204, response_class=Response)
    async def activate_plugin(plugin_id: str, config: dict[str, JsonValue],
                              authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        if not await manager.activate(plugin_id, config):
            raise HTTPException(409, detail='plugin_activation_failed')
        return Response(status_code=204)

    @app.post('/internal/v1/plugins/{plugin_id}/deactivate', status_code=204, response_class=Response)
    async def deactivate_plugin(plugin_id: str, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        if not await manager.deactivate(plugin_id):
            raise HTTPException(409, detail='plugin_deactivation_failed')
        return Response(status_code=204)

    @app.get('/internal/v1/plugins/{plugin_id}/health')
    async def plugin_health(plugin_id: str, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        return await manager.health(plugin_id)

    @app.post('/internal/v1/directives/validate', status_code=204, response_class=Response)
    async def validate_directives(body: DirectiveSelection, authorization: Annotated[str, Header()] = ''):
        if not hmac.compare_digest(hashlib.sha256(authorization.encode()).digest(), expected):
            raise HTTPException(401, detail='unauthorized')
        try:
            manager.snapshot().directives.build(body.directives)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post('/internal/v1/runs')
    async def run(body: RunRequest, authorization: Annotated[str, Header()] = ''):
        require_internal(authorization)
        active = app.state.providers.snapshot()
        provider = active.provider
        definition = active.definitions.get(body.model)
        if definition is None:
            raise HTTPException(422, detail='model_unavailable')
        if body.model_snapshot is not None and body.model_snapshot != definition:
            raise HTTPException(409, detail='model_configuration_changed')
        if body.assistant is not None and (body.model != body.assistant.model
                                          or body.system_prompt != body.assistant.system_prompt):
            raise HTTPException(422, detail='assistant_snapshot_mismatch')
        if body.assistant is not None and not body.assistant.memory.conversation and len(body.messages) != 1:
            raise HTTPException(422, detail='conversation_memory_disabled')
        effective_limits = limits
        if body.assistant is not None:
            requested = body.assistant.limits
            effective_limits = ExecutionLimits(
                max_input_chars=min(limits.max_input_chars, requested.max_input_chars),
                max_output_chars=min(limits.max_output_chars, requested.max_output_chars),
                duration_seconds=min(limits.duration_seconds, requested.duration_seconds),
                max_steps=min(limits.max_steps, requested.max_steps),
                max_tool_calls=min(limits.max_tool_calls, requested.max_tool_calls),
                max_tokens=min(limits.max_tokens, requested.max_tokens))
        uses_tools = body.assistant is not None and bool(body.assistant.tools)
        if uses_tools and 'tool_calling' not in definition.capabilities:
            raise HTTPException(422, detail='tool_calling_unsupported')
        if (body.assistant is not None and body.assistant.structured_output is not None
                and 'structured_output' not in definition.capabilities):
            raise HTTPException(422, detail='structured_output_unsupported')
        lease = ExitStack()
        cancel_event = run_states.register(str(body.run_id))
        try:
            snapshot = lease.enter_context(manager.execution())
            if uses_tools:
                agent = ToolCallingAgent(provider, model_definition=definition,
                    directive_registry=snapshot.directives, hook_registry=snapshot.hooks,
                    tool_executor=app.state.tool_executor,
                    tool_catalog=lambda catalog=snapshot.tools: catalog.catalog(),
                    execution_journal=execution_journal, audit_log=audit_log)
            else:
                agent = BasicAgent(provider, model_definition=definition,
                    directive_registry=snapshot.directives, hook_registry=snapshot.hooks)
            runtime = AgentRuntime(agent)
            events = runtime.run(run_id=body.run_id, correlation_id=body.correlation_id,
                                 authority=body.authority, limits=effective_limits,
                                 assistant=body.assistant, model_definition=definition,
                                 retrieval_targets=tuple(target.to_index_target()
                                                         for target in body.retrieval_targets),
                                 model_input=ModelInput(model=body.model,
                                                        system_prompt=body.system_prompt,
                                                        messages=tuple(body.messages)))
            events = cancel_aware_events(events, run_states, str(body.run_id),
                                         body.correlation_id, cancel_event)
        except BaseException as exc:
            run_states.unregister(str(body.run_id))
            lease.close()
            if isinstance(exc, ValueError):
                code = 503 if str(exc) in ('plugin_lifecycle_busy', 'plugin_configuration_pending') else 422
                raise HTTPException(code, detail=str(exc)) from exc
            raise

        async def generate():
            telemetry = get_telemetry('uai-runtime')
            try:
                async with aclosing(events):
                    with telemetry.span('runtime.run', {
                        'run_id': str(body.run_id),
                        'correlation_id': str(body.correlation_id),
                        'model': body.model,
                        'assistant_id': str(body.assistant.id) if body.assistant else '',
                    }):
                        async for event in events:
                            terminal = event.event_type in ('response.completed', 'agent.failed', 'agent.cancelled')
                            telemetry.record_event(event.event_type, terminal=terminal)
                            if event.event_type == 'response.completed':
                                usage = event.payload.usage or {}
                                telemetry.record_tokens(
                                    body.model,
                                    int(usage.get('input_tokens', 0)),
                                    int(usage.get('output_tokens', 0)),
                                )
                                telemetry.record_cost(
                                    body.model,
                                    int(usage.get('input_tokens', 0)),
                                    int(usage.get('output_tokens', 0)),
                                )
                            elif event.event_type == 'agent.failed':
                                telemetry.record_error(str(event.payload.code), 'runtime.run')
                            yield event.sse()
            finally:
                lease.close()

        async def release_lease():
            lease.close()

        return StreamingResponse(generate(), media_type='text/event-stream', background=BackgroundTask(release_lease),
                                 headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})

    @app.post('/internal/v1/runs/{run_id}/cancel', status_code=204, response_class=Response)
    async def cancel_run(run_id: str, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        if not run_states.cancel(run_id):
            raise HTTPException(404, detail='run_not_found')
        return Response(status_code=204)

    @app.put('/internal/v1/storage/{key:path}', status_code=204, response_class=Response)
    async def put_blob(key: str, request: Request, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        if blob_store is None:
            raise HTTPException(503, detail='storage_unavailable')
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > 32 * 1024 * 1024:
                raise HTTPException(413, detail='blob_too_large')
            data.extend(chunk)
        try:
            await blob_store.put(key, bytes(data))
        except ValueError:
            raise HTTPException(422, detail='invalid_blob_key') from None
        except BlobStoreError:
            raise HTTPException(503, detail='storage_unavailable') from None
        return Response(status_code=204)

    @app.get('/internal/v1/storage/{key:path}')
    async def get_blob(key: str, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        if blob_store is None:
            raise HTTPException(503, detail='storage_unavailable')
        try:
            data = await blob_store.get(key)
        except ValueError:
            raise HTTPException(422, detail='invalid_blob_key') from None
        except BlobNotFound:
            raise HTTPException(404, detail='blob_not_found') from None
        except BlobStoreError:
            raise HTTPException(503, detail='storage_unavailable') from None
        return Response(content=data, media_type='application/octet-stream')

    @app.delete('/internal/v1/storage/{key:path}', status_code=204, response_class=Response)
    async def delete_blob(key: str, authorization: Annotated[str, Header()] = ''):
        authorize(authorization)
        if blob_store is None:
            raise HTTPException(503, detail='storage_unavailable')
        try:
            await blob_store.delete(key)
        except ValueError:
            raise HTTPException(422, detail='invalid_blob_key') from None
        except BlobStoreError:
            raise HTTPException(503, detail='storage_unavailable') from None
        return Response(status_code=204)

    return app


def from_env(*, directive_registry: DirectiveRegistry | None = None,
             hook_registry: HookRegistry | None = None,
             tool_registry: ToolRegistry | None = None) -> FastAPI:
    from uai_plugin_hello import HelloPlugin, HelloConfig
    model = os.environ['MODEL_NAME']
    internal_key = secret_from_env('INTERNAL_API_KEY', required=True)
    if len(internal_key) < 32:
        raise ValueError('Internal API key must contain at least 32 characters')
    egress = EgressPolicy.from_env()
    backend = os.environ.get('UAI_STORAGE_BACKEND', 'filesystem')
    if backend == 'filesystem':
        blob_store = filesystem_from_env()
    elif backend == 's3':
        blob_store = S3BlobStore.from_env()
    else:
        raise ValueError('invalid_storage_backend')
    model_provider = os.environ.get('MODEL_PROVIDER', 'openai-compatible')
    max_tokens = int(os.environ.get('MODEL_MAX_TOKENS', '1024'))
    if model_provider == 'ollama':
        provider_url = os.environ.get('OLLAMA_BASE_URL', 'http://ollama:11434')
        provider = OllamaProvider(provider_url, max_tokens=max_tokens)
        api_key_ref = ''
    elif model_provider == 'openai-compatible':
        provider_url = os.environ['MODEL_BASE_URL']
        provider = OpenAIProvider(provider_url, secret_from_env('MODEL_API_KEY') or '',
                                  max_tokens=max_tokens)
        api_key_ref = 'MODEL_API_KEY'
    else:
        raise ValueError('invalid_model_provider')
    if egress is not None:
        egress.require(provider_url)
    retriever = retriever_from_env()
    allowed_connectors = frozenset(item.strip() for item in os.environ.get('TOOL_ALLOWED_CONNECTORS', '').split(',')
                                    if item.strip())
    approved_plugins = [(HelloPlugin(), HelloConfig)]
    isolated = isolated_plugin_from_env(allowed_connectors, egress=egress)
    if isolated is not None:
        approved_plugins.append((isolated, IsolatedConfig))
    capabilities = {'chat', 'streaming'}
    if os.environ.get('MODEL_TOOL_CALLING', '').lower() in ('1', 'true', 'yes'):
        capabilities.add('tool_calling')
    if os.environ.get('MODEL_STRUCTURED_OUTPUT', '').lower() in ('1', 'true', 'yes'):
        capabilities.add('structured_output')
    context_window = os.environ.get('MODEL_CONTEXT_WINDOW', '').strip()
    model_definition = ModelDefinition(id=model, provider=model_provider,
                                       capabilities=capabilities,
                                       max_output_tokens=getattr(provider, 'max_tokens', None),
                                       context_window=int(context_window) if context_window else None)
    gateway_url = os.environ.get('GATEWAY_URL', '').rstrip('/')
    provider_config = ProviderConfig(
        revision=0,
        provider=model_provider,
        base_url=provider_url,
        api_key_ref=api_key_ref,
        max_output_tokens=max_tokens,
        models=[ProviderModelInput(
            id=model,
            capabilities=frozenset(capability for capability in capabilities
                                   if capability in ('tool_calling', 'structured_output')
                                   and model_provider == 'openai-compatible'),
            context_window=int(context_window) if context_window else None,
        )],
    )
    execution_journal = (GatewayExecutionJournal(gateway_url, internal_key)
                         if gateway_url else None)
    return create_app(internal_key, provider,
                      allowed_model=model, model_definition=model_definition,
                      provider_config=provider_config, egress=egress,
                      control_plane_url=gateway_url or None,
                      directive_registry=directive_registry, hook_registry=hook_registry,
                      tool_registry=tool_registry, approved_plugins=approved_plugins,
                      blob_store=blob_store, retriever=retriever,
                      tool_policy=ToolPolicyDirective(allowed_connectors=allowed_connectors),
                      execution_journal=execution_journal, audit_log=AuditLog())
