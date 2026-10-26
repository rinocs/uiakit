import asyncio
import json
import os

import httpx
import pytest

from uai_core.embeddings import EmbeddingError, EmbeddingModel, EmbeddingUnavailable
from uai_core.models import Message, ModelInput
from uai_core.providers import ProviderError
from uai_runtime.providers import (OllamaEmbeddingProvider, OllamaProvider, OpenAIEmbeddingProvider,
                                   embedding_provider_from_env)


def model(provider='ollama', dimension=2, version='v1', batch_size=2):
    return EmbeddingModel(id='embed', provider=provider, dimension=dimension,
                          version=version, batch_size=batch_size)


def run(coro):
    return asyncio.run(coro)


def test_model_identity_and_index_version():
    a = model()
    assert a.index_version == model().index_version
    assert a.index_version != model(dimension=3).index_version
    assert a.index_version != model(version='v2').index_version
    assert a.index_version != model(provider='openai-compatible').index_version
    for bad in (dict(dimension=0), dict(batch_size=0), dict(provider='other'), dict(id='')):
        with pytest.raises(ValueError):
            EmbeddingModel(**{**dict(id='e', provider='ollama', dimension=2, version='v'), **bad})


def test_ollama_embeddings_batch_and_no_auth_header():
    seen = {}

    async def handler(request):
        seen['path'] = request.url.path
        seen['auth'] = request.headers.get('authorization')
        seen['body'] = json.loads(request.content)
        return httpx.Response(200, json={'embeddings': [[0.1, 0.2], [0.3, 0.4]]})

    provider = OllamaEmbeddingProvider('http://ollama:11434', model(), transport=httpx.MockTransport(handler))
    vectors = run(provider.embed(['a', 'b']))
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert seen == {'path': '/api/embed', 'auth': None,
                    'body': {'model': 'embed', 'input': ['a', 'b']}}


def test_openai_embeddings_orders_by_index_and_sends_bearer():
    seen = {}

    async def handler(request):
        seen['path'] = request.url.path
        seen['auth'] = request.headers.get('authorization')
        return httpx.Response(200, json={'data': [
            {'index': 1, 'embedding': [0.3, 0.4]},
            {'index': 0, 'embedding': [0.1, 0.2]},
        ]})

    provider = OpenAIEmbeddingProvider('http://provider/v1', 'secret', model('openai-compatible'),
                                       transport=httpx.MockTransport(handler))
    assert run(provider.embed(['a', 'b'])) == [[0.1, 0.2], [0.3, 0.4]]
    assert seen == {'path': '/v1/embeddings', 'auth': 'Bearer secret'}


def test_embedding_limits_dimensions_and_invalid_responses():
    calls = []

    async def handler(request):
        calls.append(1)
        return httpx.Response(200, request=request, content=b'{"embeddings": [[0.1]]}')

    provider = OllamaEmbeddingProvider('http://ollama:11434', model(), transport=httpx.MockTransport(handler))
    with pytest.raises(EmbeddingError, match='invalid_embedding_batch'):
        run(provider.embed(['a', 'b', 'c']))
    with pytest.raises(EmbeddingError, match='embedding_dimension_mismatch'):
        run(provider.embed(['a']))
    assert calls == [1]
    with pytest.raises(EmbeddingError, match='invalid_embedding_text'):
        run(provider.embed(['']))
    with pytest.raises(EmbeddingError, match='invalid_embedding_response'):
        run(provider.embed(['a', 'b']))


def test_retry_only_transient_status_and_timeout():
    calls = []

    async def flaky(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, request=request, json={'embeddings': [[0.1, 0.2]]})

    provider = OllamaEmbeddingProvider('http://ollama:11434', model(dimension=2, batch_size=1),
                                       transport=httpx.MockTransport(flaky), max_retries=1)
    assert run(provider.embed(['a'])) == [[0.1, 0.2]]
    assert len(calls) == 2

    calls.clear()

    async def bad_request(request):
        calls.append(1)
        return httpx.Response(400, request=request)

    provider = OllamaEmbeddingProvider('http://ollama:11434', model(dimension=2, batch_size=1),
                                       transport=httpx.MockTransport(bad_request), max_retries=3)
    with pytest.raises(EmbeddingError, match='embedding_rejected'):
        run(provider.embed(['a']))
    assert len(calls) == 1

    calls.clear()

    async def timeout(request):
        calls.append(1)
        raise httpx.ReadTimeout('timeout', request=request)

    provider = OllamaEmbeddingProvider('http://ollama:11434', model(dimension=2, batch_size=1),
                                       transport=httpx.MockTransport(timeout), max_retries=1)
    with pytest.raises(EmbeddingUnavailable, match='embedding_unavailable'):
        run(provider.embed(['a']))
    assert len(calls) == 2


def test_embedding_factory_requires_base_for_openai(monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'ollama')
    monkeypatch.setenv('EMBEDDING_MODEL', 'embed')
    monkeypatch.setenv('EMBEDDING_DIMENSION', '2')
    monkeypatch.delenv('EMBEDDING_BASE_URL', raising=False)
    provider = embedding_provider_from_env()
    assert isinstance(provider, OllamaEmbeddingProvider) and provider.model.dimension == 2
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'openai-compatible')
    with pytest.raises(ValueError, match='embedding_base_url_required'):
        embedding_provider_from_env()


def test_ollama_chat_stream_maps_text_and_usage():
    lines = [
        {'message': {'role': 'assistant', 'content': 'Hel'}},
        {'message': {'content': 'lo'}, 'done': False},
        {'message': {'content': ''}, 'done': True, 'prompt_eval_count': 3, 'eval_count': 2},
    ]
    body = ''.join(json.dumps(line) + '\n' for line in lines)

    async def handler(request):
        assert request.url.path == '/api/chat'
        return httpx.Response(200, content=body.encode())

    provider = OllamaProvider('http://ollama:11434', transport=httpx.MockTransport(handler))
    request = ModelInput(model='llama', system_prompt='s',
                         messages=(Message(role='user', content='Hi'),))
    async def collect():
        return [chunk async for chunk in provider.stream(request)]
    chunks = run(collect())
    assert ''.join(chunk.text for chunk in chunks) == 'Hello'
    assert chunks[-1].usage == {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}


def test_ollama_chat_fails_closed_without_done_or_with_error():
    async def no_done(request):
        return httpx.Response(200, content=b'{"message":{"content":"x"}}\n')

    provider = OllamaProvider('http://ollama:11434', transport=httpx.MockTransport(no_done))
    request = ModelInput(model='llama', system_prompt='s',
                         messages=(Message(role='user', content='Hi'),))
    with pytest.raises(ProviderError, match='incomplete_provider_stream'):
        async def consume():
            return [chunk async for chunk in provider.stream(request)]
        run(consume())

    async def error(request):
        return httpx.Response(200, content=b'{"error":"bad"}\n')

    provider = OllamaProvider('http://ollama:11434', transport=httpx.MockTransport(error))
    with pytest.raises(ProviderError, match='provider_error'):
        run(consume())


@pytest.mark.skipif(not (os.environ.get('UAI_OLLAMA_TEST_URL') and os.environ.get('UAI_EMBEDDING_TEST_MODEL')),
                    reason='real Ollama endpoint/model not configured')
def test_ollama_embeddings_real_backend():
    dimension = int(os.environ.get('UAI_EMBEDDING_TEST_DIMENSION', '768'))
    model = EmbeddingModel(id=os.environ['UAI_EMBEDDING_TEST_MODEL'], provider='ollama',
                           dimension=dimension, version='integration', batch_size=4)
    provider = OllamaEmbeddingProvider(os.environ['UAI_OLLAMA_TEST_URL'], model)
    vectors = run(provider.embed(['hello world']))
    assert len(vectors) == 1 and len(vectors[0]) == dimension
