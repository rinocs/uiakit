"""Small bounded JSON POST helper shared by embedding adapters."""
import asyncio
import httpx

from uai_core.embeddings import EmbeddingError, EmbeddingUnavailable

_MAX_RESPONSE = 16 * 1024 * 1024


async def post_embedding_json(url: str, payload: dict, headers: dict, *,
                              transport=None, timeout: float = 30,
                              max_retries: int = 1) -> dict:
    if max_retries < 0 or max_retries > 3:
        raise ValueError('invalid_embedding_retries')
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            async with httpx.AsyncClient(transport=transport, timeout=timeout,
                                         trust_env=False, follow_redirects=False) as client:
                response = await client.post(url, headers=headers, json=payload)
            if 200 <= response.status_code < 300:
                if len(response.content) > _MAX_RESPONSE:
                    raise EmbeddingError('embedding_response_too_large')
                try:
                    data = response.json()
                except ValueError:
                    raise EmbeddingError('invalid_embedding_response') from None
                if not isinstance(data, dict):
                    raise EmbeddingError('invalid_embedding_response')
                return data
            if response.status_code in (429, 500, 502, 503, 504) and attempt < attempts - 1:
                await asyncio.sleep(0.1 * (2 ** attempt))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                raise EmbeddingUnavailable('embedding_unavailable')
            raise EmbeddingError('embedding_rejected')
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt < attempts - 1:
                await asyncio.sleep(0.1 * (2 ** attempt))
                continue
            raise EmbeddingUnavailable('embedding_unavailable') from None
    raise EmbeddingUnavailable('embedding_unavailable')


__all__ = ['post_embedding_json']
