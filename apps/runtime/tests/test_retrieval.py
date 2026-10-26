import asyncio
from types import SimpleNamespace

import pytest

from uai_core.embeddings import EmbeddingModel
from uai_core.retrieval import (AccessFilter, ContextAssembler, IndexTarget, RetrievalError,
                                RetrievedChunk, Retriever)
from uai_core.vector_store import VectorHit
from uai_runtime.rag import HaystackRetrieverAdapter, retriever_from_env

KB_A = '00000000-0000-4000-8000-000000000001'
KB_B = '00000000-0000-4000-8000-000000000002'
DOC = '00000000-0000-4000-8000-000000000003'
HASH = 'a' * 64


def model():
    return EmbeddingModel(id='embed', provider='ollama', dimension=3, version='v1', batch_size=4)


def hit(chunk, kb, score, text):
    return VectorHit(chunk_id=chunk, score=score, knowledge_base_id=kb, document_id=DOC,
                     document_hash=HASH, document_version=1, page=1, start=0, end=len(text), text=text)


class FakeEmbedding:
    def __init__(self, error=None):
        self.model = model()
        self.error = error

    async def embed(self, texts):
        if self.error:
            raise self.error
        return [[1.0, 0.0, 0.0] for _ in texts]


class FakeVector:
    dimension = 3

    def __init__(self, hits):
        self.hits = hits
        self.calls = []

    async def search(self, collection, vector, *, knowledge_base_ids, limit=10):
        self.calls.append((collection, tuple(vector), knowledge_base_ids, limit))
        return self.hits


class ReverseReranker:
    def rerank(self, query, chunks):
        return list(reversed(chunks))


class BadReranker:
    def rerank(self, query, chunks):
        return [RetrievedChunk(chunk_id='z' * 64, score=1, knowledge_base_id=KB_A,
                               document_id=DOC, document_hash=HASH, document_version=1,
                               page=1, start=0, end=1, text='x')]


def run(coro):
    return asyncio.run(coro)


def test_retrieval_filters_version_orders_and_assembles_budget():
    hits = [hit('b' * 64, KB_A, 0.5, 'world'), hit('c' * 64, KB_A, 0.9, 'hello')]
    vector = FakeVector(hits)
    target = IndexTarget.for_knowledge_base(KB_A, model())
    retriever = Retriever(FakeEmbedding(), vector, search_limit=10,
                          context=ContextAssembler(max_chars=5, max_chunks=2))
    result = run(retriever.retrieve('  hello   world ', AccessFilter(frozenset({KB_A})), target))
    assert [chunk.text for chunk in result.chunks] == ['hello']
    assert result.context == 'hello' and result.used_chars == 5
    assert vector.calls[0][2] == {KB_A}
    assert vector.calls[0][3] == 10


def test_acl_embedding_and_version_mismatches_fail_closed():
    target = IndexTarget.for_knowledge_base(KB_A, model())
    retriever = Retriever(FakeEmbedding(), FakeVector([hit('a' * 64, KB_B, 1, 'x')]))
    with pytest.raises(RetrievalError, match='missing_authorized_filter'):
        run(retriever.retrieve('q', AccessFilter(frozenset()), target))
    with pytest.raises(RetrievalError, match='unauthorized_result'):
        run(retriever.retrieve('q', AccessFilter(frozenset({KB_A})), target))
    other = EmbeddingModel(id='embed', provider='ollama', dimension=3, version='v2')
    with pytest.raises(RetrievalError, match='index_version_mismatch'):
        IndexTarget(knowledge_base_id=KB_A, collection=target.collection, index_version=other.index_version, embedding=model())
    class WrongDimensionVector:
        dimension = 4

        async def search(self, *args, **kwargs):
            return []

    with pytest.raises(RetrievalError, match='embedding_index_mismatch'):
        Retriever(FakeEmbedding(), WrongDimensionVector(), search_limit=10)
    with pytest.raises(RetrievalError, match='invalid_query'):
        run(retriever.retrieve('   ', AccessFilter(frozenset({KB_A})), target))


def test_optional_reranker_and_reranker_cannot_add_hits():
    hits = [hit('a' * 64, KB_A, 0.9, 'first'), hit('b' * 64, KB_A, 0.8, 'second')]
    target = IndexTarget.for_knowledge_base(KB_A, model())
    result = run(Retriever(FakeEmbedding(), FakeVector(hits), reranker=ReverseReranker())
                 .retrieve('q', AccessFilter(frozenset({KB_A})), target))
    assert [chunk.text for chunk in result.chunks] == ['second', 'first']
    with pytest.raises(RetrievalError, match='invalid_reranker_response'):
        run(Retriever(FakeEmbedding(), FakeVector(hits), reranker=BadReranker())
            .retrieve('q', AccessFilter(frozenset({KB_A})), target))


def test_haystack_adapter_maps_documents_and_requires_acl_version():
    target = IndexTarget.for_knowledge_base(KB_A, model())
    doc = SimpleNamespace(content='hello', score=0.7, meta={
        'chunk_id': 'a' * 64, 'knowledge_base_id': KB_A, 'document_id': DOC,
        'document_hash': HASH, 'document_version': 1, 'page': 1, 'start': 0, 'end': 5,
        'index_version': target.index_version})
    seen = {}

    class FakeHaystack:
        def run(self, **kwargs):
            seen.update(kwargs)
            return {'documents': [doc]}

    result = run(HaystackRetrieverAdapter(FakeHaystack()).retrieve(
        'q', AccessFilter(frozenset({KB_A})), target))
    assert result.context == 'hello'
    assert seen['filters']['conditions'][0]['value'] == [KB_A]
    assert seen['filters']['conditions'][1]['value'] == target.index_version

    doc.meta = {**doc.meta, 'knowledge_base_id': KB_B}
    with pytest.raises(RetrievalError, match='unauthorized_result'):
        run(HaystackRetrieverAdapter(FakeHaystack()).retrieve(
            'q', AccessFilter(frozenset({KB_A})), target))


def test_retriever_from_env_uses_configured_limits(monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'ollama')
    monkeypatch.setenv('EMBEDDING_MODEL', 'embed')
    monkeypatch.setenv('EMBEDDING_DIMENSION', '3')
    monkeypatch.setenv('EMBEDDING_VERSION', 'v1')
    monkeypatch.setenv('QDRANT_URL', 'http://qdrant:6333')
    monkeypatch.setenv('RETRIEVAL_SEARCH_LIMIT', '7')
    monkeypatch.setenv('RETRIEVAL_CONTEXT_CHARS', '123')
    retriever = retriever_from_env()
    assert retriever.search_limit == 7
    assert retriever.context.max_chars == 123
    assert retriever.embedding_provider.model.dimension == 3
