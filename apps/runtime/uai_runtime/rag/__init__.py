"""RAG adapters. Parsing is bounded; retrieval/indexing arrive in later tasks."""
from .parsers import DocxParser, HtmlParser, MarkdownParser, PdfParser, TxtParser, default_processor

__all__ = ['DocxParser', 'HtmlParser', 'MarkdownParser', 'PdfParser', 'TxtParser', 'default_processor']
from .qdrant_store import QdrantVectorStore

__all__.append('QdrantVectorStore')
from .haystack_adapter import HaystackRetrieverAdapter
from .retriever import retriever_from_env

__all__.extend(['HaystackRetrieverAdapter', 'retriever_from_env'])
