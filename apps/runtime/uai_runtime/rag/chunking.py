"""Runtime chunking facade; algorithm and contracts live in uai_core.chunks."""
from uai_core.chunks import Chunk, Chunker, ChunkingError, chunk_document

__all__ = ['Chunk', 'Chunker', 'ChunkingError', 'chunk_document']
