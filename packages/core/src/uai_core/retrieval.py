"""Composable retrieval: ACL/version checks, optional rerank, deterministic context."""
import inspect
import math
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .embeddings import EmbeddingError, EmbeddingModel, EmbeddingProvider
from .vector_store import (VectorHit, VectorStore, VectorStoreError, collection_for,
                           validate_authorized_kbs, validate_collection_name)

MAX_QUERY_CHARS = 32000
MAX_RETRIEVAL_LIMIT = 100
MAX_CONTEXT_CHARS = 64000
MAX_CONTEXT_CHUNKS = 50


class RetrievalError(Exception):
    """Safe retrieval failure; no query text, vectors or credentials in messages."""


@dataclass(frozen=True)
class AccessFilter:
    knowledge_base_ids: frozenset[str]

    def validate(self) -> tuple[str, ...]:
        return validate_authorized_kbs(self.knowledge_base_ids)


@dataclass(frozen=True)
class IndexTarget:
    knowledge_base_id: str
    collection: str
    index_version: str
    embedding: EmbeddingModel

    def __post_init__(self):
        if not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', self.knowledge_base_id):
            raise RetrievalError('invalid_knowledge_base')
        validate_collection_name(self.collection)
        if self.embedding.index_version != self.index_version:
            raise RetrievalError('index_version_mismatch')

    @classmethod
    def for_knowledge_base(cls, knowledge_base_id: str, embedding: EmbeddingModel) -> 'IndexTarget':
        return cls(knowledge_base_id=knowledge_base_id,
                   collection=collection_for(knowledge_base_id, embedding.index_version),
                   index_version=embedding.index_version, embedding=embedding)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    score: float
    knowledge_base_id: str
    document_id: str
    document_hash: str
    document_version: int
    page: int
    start: int
    end: int
    text: str

    @classmethod
    def from_hit(cls, hit: VectorHit) -> 'RetrievedChunk':
        return cls(chunk_id=hit.chunk_id, score=float(hit.score), knowledge_base_id=hit.knowledge_base_id,
                   document_id=hit.document_id, document_hash=hit.document_hash,
                   document_version=hit.document_version, page=hit.page, start=hit.start,
                   end=hit.end, text=hit.text)


class Citation(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    citation_id: str = Field(pattern=r'^C[1-9][0-9]{0,2}$')
    chunk_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    knowledge_base_id: str = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    document_id: str = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    document_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    document_version: int = Field(ge=1)
    page: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


def assemble_citations(output: str, retrieved: dict[str, Citation]) -> tuple[Citation, ...]:
    """Return citations actually referenced by generated text, in first-use order."""
    if not isinstance(output, str):
        return ()
    used = []
    seen = set()
    for citation_id in re.findall(r'\[(C[1-9][0-9]{0,2})\]', output):
        if citation_id in retrieved and citation_id not in seen:
            seen.add(citation_id)
            used.append(retrieved[citation_id])
    return tuple(used)


class Reranker(Protocol):
    def rerank(self, query: str, chunks: Sequence[RetrievedChunk]) -> Sequence[RetrievedChunk]: ...


@dataclass(frozen=True)
class RetrievalResult:
    chunks: tuple[RetrievedChunk, ...]
    context: str
    used_chars: int


def normalize_query(query: str) -> str:
    if not isinstance(query, str):
        raise RetrievalError('invalid_query')
    query = ' '.join(query.split())
    if not query or len(query) > MAX_QUERY_CHARS:
        raise RetrievalError('invalid_query')
    return query


class ContextAssembler:
    def __init__(self, max_chars: int = 8000, max_chunks: int = 10):
        if type(max_chars) is not int or not 1 <= max_chars <= MAX_CONTEXT_CHARS:
            raise RetrievalError('invalid_context_budget')
        if type(max_chunks) is not int or not 1 <= max_chunks <= MAX_CONTEXT_CHUNKS:
            raise RetrievalError('invalid_context_budget')
        self.max_chars = max_chars
        self.max_chunks = max_chunks

    def assemble(self, chunks: Sequence[RetrievedChunk]) -> RetrievalResult:
        selected = []
        used = 0
        seen = set()
        for chunk in chunks:
            if chunk.chunk_id in seen or len(selected) >= self.max_chunks:
                continue
            if used + len(chunk.text) > self.max_chars:
                continue
            seen.add(chunk.chunk_id)
            selected.append(chunk)
            used += len(chunk.text)
        return RetrievalResult(chunks=tuple(selected), context='\n\n'.join(c.text for c in selected),
                               used_chars=used)


class Retriever:
    def __init__(self, embedding_provider: EmbeddingProvider, vector_store: VectorStore, *,
                 reranker: Reranker | None = None, search_limit: int = 20,
                 context: ContextAssembler | None = None):
        if type(search_limit) is not int or not 1 <= search_limit <= MAX_RETRIEVAL_LIMIT:
            raise RetrievalError('invalid_retrieval_limit')
        if embedding_provider.model.dimension != vector_store.dimension:
            raise RetrievalError('embedding_index_mismatch')
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.reranker = reranker
        self.search_limit = search_limit
        self.context = context or ContextAssembler()

    async def retrieve(self, query: str, access: AccessFilter, target: IndexTarget) -> RetrievalResult:
        query = normalize_query(query)
        try:
            allowed = access.validate()
        except VectorStoreError as error:
            raise RetrievalError(str(error)) from None
        if (target.embedding.index_version != self.embedding_provider.model.index_version
                or target.embedding.dimension != self.embedding_provider.model.dimension):
            raise RetrievalError('embedding_index_mismatch')
        try:
            vectors = await self.embedding_provider.embed([query])
        except EmbeddingError:
            raise
        if len(vectors) != 1:
            raise RetrievalError('invalid_query_embedding')
        hits = await self.vector_store.search(target.collection, vectors[0],
                                              knowledge_base_ids=frozenset(allowed),
                                              limit=self.search_limit)
        if len({hit.chunk_id for hit in hits}) != len(hits):
            raise RetrievalError('invalid_retrieval_response')
        original = {hit.chunk_id: RetrievedChunk.from_hit(hit) for hit in hits}
        chunks = list(original.values())
        if any(chunk.knowledge_base_id not in allowed for chunk in chunks):
            raise RetrievalError('unauthorized_result')
        if self.reranker is not None:
            reranked = self.reranker.rerank(query, chunks)
            if inspect.isawaitable(reranked):
                reranked = await reranked
            if not isinstance(reranked, (list, tuple)):
                raise RetrievalError('invalid_reranker_response')
            ids = [chunk.chunk_id for chunk in reranked]
            if len(ids) != len(set(ids)) or any(chunk_id not in original for chunk_id in ids):
                raise RetrievalError('invalid_reranker_response')
            chunks = [original[chunk_id] for chunk_id in ids]
        else:
            chunks.sort(key=lambda chunk: (-chunk.score, chunk.chunk_id))
        if any(not math.isfinite(chunk.score) for chunk in chunks):
            raise RetrievalError('invalid_reranker_response')
        return self.context.assemble(chunks)


__all__ = ['AccessFilter', 'assemble_citations', 'Citation', 'ContextAssembler', 'IndexTarget', 'MAX_CONTEXT_CHARS', 'MAX_CONTEXT_CHUNKS',
           'MAX_QUERY_CHARS', 'MAX_RETRIEVAL_LIMIT', 'Reranker', 'RetrievalError', 'RetrievalResult',
           'RetrievedChunk', 'Retriever', 'normalize_query']
