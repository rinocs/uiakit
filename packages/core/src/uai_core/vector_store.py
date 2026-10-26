"""Vector-store contracts and validation. Retrieval always requires an ACL filter."""
import math
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

MAX_VECTOR_BATCH = 256
MAX_VECTOR_DELETE = 1000
MAX_SEARCH_LIMIT = 100
_COLLECTION = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
_HASH = re.compile(r'^[0-9a-f]{64}$')
_UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class VectorStoreError(Exception):
    """Safe vector-store failure; no URLs, vectors or credentials in messages."""


@dataclass(frozen=True)
class VectorPoint:
    chunk_id: str
    vector: tuple[float, ...]
    knowledge_base_id: str
    document_id: str
    document_hash: str
    document_version: int
    page: int
    start: int
    end: int
    text: str

    def validate(self, dimension: int) -> None:
        if (not _HASH.fullmatch(self.chunk_id) or not _UUID.fullmatch(self.knowledge_base_id)
                or not _UUID.fullmatch(self.document_id) or not _HASH.fullmatch(self.document_hash)
                or self.document_version < 1 or self.page < 1 or self.start < 0
                or self.end <= self.start or len(self.text) != self.end - self.start
                or not self.text or len(self.vector) != dimension):
            raise VectorStoreError('invalid_vector_point')
        for value in self.vector:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise VectorStoreError('invalid_vector_point')


@dataclass(frozen=True)
class VectorHit:
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


class VectorStore(Protocol):
    dimension: int

    async def ensure_collection(self, collection: str) -> None: ...

    async def upsert(self, collection: str, points: Sequence[VectorPoint]) -> None: ...

    async def search(self, collection: str, vector: Sequence[float], *,
                     knowledge_base_ids: frozenset[str], limit: int = 10) -> list[VectorHit]: ...

    async def delete(self, collection: str, chunk_ids: Sequence[str]) -> None: ...

    async def delete_collection(self, collection: str) -> None: ...


def validate_collection_name(collection: str) -> str:
    if not isinstance(collection, str) or not _COLLECTION.fullmatch(collection):
        raise VectorStoreError('invalid_collection')
    return collection


def collection_for(knowledge_base_id: str, index_version: str, prefix: str = 'uai') -> str:
    if not _UUID.fullmatch(knowledge_base_id) or not _HASH.fullmatch(index_version):
        raise VectorStoreError('invalid_collection')
    name = f'{prefix}_{knowledge_base_id.replace("-", "")}_{index_version[:16]}'
    return validate_collection_name(name)


def validate_vector(vector: Sequence[float], dimension: int) -> tuple[float, ...]:
    if not isinstance(vector, (list, tuple)) or len(vector) != dimension:
        raise VectorStoreError('vector_dimension_mismatch')
    values = []
    for value in vector:
        if type(value) not in (int, float) or not math.isfinite(value):
            raise VectorStoreError('invalid_vector')
        values.append(float(value))
    return tuple(values)


def validate_authorized_kbs(knowledge_base_ids: frozenset[str]) -> tuple[str, ...]:
    """An empty filter is never a wildcard: retrieval must fail closed."""
    if not isinstance(knowledge_base_ids, (set, frozenset)) or not knowledge_base_ids:
        raise VectorStoreError('missing_authorized_filter')
    if not all(_UUID.fullmatch(item) for item in knowledge_base_ids):
        raise VectorStoreError('invalid_authorized_filter')
    return tuple(sorted(knowledge_base_ids))


def validate_search(collection: str, vector: Sequence[float], dimension: int,
                    knowledge_base_ids: frozenset[str], limit: int) -> tuple[tuple[float, ...], tuple[str, ...]]:
    validate_collection_name(collection)
    if type(limit) is not int or not 1 <= limit <= MAX_SEARCH_LIMIT:
        raise VectorStoreError('invalid_search_limit')
    return validate_vector(vector, dimension), validate_authorized_kbs(knowledge_base_ids)


def validate_points(points: Sequence[VectorPoint], dimension: int) -> tuple[VectorPoint, ...]:
    if not isinstance(points, (list, tuple)) or not points or len(points) > MAX_VECTOR_BATCH:
        raise VectorStoreError('invalid_vector_batch')
    seen = set()
    for point in points:
        if not isinstance(point, VectorPoint) or point.chunk_id in seen:
            raise VectorStoreError('invalid_vector_batch')
        point.validate(dimension)
        seen.add(point.chunk_id)
    return tuple(points)


def validate_delete_ids(chunk_ids: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(chunk_ids, (list, tuple)) or len(chunk_ids) > MAX_VECTOR_DELETE:
        raise VectorStoreError('invalid_delete_batch')
    if not all(_HASH.fullmatch(chunk_id) for chunk_id in chunk_ids):
        raise VectorStoreError('invalid_delete_batch')
    return tuple(chunk_ids)


__all__ = ['MAX_SEARCH_LIMIT', 'MAX_VECTOR_BATCH', 'MAX_VECTOR_DELETE', 'VectorHit', 'VectorPoint',
           'VectorStore', 'VectorStoreError', 'collection_for', 'validate_authorized_kbs',
           'validate_collection_name', 'validate_delete_ids', 'validate_points', 'validate_search',
           'validate_vector']
