"""OpenAI-compatible chat streaming adapter. No retries once generation begins."""
import json
from collections.abc import AsyncIterator
import httpx

from uai_core.models import ModelInput
from uai_core.providers import ModelChunk, ModelProvider, ProviderError, ToolCallDelta


async def _bounded_lines(response: httpx.Response) -> AsyncIterator[str]:
    # Bound memory before HTTPX's line assembler could accumulate an unbounded line.
    buffer = bytearray()
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > 4 * 1024 * 1024:
            raise ProviderError('provider_response_limit')
        buffer.extend(chunk)
        while (end := buffer.find(b'\n')) >= 0:
            if end > 262144:
                raise ProviderError('oversized_provider_event')
            line = bytes(buffer[:end]).decode('utf-8').rstrip('\r')
            del buffer[:end + 1]
            yield line
        if len(buffer) > 262144:
            raise ProviderError('oversized_provider_event')
    if buffer:
        yield bytes(buffer).decode('utf-8').rstrip('\r')


class OpenAIProvider:
    def __init__(self, base_url: str, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 max_tokens: int = 1024):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.transport = transport
        if not 1 <= max_tokens <= 8192:
            raise ValueError("MODEL_MAX_TOKENS must be between 1 and 8192")
        url = httpx.URL(self.base_url)
        if url.scheme not in ("http", "https") or not url.host or url.userinfo:
            raise ValueError("Invalid model base URL")
        self.max_tokens = max_tokens

    async def stream(self, request: ModelInput) -> AsyncIterator[ModelChunk]:
        provider_messages = getattr(request, 'provider_messages', ())
        messages = (list(provider_messages) if provider_messages else
                    [{'role': 'system', 'content': request.system_prompt}]
                    + [m.model_dump() for m in request.messages])
        payload = {'model': request.model, 'messages': messages, 'stream': True,
                   'max_tokens': self.max_tokens, 'stream_options': {'include_usage': True}}
        tools = getattr(request, 'tools', ())
        if tools:
            payload['tools'] = list(tools)
            payload['tool_choice'] = 'auto'
        structured_output = getattr(request, 'structured_output', None)
        if structured_output:
            payload['response_format'] = {
                'type': 'json_schema',
                'json_schema': {'name': 'response', 'strict': False, 'schema': structured_output},
            }
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=30, trust_env=False,
                                        follow_redirects=False) as client:
                async with client.stream('POST', f'{self.base_url}/chat/completions',
                        headers=headers,
                        json=payload) as response:
                    response.raise_for_status()
                    finished = False
                    async for line in _bounded_lines(response):
                        if len(line) > 262144:
                            raise ProviderError('oversized_provider_event')
                        if not line.startswith('data:'):
                            continue
                        raw = line[5:].strip()
                        if raw == '[DONE]':
                            if not finished:
                                raise ProviderError('incomplete_provider_stream')
                            return
                        data = json.loads(raw)
                        if data.get('error'):
                            raise ProviderError('provider_error')
                        usage = data.get('usage')
                        if usage:
                            if not isinstance(usage, dict):
                                raise ProviderError('invalid_usage')
                            clean = {k: v for k, v in usage.items()
                                     if k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                                     and type(v) is int and v >= 0}
                            yield ModelChunk(usage=clean)
                        choices = data['choices']
                        if not isinstance(choices, list):
                            raise ProviderError('invalid_choices')
                        if not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get('delta', {})
                        if delta.get('function_call'):
                            raise ProviderError('unsupported_tool_call')
                        raw_calls = delta.get('tool_calls')
                        if raw_calls is not None:
                            if not isinstance(raw_calls, list) or len(raw_calls) > 8:
                                raise ProviderError('invalid_tool_call')
                            calls = []
                            for item in raw_calls:
                                if not isinstance(item, dict) or type(item.get('index')) is not int:
                                    raise ProviderError('invalid_tool_call')
                                function = item.get('function') or {}
                                if not isinstance(function, dict):
                                    raise ProviderError('invalid_tool_call')
                                index = item['index']
                                call_id = item.get('id') or ''
                                name = function.get('name') or ''
                                arguments = function.get('arguments') or ''
                                if (not 0 <= index <= 7 or not all(isinstance(value, str) for value in
                                        (call_id, name, arguments)) or len(call_id) > 200
                                        or len(name) > 200 or len(arguments) > 131072):
                                    raise ProviderError('invalid_tool_call')
                                calls.append(ToolCallDelta(index=index, id=call_id, name=name,
                                                           arguments=arguments))
                            if calls:
                                yield ModelChunk(tool_calls=tuple(calls))
                        text = delta.get('content')
                        if text is not None:
                            if not isinstance(text, str) or finished:
                                raise ProviderError('invalid_delta')
                            if text:
                                yield ModelChunk(text=text)
                        reason = choice.get('finish_reason')
                        if reason:
                            if reason not in ('stop', 'tool_calls'):
                                raise ProviderError('generation_not_completed')
                            finished = True
                    # EOF without DONE may mean transport truncation; never report success.
                    raise ProviderError('incomplete_provider_stream')
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            raise ProviderError('provider_error') from exc

# Compatibility aliases for users of the initial runtime module.
__all__ = ['OpenAIProvider', 'ModelChunk', 'ModelProvider', 'ProviderError']
