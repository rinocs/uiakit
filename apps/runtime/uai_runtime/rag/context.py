"""Context assembly re-export; budget logic lives in uai_core.retrieval."""
from uai_core.retrieval import ContextAssembler, RetrievalResult, RetrievedChunk

__all__ = ['ContextAssembler', 'RetrievalResult', 'RetrievedChunk']
