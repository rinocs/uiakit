"""Runtime retriever factory: configured embedding + Qdrant + optional reranker."""
import os

from uai_core.retrieval import ContextAssembler, Retriever
from uai_runtime.providers import embedding_provider_from_env

from .qdrant_store import QdrantVectorStore


def retriever_from_env(*, reranker=None) -> Retriever:
    embedding = embedding_provider_from_env()
    vector_store = QdrantVectorStore(os.environ.get('QDRANT_URL', 'http://qdrant:6333'),
                                     embedding.model.dimension)
    return Retriever(
        embedding, vector_store, reranker=reranker,
        search_limit=int(os.environ.get('RETRIEVAL_SEARCH_LIMIT', '20')),
        context=ContextAssembler(max_chars=int(os.environ.get('RETRIEVAL_CONTEXT_CHARS', '8000')),
                                 max_chunks=int(os.environ.get('RETRIEVAL_CONTEXT_CHUNKS', '10'))),
    )


__all__ = ['retriever_from_env']
