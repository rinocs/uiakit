import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from contextlib import contextmanager

from uai_runtime.app import create_app
from uai_runtime.provider import OpenAIProvider


def test_provider_rejects_tool_calls_after_finish():
    from uai_core.providers import ProviderError
    from uai_runtime.models import RunRequest

    body = (
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"late",'
        '"function":{"name":"unexpected","arguments":"{}"}}]}}]}\n\n'
        'data: [DONE]\n\n'
    )

    async def consume():
        provider = OpenAIProvider('http://provider/v1', '', transport=httpx.MockTransport(
            lambda r: httpx.Response(200, text=body)))
        return [chunk async for chunk in provider.stream(RunRequest(**request_body()))]

    with pytest.raises(ProviderError):
        asyncio.run(consume())


def request_body():
    return dict(run_id=str(uuid4()), correlation_id=str(uuid4()), model='test',
                system_prompt='Helpful', messages=[dict(role='user', content='Ciao')])


def mock_provider(request):
    data = json.loads(request.content)
    assert data['messages'][0] == {'role': 'system', 'content': 'Helpful'}
    assert data['stream'] is True
    return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Ciao"}}]}\n\n'
                          'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                          'data: [DONE]\n\n')


@contextmanager
def client(handler=mock_provider, **kwargs):
    provider = OpenAIProvider('http://provider/v1', 'private',
                              transport=httpx.MockTransport(handler))
    app = create_app('internal-secret', provider, **kwargs)
    class Client:
        def post(self, path, **kw):
            async def send():
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as c:
                    return await c.post(path, **kw)
            return asyncio.run(send())
    yield Client()


def events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]


def test_auth_and_validation():
    with client() as c:
        assert c.post('/internal/v1/runs', json=request_body()).status_code == 401
        assert c.post('/internal/v1/runs', json={}, headers={'Authorization': 'Bearer internal-secret'}).status_code == 422
        body = request_body()
        body['messages'][0]['role'] = 'system'
        assert c.post('/internal/v1/runs', json=body, headers={'Authorization': 'Bearer internal-secret'}).status_code == 422


def test_stream_envelope_and_completion():
    body = request_body()
    with client() as c:
        r = c.post('/internal/v1/runs', json=body, headers={'Authorization': 'Bearer internal-secret'})
    assert r.status_code == 200
    assert r.headers['content-type'].startswith('text/event-stream')
    result = events(r)
    assert [e['event_type'] for e in result] == ['agent.started', 'response.delta', 'response.completed']
    assert result[-1]['payload']['text'] == 'Ciao'
    assert all(e['run_id'] == body['run_id'] and e['event_version'] == 1 for e in result)
    assert len({e['event_id'] for e in result}) == len(result)


@pytest.mark.parametrize('handler', [
    lambda r: httpx.Response(401, text='secret-provider-detail'),
    lambda r: httpx.Response(200, text='data: invalid\n\n'),
    lambda r: httpx.Response(200, text='data: {"choices":[]}\n\n'),
])
def test_provider_errors_are_normalized(handler):
    with client(handler) as c:
        r = c.post('/internal/v1/runs', json=request_body(), headers={'Authorization': 'Bearer internal-secret'})
    result = events(r)
    assert result[-1]['event_type'] == 'agent.failed'
    assert 'secret-provider-detail' not in r.text
    assert not any(e['event_type'] == 'response.completed' for e in result)


def test_output_limit():
    with client(max_output_chars=2) as c:
        r = c.post('/internal/v1/runs', json=request_body(), headers={'Authorization': 'Bearer internal-secret'})
    assert events(r)[-1]['payload']['code'] == 'output_limit'


@pytest.mark.parametrize('trailing_content', ['', 'unexpected'])
def test_openrouter_usage_event_after_stop(trailing_content):
    usage_event = json.dumps({
        'choices': [{'delta': {'content': trailing_content, 'role': 'assistant'},
                     'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 4, 'completion_tokens': 2, 'total_tokens': 6},
    })
    text = (
        'data: {"choices":[{"delta":{"content":"Ciao"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}\n\n'
        f'data: {usage_event}\n\n'
        'data: [DONE]\n\n'
    )
    with client(lambda r: httpx.Response(200, text=text)) as c:
        response = c.post('/internal/v1/runs', json=request_body(),
                          headers={'Authorization': 'Bearer internal-secret'})
    result = events(response)
    if trailing_content:
        assert result[-1]['event_type'] == 'agent.failed'
        assert not any(e['event_type'] == 'response.completed' for e in result)
    else:
        assert result[-1]['event_type'] == 'response.completed'
        assert result[-1]['payload']['text'] == 'Ciao'
        assert result[-1]['payload']['usage']['total_tokens'] == 6


def test_timeout_is_terminal_failure():
    class SlowProvider:
        async def stream(self, request):
            await asyncio.sleep(0.03)
            yield None
    app = create_app('internal-secret', SlowProvider(), duration_seconds=0.001)
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as c:
            return await c.post('/internal/v1/runs', json=request_body(), headers={'Authorization': 'Bearer internal-secret'})
    result = events(asyncio.run(send()))
    assert result[-1]['event_type'] == 'agent.failed'
    assert result[-1]['payload']['code'] == 'execution_timeout'


def test_model_and_context_limits():
    with client(max_input_chars=4) as c:
        r = c.post('/internal/v1/runs', json=request_body(), headers={'Authorization': 'Bearer internal-secret'})
        assert r.status_code == 422
    body = request_body()
    body['model'] = 'not-configured'
    with client() as c:
        r = c.post('/internal/v1/runs', json=body, headers={'Authorization': 'Bearer internal-secret'})
        assert r.status_code == 422


@pytest.mark.parametrize('text', [
    'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
    'data: {"choices":[{"delta":{"tool_calls":[{}]}}]}\n\n',
    'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n',
    'data: [DONE]\n\n',
])
def test_truncation_and_unsupported_capabilities_fail(text):
    with client(lambda r: httpx.Response(200, text=text)) as c:
        r = c.post('/internal/v1/runs', json=request_body(), headers={'Authorization': 'Bearer internal-secret'})
    assert events(r)[-1]['event_type'] == 'agent.failed'


def test_event_rejects_payload_for_wrong_lifecycle_phase():
    from pydantic import ValidationError
    from uai_runtime.models import RuntimeEvent
    with pytest.raises(ValidationError):
        RuntimeEvent(event_type='response.delta', run_id=uuid4(), correlation_id=uuid4(),
                     payload={'code': 'provider_error'})


def test_provider_line_limit_stops_reading_before_buffering_entire_response():
    class LongLine(httpx.AsyncByteStream):
        read_chunks = 0
        async def __aiter__(self):
            for _ in range(100):
                self.read_chunks += 1
                yield b'x' * 16384
    stream = LongLine()
    with client(lambda r: httpx.Response(200, stream=stream)) as c:
        r = c.post('/internal/v1/runs', json=request_body(), headers={'Authorization': 'Bearer internal-secret'})
    assert events(r)[-1]['event_type'] == 'agent.failed'
    assert stream.read_chunks <= 20


def test_provider_yields_first_delta_without_waiting_for_next_packet():
    from uai_runtime.models import RunRequest
    class LiveStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            await asyncio.sleep(1)
            yield b'data: [DONE]\n\n'
    async def first_delta():
        provider = OpenAIProvider('http://provider/v1', '',
                                  transport=httpx.MockTransport(lambda r: httpx.Response(200, stream=LiveStream())))
        stream = provider.stream(RunRequest(**request_body()))
        try:
            return await asyncio.wait_for(anext(stream), timeout=0.1)
        finally:
            await stream.aclose()
    assert asyncio.run(first_delta()).text == 'first'


def test_authority_claim_requires_authenticated_internal_gateway():
    body = request_body()
    body['authority'] = {'principal_id': 'admin', 'scopes': ['tools:execute']}
    with client() as c:
        r = c.post('/internal/v1/runs', json=body)
    assert r.status_code == 401


def test_model_provider_receives_only_immutable_model_input():
    from uai_core.models import ModelInput
    from uai_core.providers import ModelChunk
    seen = []
    class RecordingProvider:
        async def stream(self, request):
            assert isinstance(request, ModelInput)
            assert not hasattr(request, 'authority')
            assert not hasattr(request, 'working_memory')
            assert not hasattr(request, 'run_id')
            seen.append(request)
            yield ModelChunk(text='safe')
    async def send():
        app = create_app('internal-secret', RecordingProvider())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as c:
            return await c.post('/internal/v1/runs', json=request_body(), headers={'Authorization': 'Bearer internal-secret'})
    response = asyncio.run(send())
    assert events(response)[-1]['payload']['text'] == 'safe'
    assert len(seen) == 1


def test_history_accepts_long_assistant_output_but_limits_user_messages():
    body = request_body()
    body['messages'].insert(0, {'role': 'assistant', 'content': 'a' * 40000})
    with client() as c:
        r = c.post('/internal/v1/runs', json=body, headers={'Authorization': 'Bearer internal-secret'})
        assert r.status_code == 200
        assert events(r)[-1]['event_type'] == 'response.completed'
    body['messages'] = [{'role': 'user', 'content': 'a' * 32001}]
    with client() as c:
        assert c.post('/internal/v1/runs', json=body, headers={'Authorization': 'Bearer internal-secret'}).status_code == 422
