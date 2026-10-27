import asyncio

import httpx

from uai_runtime.app import create_app
from uai_runtime.egress import EgressPolicy
from uai_runtime.provider_control import (ProviderConfig, ProviderDiscoveryConfig,
                                            ProviderRegistry, discover_models, make_active)


class Provider:
    async def stream(self, request):
        from uai_core.providers import ModelChunk
        yield ModelChunk(text='Ciao')


def send(app, path, body=None, authorized=True):
    async def perform():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://runtime') as client:
            headers = {'Authorization': 'Bearer internal-secret'} if authorized else {}
            return await (client.get(path, headers=headers) if body is None
                          else client.post(path, json=body, headers=headers))
    return asyncio.run(perform())


def config(models=None, **overrides):
    payload = {
        'revision': 1,
        'provider': 'openai-compatible',
        'base_url': 'http://provider/v1',
        'api_key_ref': '',
        'max_output_tokens': 256,
        'models': models or [{'id': 'test', 'capabilities': [], 'context_window': None}],
    }
    payload.update(overrides)
    return payload


def test_provider_endpoints_require_internal_auth():
    app = create_app('internal-secret', Provider())
    assert send(app, '/internal/v1/provider/state', None, authorized=False).status_code == 401
    assert send(app, '/internal/v1/provider/models', {
        'provider': 'openai-compatible', 'base_url': 'http://provider/v1', 'api_key_ref': '',
    }, authorized=False).status_code == 401
    assert send(app, '/internal/v1/provider/apply', config(), authorized=False).status_code == 401
    assert send(app, '/internal/v1/provider/validate', config(), authorized=False).status_code == 401


def test_apply_swaps_models_and_reports_state(monkeypatch):
    monkeypatch.setenv('MODEL_API_KEY', 'provider-secret')
    app = create_app('internal-secret', Provider())
    applied = send(app, '/internal/v1/provider/apply', config(
        api_key_ref='MODEL_API_KEY',
        models=[
            {'id': 'test', 'capabilities': [], 'context_window': None},
            {'id': 'second', 'capabilities': ['tool_calling'], 'context_window': 8192},
        ],
    ))
    assert applied.status_code == 200
    state = applied.json()
    assert state['revision'] == 1
    assert state['api_key_configured'] is True
    assert [model['id'] for model in state['models']] == ['second', 'test']
    assert state['models'][0]['capabilities'] == ['chat', 'streaming', 'tool_calling']

    catalog = send(app, '/internal/v1/models')
    assert [model['id'] for model in catalog.json()] == ['second', 'test']


def test_apply_rejects_unowned_secret_references():
    app = create_app('internal-secret', Provider())
    response = send(app, '/internal/v1/provider/apply', config(api_key_ref='INTERNAL_API_KEY'))
    assert response.status_code == 422
    assert 'invalid_api_key_ref' in response.text


def test_apply_rejects_egress_and_ollama_capabilities(monkeypatch):
    monkeypatch.setenv('UAI_EGRESS_ALLOW', 'allowed.example:443')
    app = create_app('internal-secret', Provider(),
                     egress=EgressPolicy.from_env())
    denied = send(app, '/internal/v1/provider/apply', config())
    assert denied.status_code == 422
    assert 'egress_denied' in denied.text

    monkeypatch.setenv('UAI_EGRESS_ALLOW', 'provider:80')
    app = create_app('internal-secret', Provider(), egress=EgressPolicy.from_env())
    unsupported = send(app, '/internal/v1/provider/apply', config(
        provider='ollama', api_key_ref='',
        models=[{'id': 'test', 'capabilities': ['tool_calling'], 'context_window': None}],
    ))
    assert unsupported.status_code == 422
    assert 'capability_not_supported' in unsupported.text


def test_registry_snapshot_keeps_in_flight_provider():
    config_one = ProviderConfig.model_validate(config())
    active_one = make_active(config_one, None)
    registry = ProviderRegistry(active_one)
    snapshot = registry.snapshot()
    config_two = ProviderConfig.model_validate(config(revision=2, max_output_tokens=512))
    active_two = make_active(config_two, None)
    assert registry.replace(active_two) is active_two
    assert registry.snapshot() is active_two
    assert snapshot is active_one
    assert snapshot.definitions['test'].max_output_tokens == 256


def test_discovery_lists_openai_and_ollama_models(monkeypatch):
    monkeypatch.setenv('MODEL_API_KEY', 'provider-secret')
    seen = []

    def handler(request):
        seen.append(str(request.url))
        assert request.headers['authorization'] == 'Bearer provider-secret'
        return httpx.Response(200, json={'data': [
            {'id': 'model-b'}, {'id': 'model-a'}, {'id': 'model-b'}, {'bad': True},
        ]})

    app = create_app('internal-secret', Provider(),
                     discovery_transport=httpx.MockTransport(handler))
    response = send(app, '/internal/v1/provider/models', {
        'provider': 'openai-compatible',
        'base_url': 'http://provider/v1',
        'api_key_ref': 'MODEL_API_KEY',
    })
    assert response.status_code == 200
    assert response.json() == {'models': ['model-a', 'model-b']}
    assert seen == ['http://provider/v1/models']


def test_discovery_prefers_inline_api_key():
    seen = []

    def handler(request):
        seen.append(request.headers.get('authorization'))
        return httpx.Response(200, json={'data': []})

    config = ProviderDiscoveryConfig(provider='openai-compatible', base_url='http://provider/v1',
                                     api_key='sk-inline', api_key_ref='MODEL_API_KEY')
    assert asyncio.run(discover_models(config, None, transport=httpx.MockTransport(handler))) == []
    assert seen == ['Bearer sk-inline']


def test_discovery_rejects_inline_api_key_and_ref_together():
    app = create_app('internal-secret', Provider())
    response = send(app, '/internal/v1/provider/models', {
        'provider': 'openai-compatible',
        'base_url': 'http://provider/v1',
        'api_key': 'sk-inline',
        'api_key_ref': 'MODEL_API_KEY',
    })
    assert response.status_code == 422
    assert 'invalid_configuration' in response.text


def test_discovery_lists_ollama_tags_and_hides_failures(monkeypatch):
    monkeypatch.setenv('OLLAMA_BASE_URL', 'http://ollama:11434')

    def handler(request):
        assert str(request.url) == 'http://ollama:11434/api/tags'
        return httpx.Response(200, json={'models': [
            {'name': 'llama3.2:3b'}, {'model': 'qwen2.5:7b'},
        ]})

    app = create_app('internal-secret', Provider(),
                     discovery_transport=httpx.MockTransport(handler))
    response = send(app, '/internal/v1/provider/models', {
        'provider': 'ollama',
        'base_url': 'http://ollama:11434',
        'api_key_ref': '',
    })
    assert response.status_code == 200
    assert response.json() == {'models': ['llama3.2:3b', 'qwen2.5:7b']}


def test_validation_does_not_swap_models(monkeypatch):
    monkeypatch.setenv('MODEL_API_KEY', 'provider-secret')
    app = create_app('internal-secret', Provider())
    response = send(app, '/internal/v1/provider/validate', config(
        api_key_ref='MODEL_API_KEY',
        models=[{'id': 'other', 'capabilities': [], 'context_window': None}],
    ))
    assert response.status_code == 200
    assert response.json() == {'api_key_configured': True}
    catalog = send(app, '/internal/v1/models')
    assert [model['id'] for model in catalog.json()] == ['test']


def test_duplicate_and_invalid_models_are_rejected():
    app = create_app('internal-secret', Provider())
    duplicate = config(models=[
        {'id': 'test', 'capabilities': [], 'context_window': None},
        {'id': 'test', 'capabilities': [], 'context_window': None},
    ])
    assert send(app, '/internal/v1/provider/apply', duplicate).status_code == 422
    bad = config(models=[{'id': ' bad', 'capabilities': [], 'context_window': None}])
    assert send(app, '/internal/v1/provider/apply', bad).status_code == 422


def test_synthetic_initial_state_is_safe():
    app = create_app('internal-secret', Provider())
    state = send(app, '/internal/v1/provider/state')
    assert state.status_code == 200
    payload = state.json()
    assert payload['revision'] == 0
    assert payload['api_key_configured'] is False
    assert 'provider-secret' not in state.text

def test_discovery_rejects_oversized_provider_response():
    def handler(request):
        return httpx.Response(200, content=b'x' * (512 * 1024 + 1))

    app = create_app('internal-secret', Provider(),
                     discovery_transport=httpx.MockTransport(handler))
    response = send(app, '/internal/v1/provider/models', {
        'provider': 'openai-compatible',
        'base_url': 'http://provider/v1',
        'api_key_ref': '',
    })
    assert response.status_code == 422
    assert 'provider_models_too_large' in response.text
