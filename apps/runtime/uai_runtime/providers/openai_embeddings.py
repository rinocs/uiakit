"""OpenAI-compatible embeddings; also serves LiteLLM through the same boundary."""
import httpx

from uai_core.embeddings import EmbeddingError, EmbeddingModel, validate_texts, validate_vectors

from .embedding_http import post_embedding_json


class OpenAIEmbeddingProvider:
    def __init__(self, base_url: str, api_key: str, model: EmbeddingModel, *,
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 30,
                 max_retries: int = 1):
        url = httpx.URL(base_url)
        if url.scheme not in ('http', 'https') or not url.host or url.userinfo:
            raise ValueError('invalid_embedding_base_url')
        self.model = model
        self._base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._transport = transport
        self._timeout = timeout
        self._max_retries = max_retries

    async def embed(self, texts) -> list[list[float]]:
        clean = validate_texts(self.model, texts)
        headers = {'Authorization': f'Bearer {self._api_key}'} if self._api_key else {}
        data = await post_embedding_json(
            f'{self._base_url}/embeddings',
            {'model': self.model.id, 'input': list(clean)},
            headers, transport=self._transport, timeout=self._timeout,
            max_retries=self._max_retries)
        entries = data.get('data')
        if not isinstance(entries, list) or len(entries) != len(clean):
            raise EmbeddingError('invalid_embedding_response')
        vectors = [None] * len(clean)
        for entry in entries:
            if not isinstance(entry, dict):
                raise EmbeddingError('invalid_embedding_response')
            index = entry.get('index')
            if type(index) is not int or not 0 <= index < len(clean) or vectors[index] is not None:
                raise EmbeddingError('invalid_embedding_response')
            vectors[index] = entry.get('embedding')
        return validate_vectors(self.model, vectors, len(clean))


__all__ = ['OpenAIEmbeddingProvider']
