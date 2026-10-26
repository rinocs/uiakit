"""Universal AI Kit execution contracts, independent of HTTP and persistence."""
from .directives import Directive, DirectiveRegistry, DirectivePipeline, DirectiveError
from .capabilities import Capability, ModelDefinition
from .configuration import AssistantConfig
from .agent import Agent, AgentRuntime
from .context import ExecutionAuthority, ExecutionContext, ExecutionLimits
from .events import LifecycleEvent, LifecycleEventType, RuntimeEvent, RuntimeEventType
from .memory import MemoryProvider, MemoryScope, WorkingMemory
from .models import Message, ModelInput
from .tools import ToolDefinition, ToolExecutionError
from .providers import ModelChunk, ModelProvider, ProviderError
from .storage import BlobNotFound, BlobStore, BlobStoreError, BlobStoreUnavailable, new_blob_key, validate_blob_key
from .chunks import Chunk, Chunker, ChunkingError, chunk_document
from .embeddings import (EmbeddingError, EmbeddingModel, EmbeddingProvider, EmbeddingUnavailable)
from .documents import (BytesLoader, CorruptDocument, DocumentError, DocumentLimit, DocumentLoader,
                        DocumentPage, DocumentParser, DocumentProcessor, GitLoader, OcrProvider,
                        ParsedDocument, SqlConnector, UnsupportedBackend, UnsupportedDocument,
                        WebLoader, document_from_pages, normalize_text)

__all__ = [
    'ToolDefinition', 'ToolExecutionError',
    'LifecycleEvent', 'LifecycleEventType',
    'Directive', 'DirectiveRegistry', 'DirectivePipeline', 'DirectiveError',
    'AssistantConfig', 'Capability', 'ModelDefinition', 'Agent', 'AgentRuntime', 'ExecutionAuthority', 'ExecutionContext',
    'ExecutionLimits', 'RuntimeEvent', 'RuntimeEventType', 'MemoryProvider',
    'MemoryScope', 'WorkingMemory', 'Message', 'ModelInput', 'ModelChunk',
    'ModelProvider', 'ProviderError',
    'BlobStore', 'BlobStoreError', 'BlobStoreUnavailable', 'BlobNotFound',
    'new_blob_key', 'validate_blob_key',
    'BytesLoader', 'CorruptDocument', 'DocumentError', 'DocumentLimit', 'DocumentLoader',
    'DocumentPage', 'DocumentParser', 'DocumentProcessor', 'GitLoader', 'OcrProvider',
    'ParsedDocument', 'SqlConnector', 'UnsupportedBackend', 'UnsupportedDocument',
    'WebLoader', 'document_from_pages', 'normalize_text',
    'Chunk', 'Chunker', 'ChunkingError', 'chunk_document',
    'EmbeddingError', 'EmbeddingModel', 'EmbeddingProvider', 'EmbeddingUnavailable',
]
