"""Native Ollama chat streaming and batch embeddings. No cloud key required."""
import json

import httpx

from uai_core.embeddings import EmbeddingError, EmbeddingModel, validate_texts, validate_vectors
from uai_core.models import ModelInput
from uai_core.providers import ModelChunk, ProviderError

from ..provider import _bounded_lines
from .embedding_http import post_embedding_json


class OllamaEmbeddingProvider:
    def __init__(self, base_url: str, model: EmbeddingModel, *,
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 30,
                 max_retries: int = 1):
        url = httpx.URL(base_url)
        if url.scheme not in ('http', 'https') or not url.host or url.userinfo:
            raise ValueError('invalid_embedding_base_url')
        self.model = model
        self._base_url = base_url.rstrip('/')
        self._transport = transport
        self._timeout = timeout
        self._max_retries = max_retries

    async def embed(self, texts) -> list[list[float]]:
        clean = validate_texts(self.model, texts)
        data = await post_embedding_json(
            f'{self._base_url}/api/embed',
            {'model': self.model.id, 'input': list(clean)}, {},
            transport=self._transport, timeout=self._timeout, max_retries=self._max_retries)
        vectors = data.get('embeddings')
        if not isinstance(vectors, list):
            raise EmbeddingError('invalid_embedding_response')
        return validate_vectors(self.model, vectors, len(clean))


class OllamaProvider:
    def __init__(self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None,
                 max_tokens: int = 1024):
        if not 1 <= max_tokens <= 8192:
            raise ValueError('MODEL_MAX_TOKENS must be between 1 and 8192')
        url = httpx.URL(base_url)
        if url.scheme not in ('http', 'https') or not url.host or url.userinfo:
            raise ValueError('invalid_ollama_base_url')
        self._base_url = base_url.rstrip('/')
        self._transport = transport
        self.max_tokens = max_tokens

    async def stream(self, request: ModelInput):
        messages = [{'role': 'system', 'content': request.system_prompt}]
        messages += [m.model_dump() for m in request.messages]
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30, trust_env=False,
                                         follow_redirects=False) as client:
                async with client.stream('POST', f'{self._base_url}/api/chat', json={
                        'model': request.model, 'messages': messages, 'stream': True,
                        'options': {'num_predict': self.max_tokens}}) as response:
                    response.raise_for_status()
                    finished = False
                    async for line in _bounded_lines(response):
                        if not line.strip():
                            continue
                        if len(line) > 262144:
                            raise ProviderError('oversized_provider_event')
                        data = json.loads(line)
                        if data.get('error'):
                            raise ProviderError('provider_error')
                        message = data.get('message') or {}
                        text = message.get('content')
                        if text is not None:
                            if not isinstance(text, str) or finished:
                                raise ProviderError('invalid_delta')
                            if text:
                                yield ModelChunk(text=text)
                        if data.get('done'):
                            prompt = data.get('prompt_eval_count')
                            completion = data.get('eval_count')
                            usage = {}
                            if type(prompt) is int and prompt >= 0:
                                usage['prompt_tokens'] = prompt
                            if type(completion) is int and completion >= 0:
                                usage['completion_tokens'] = completion
                            if usage:
                                usage['total_tokens'] = usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)
                                yield ModelChunk(usage=usage)
                            finished = True
                    if not finished:
                        raise ProviderError('incomplete_provider_stream')
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
            raise ProviderError('provider_error') from exc


__all__ = ['OllamaEmbeddingProvider', 'OllamaProvider']
