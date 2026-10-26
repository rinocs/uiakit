"""Embedding contracts with explicit model identity, dimensions and batch limits."""
import hashlib
import math
from dataclasses import dataclass
from typing import Literal, Protocol, Sequence

MAX_EMBEDDING_TEXTS = 128
MAX_EMBEDDING_TEXT_CHARS = 32000


class EmbeddingError(Exception):
    """Safe embedding failure; messages are stable codes, not vectors or keys."""


class EmbeddingUnavailable(EmbeddingError):
    """The embedding backend is unavailable or timed out."""


@dataclass(frozen=True)
class EmbeddingModel:
    id: str
    provider: Literal['ollama', 'openai-compatible']
    dimension: int
    version: str
    batch_size: int = 32

    def __post_init__(self):
        if (not isinstance(self.id, str) or not self.id or len(self.id) > 200
                or self.provider not in ('ollama', 'openai-compatible')
                or not isinstance(self.version, str) or not self.version or len(self.version) > 200
                or type(self.dimension) is not int or not 1 <= self.dimension <= 8192
                or type(self.batch_size) is not int or not 1 <= self.batch_size <= MAX_EMBEDDING_TEXTS):
            raise ValueError('invalid_embedding_model')

    @property
    def index_version(self) -> str:
        payload = f'{self.provider}\x00{self.id}\x00{self.version}\x00{self.dimension}'.encode()
        return hashlib.sha256(payload).hexdigest()


class EmbeddingProvider(Protocol):
    model: EmbeddingModel

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def validate_texts(model: EmbeddingModel, texts: Sequence[str]) -> tuple[str, ...]:
    if not isinstance(texts, (list, tuple)) or not texts or len(texts) > model.batch_size:
        raise EmbeddingError('invalid_embedding_batch')
    result = []
    for text in texts:
        if (not isinstance(text, str) or not text.strip() or len(text) > MAX_EMBEDDING_TEXT_CHARS):
            raise EmbeddingError('invalid_embedding_text')
        result.append(text)
    return tuple(result)


def validate_vectors(model: EmbeddingModel, vectors, expected: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected:
        raise EmbeddingError('invalid_embedding_response')
    result = []
    for vector in vectors:
        if not isinstance(vector, (list, tuple)) or len(vector) != model.dimension:
            raise EmbeddingError('embedding_dimension_mismatch')
        clean = []
        for value in vector:
            if type(value) not in (int, float) or not math.isfinite(value):
                raise EmbeddingError('invalid_embedding_response')
            clean.append(float(value))
        result.append(clean)
    return result


__all__ = ['EmbeddingError', 'EmbeddingModel', 'EmbeddingProvider', 'EmbeddingUnavailable',
           'MAX_EMBEDDING_TEXTS', 'MAX_EMBEDDING_TEXT_CHARS', 'validate_texts', 'validate_vectors']
