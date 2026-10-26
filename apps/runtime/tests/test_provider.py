import asyncio

import httpx

from uai_core.models import Message, ModelInput
from uai_runtime.provider import OpenAIProvider


BODY = (
    b'data: {"choices":[{"delta":{"content":"ok"}}]}\n\n'
    b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
    b'data: [DONE]\n\n'
)


def collect(provider, seen):
    async def handler(request):
        seen['authorization'] = request.headers.get('authorization')
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=BODY)

    async def run():
        request = ModelInput(model='test', system_prompt='Helpful',
                             messages=(Message(role='user', content='Hi'),))
        return [chunk async for chunk in OpenAIProvider(
            'http://provider/v1', provider, transport=httpx.MockTransport(handler)
        ).stream(request)]

    return asyncio.run(run())


def test_stream_omits_authorization_without_api_key():
    seen = {}
    chunks = collect('', seen)
    assert seen['authorization'] is None
    assert ''.join(chunk.text for chunk in chunks) == 'ok'


def test_stream_sends_authorization_when_configured():
    seen = {}
    collect('secret', seen)
    assert seen['authorization'] == 'Bearer secret'


def test_stream_accumulates_tool_call_deltas():
    body = (
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1",'
        b'"function":{"name":"test.count","arguments":"{\\"text\\":"}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        b'"function":{"arguments":"\\"abc\\"}"}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        b'data: [DONE]\n\n'
    )

    async def handler(request):
        assert b'"tools"' not in request.content  # no tools requested in this test
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=body)

    async def run():
        request = ModelInput(model='test', system_prompt='Helpful',
                             messages=(Message(role='user', content='Hi'),))
        return [chunk async for chunk in OpenAIProvider(
            'http://provider/v1', '', transport=httpx.MockTransport(handler)).stream(request)]

    chunks = asyncio.run(run())
    calls = [delta for chunk in chunks for delta in chunk.tool_calls]
    assert [call.id for call in calls if call.id] == ['call-1']
    assert ''.join(call.arguments for call in calls) == '{"text":"abc"}'


def test_stream_requests_json_schema_when_structured_output_is_set():
    seen = {}

    async def handler(request):
        seen['body'] = request.content
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, content=BODY)

    async def run():
        request = ModelInput(model='test', system_prompt='Helpful',
                             messages=(Message(role='user', content='Hi'),),
                             structured_output={'type': 'object',
                                                'properties': {'answer': {'type': 'string'}}})
        return [chunk async for chunk in OpenAIProvider(
            'http://provider/v1', '', transport=httpx.MockTransport(handler)).stream(request)]

    asyncio.run(run())
    assert b'"response_format"' in seen['body']
    assert b'"json_schema"' in seen['body']
