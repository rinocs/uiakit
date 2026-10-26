"""Provider adapters and host-configured factories."""
import os

from uai_core.embeddings import EmbeddingModel

from ..egress import EgressError, EgressPolicy
from ..secrets import secret_from_env
from .ollama import OllamaEmbeddingProvider, OllamaProvider
from .openai_embeddings import OpenAIEmbeddingProvider


def embedding_provider_from_env(egress: EgressPolicy | None = None):
    provider = os.environ.get('EMBEDDING_PROVIDER', 'ollama')
    model_id = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')
    model = EmbeddingModel(
        id=model_id,
        provider=provider,
        dimension=int(os.environ.get('EMBEDDING_DIMENSION', '768')),
        version=os.environ.get('EMBEDDING_VERSION', model_id),
        batch_size=int(os.environ.get('EMBEDDING_BATCH_SIZE', '32')),
    )
    base_url = os.environ.get('EMBEDDING_BASE_URL') or (
        'http://ollama:11434' if provider == 'ollama' else '')
    if not base_url:
        raise ValueError('embedding_base_url_required')
    if egress is not None:
        try:
            egress.require(base_url)
        except EgressError:
            raise ValueError('egress_denied') from None
    if provider == 'ollama':
        return OllamaEmbeddingProvider(base_url, model)
    return OpenAIEmbeddingProvider(base_url, secret_from_env('EMBEDDING_API_KEY') or '', model)


__all__ = ['OllamaEmbeddingProvider', 'OllamaProvider', 'OpenAIEmbeddingProvider',
           'embedding_provider_from_env']
