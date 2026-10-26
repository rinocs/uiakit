"""Optional Haystack-like retriever adapter. The core never imports Haystack."""
import asyncio

from uai_core.retrieval import (AccessFilter, ContextAssembler, IndexTarget, RetrievalError,
                                RetrievalResult, RetrievedChunk, normalize_query)
from uai_core.vector_store import VectorStoreError


class HaystackRetrieverAdapter:
    """Adapt an injected Haystack retriever object exposing ``run``.

    The object is supplied by the host; this module does not import Haystack.
    Documents must expose content/text and meta with the UAI provenance fields.
    """

    def __init__(self, retriever, *, top_k: int = 10, context: ContextAssembler | None = None):
        if not 1 <= top_k <= 100 or not hasattr(retriever, 'run'):
            raise RetrievalError('invalid_haystack_retriever')
        self.retriever = retriever
        self.top_k = top_k
        self.context = context or ContextAssembler()

    async def retrieve(self, query: str, access: AccessFilter, target: IndexTarget) -> RetrievalResult:
        query = normalize_query(query)
        try:
            allowed = access.validate()
        except VectorStoreError as error:
            raise RetrievalError(str(error)) from None
        filters = {'operator': 'AND', 'conditions': [
            {'field': 'knowledge_base_id', 'operator': 'in', 'value': list(allowed)},
            {'field': 'index_version', 'operator': '==', 'value': target.index_version},
        ]}
        try:
            result = await asyncio.to_thread(self.retriever.run, query=query, filters=filters,
                                             top_k=self.top_k)
        except Exception:
            raise RetrievalError('retrieval_unavailable') from None
        documents = result.get('documents') if isinstance(result, dict) else None
        if not isinstance(documents, list):
            raise RetrievalError('invalid_retrieval_response')
        chunks = []
        for document in documents:
            meta = getattr(document, 'meta', None)
            text = getattr(document, 'content', None) or getattr(document, 'text', None)
            if not isinstance(meta, dict) or not isinstance(text, str):
                raise RetrievalError('invalid_retrieval_response')
            try:
                chunk = RetrievedChunk(
                    chunk_id=meta['chunk_id'], score=float(getattr(document, 'score', 0.0)),
                    knowledge_base_id=meta['knowledge_base_id'], document_id=meta['document_id'],
                    document_hash=meta['document_hash'], document_version=meta['document_version'],
                    page=meta['page'], start=meta['start'], end=meta['end'], text=text)
            except (KeyError, TypeError, ValueError):
                raise RetrievalError('invalid_retrieval_response') from None
            if (chunk.knowledge_base_id not in allowed or meta.get('index_version') != target.index_version
                    or len(chunk.text) != chunk.end - chunk.start):
                raise RetrievalError('unauthorized_result')
            chunks.append(chunk)
        return self.context.assemble(chunks)


__all__ = ['HaystackRetrieverAdapter']
