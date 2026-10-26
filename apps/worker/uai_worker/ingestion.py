"""KB index build, atomic activation and vector cleanup."""
import asyncio
import logging
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from uai_core.chunks import Chunker, ChunkingError
from uai_core.documents import CorruptDocument, DocumentError, DocumentLimit, UnsupportedBackend, UnsupportedDocument
from uai_core.embeddings import EmbeddingError, EmbeddingModel, EmbeddingUnavailable
from uai_core.storage import BlobNotFound, BlobStoreError, BlobStoreUnavailable
from uai_core.vector_store import VectorPoint, VectorStoreError
from uai_runtime.rag import default_processor

from .jobs import safe_code

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexJob:
    knowledge_base_id: str
    version: int
    chunk_size: int
    chunk_overlap: int
    embedding: EmbeddingModel | None
    collection_name: str
    attempts: int


@dataclass(frozen=True)
class DocumentSource:
    id: str
    sha256: str
    blob_key: str
    mime_type: str
    filename: str


@dataclass(frozen=True)
class CleanupJob:
    id: str
    knowledge_base_id: str
    chunk_ids: tuple[str, ...]
    attempts: int


class IndexStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def claim_version(self, worker_id: str, lease_seconds: int) -> IndexJob | None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute(
                    """WITH candidate AS (
                           SELECT knowledge_base_id,version FROM knowledge_base_versions
                           WHERE state='reindexing'
                              OR (state='building' AND (lease_until IS NULL OR lease_until < now()))
                           ORDER BY created_at,knowledge_base_id,version
                           FOR UPDATE SKIP LOCKED LIMIT 1)
                       UPDATE knowledge_base_versions v
                       SET state='building',lease_owner=%s,lease_until=now()+make_interval(secs => %s),
                           attempts=attempts+1,error_code=NULL
                       FROM candidate c
                       WHERE v.knowledge_base_id=c.knowledge_base_id AND v.version=c.version
                       RETURNING v.knowledge_base_id::text,v.version,
                         (v.config->>'chunk_size')::int AS chunk_size,
                         (v.config->>'chunk_overlap')::int AS chunk_overlap,
                         v.embedding_provider,v.embedding_model,v.embedding_version,
                         v.embedding_dimension,v.collection_name,v.attempts""",
                    (worker_id, lease_seconds)).fetchone()
        if not row:
            return None
        embedding = None
        if row['embedding_provider']:
            try:
                embedding = EmbeddingModel(id=row['embedding_model'], provider=row['embedding_provider'],
                                           dimension=int(row['embedding_dimension']),
                                           version=row['embedding_version'], batch_size=128)
            except ValueError:
                embedding = None
        return IndexJob(knowledge_base_id=row['knowledge_base_id'], version=row['version'],
                        chunk_size=row['chunk_size'], chunk_overlap=row['chunk_overlap'],
                        embedding=embedding, collection_name=row['collection_name'], attempts=row['attempts'])

    def documents(self, knowledge_base_id: str) -> list[DocumentSource]:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute(
                """SELECT d.id::text,d.sha256,d.blob_key,d.mime_type,d.filename
                   FROM documents d JOIN document_jobs j ON j.document_id=d.id
                   WHERE d.knowledge_base_id=%s AND j.state='completed'
                   ORDER BY d.created_at,d.id""", (knowledge_base_id,)).fetchall()
        return [DocumentSource(id=row['id'], sha256=row['sha256'], blob_key=row['blob_key'],
                               mime_type=row['mime_type'], filename=row['filename']) for row in rows]

    def insert_chunks(self, document_id: str, chunks) -> None:
        rows = [(chunk.id, document_id, chunk.document_hash, chunk.document_version, chunk.index,
                 chunk.page, chunk.start, chunk.end, chunk.text, chunk.chunk_size, chunk.overlap)
                for chunk in chunks]
        if not rows:
            return
        with psycopg.connect(self.dsn) as conn:
            with conn.transaction():
                with conn.cursor() as cursor:
                    cursor.executemany(
                        """INSERT INTO document_chunks(chunk_id,document_id,document_hash,document_version,
                               chunk_index,page,start_offset,end_offset,text,chunk_size,overlap)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (chunk_id) DO NOTHING""", rows)

    def complete_version(self, job: IndexJob, worker_id: str, chunk_count: int) -> bool:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute(
                    """SELECT state,lease_owner FROM knowledge_base_versions
                       WHERE knowledge_base_id=%s AND version=%s FOR UPDATE""",
                    (job.knowledge_base_id, job.version)).fetchone()
                if not row or row['state'] != 'building' or row['lease_owner'] != worker_id:
                    return False
                conn.execute("""UPDATE knowledge_base_versions SET state='superseded'
                                  WHERE knowledge_base_id=%s AND state='active'""", (job.knowledge_base_id,))
                updated = conn.execute(
                    """UPDATE knowledge_base_versions
                       SET state='active',ready_at=now(),chunk_count=%s,lease_owner=NULL,
                           lease_until=NULL,error_code=NULL
                       WHERE knowledge_base_id=%s AND version=%s AND state='building' AND lease_owner=%s""",
                    (chunk_count, job.knowledge_base_id, job.version, worker_id)).rowcount
                if updated != 1:
                    return False
                conn.execute("""UPDATE knowledge_bases SET active_version=%s,updated_at=now()
                                  WHERE id=%s""", (job.version, job.knowledge_base_id))
                conn.execute("""INSERT INTO audit_events(actor_principal_id,action,target_id)
                                  VALUES('bootstrap-operator','knowledge_base.index_activated',%s)""",
                             (job.knowledge_base_id,))
                return True

    def fail_version(self, job: IndexJob, worker_id: str, code: str, retryable: bool, max_attempts: int) -> None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute(
                    """SELECT state,attempts,lease_owner FROM knowledge_base_versions
                       WHERE knowledge_base_id=%s AND version=%s FOR UPDATE""",
                    (job.knowledge_base_id, job.version)).fetchone()
                if not row or row['state'] != 'building' or row['lease_owner'] != worker_id:
                    return
                if retryable and row['attempts'] < max_attempts:
                    conn.execute("""UPDATE knowledge_base_versions SET state='reindexing',lease_owner=NULL,
                                      lease_until=NULL,error_code=%s
                                      WHERE knowledge_base_id=%s AND version=%s""",
                                 (code, job.knowledge_base_id, job.version))
                else:
                    conn.execute("""UPDATE knowledge_base_versions SET state='failed',lease_owner=NULL,
                                      lease_until=NULL,error_code=%s
                                      WHERE knowledge_base_id=%s AND version=%s""",
                                 (code, job.knowledge_base_id, job.version))

    def collections(self, knowledge_base_id: str) -> list[str]:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            rows = conn.execute("""SELECT collection_name FROM knowledge_base_versions
                                     WHERE knowledge_base_id=%s AND collection_name IS NOT NULL""",
                                (knowledge_base_id,)).fetchall()
        return [row['collection_name'] for row in rows]

    def claim_cleanup(self, worker_id: str, lease_seconds: int) -> CleanupJob | None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute(
                    """WITH candidate AS (
                           SELECT id FROM vector_cleanup_jobs
                           WHERE state='queued' OR (state='running' AND (lease_until IS NULL OR lease_until < now()))
                           ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1)
                       UPDATE vector_cleanup_jobs j
                       SET state='running',attempts=attempts+1,lease_owner=%s,
                           lease_until=now()+make_interval(secs => %s),updated_at=now()
                       FROM candidate c WHERE j.id=c.id
                       RETURNING j.id::text,j.knowledge_base_id::text,j.chunk_ids,j.attempts""",
                    (worker_id, lease_seconds)).fetchone()
        return CleanupJob(id=row['id'], knowledge_base_id=row['knowledge_base_id'],
                          chunk_ids=tuple(row['chunk_ids']), attempts=row['attempts']) if row else None

    def complete_cleanup(self, job: CleanupJob, worker_id: str) -> None:
        with psycopg.connect(self.dsn) as conn:
            with conn.transaction():
                conn.execute("""UPDATE vector_cleanup_jobs SET state='completed',lease_owner=NULL,
                                  lease_until=NULL,error_code=NULL,updated_at=now()
                                  WHERE id=%s AND state='running' AND lease_owner=%s""",
                             (job.id, worker_id))

    def fail_cleanup(self, job: CleanupJob, worker_id: str, code: str, retryable: bool, max_attempts: int) -> None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute("""SELECT state,attempts,lease_owner FROM vector_cleanup_jobs
                                        WHERE id=%s FOR UPDATE""", (job.id,)).fetchone()
                if not row or row['state'] != 'running' or row['lease_owner'] != worker_id:
                    return
                state = 'queued' if retryable and row['attempts'] < max_attempts else 'failed'
                conn.execute("""UPDATE vector_cleanup_jobs SET state=%s,lease_owner=NULL,lease_until=NULL,
                                  error_code=%s,updated_at=now() WHERE id=%s""", (state, code, job.id))


class IndexBuilder:
    def __init__(self, store: IndexStore, blob_store, vector_store, embedding_provider, *,
                 worker_id: str, max_attempts: int = 3, lease_seconds: int = 300,
                 processor=None):
        self.store = store
        self.blob_store = blob_store
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.worker_id = worker_id
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self.processor = processor or default_processor()

    def run_once(self) -> bool:
        job = self.store.claim_version(self.worker_id, self.lease_seconds)
        if job is not None:
            self._build(job)
            return True
        cleanup = self.store.claim_cleanup(self.worker_id, self.lease_seconds)
        if cleanup is not None:
            self._cleanup(cleanup)
            return True
        return False

    def _build(self, job: IndexJob) -> None:
        try:
            if job.embedding is None or not job.collection_name:
                raise EmbeddingError('embedding_configuration_missing')
            if job.embedding.dimension != self.embedding_provider.model.dimension:
                raise EmbeddingError('embedding_dimension_mismatch')
            asyncio.run(self.vector_store.delete_collection(job.collection_name))
            asyncio.run(self.vector_store.ensure_collection(job.collection_name))
            chunk_count = 0
            for document in self.store.documents(job.knowledge_base_id):
                data = asyncio.run(self.blob_store.get(document.blob_key))
                parsed = self.processor.process(data, document.mime_type, document.filename)
                chunks = Chunker(job.chunk_size, job.chunk_overlap).split(
                    parsed, document_hash=document.sha256, document_version=1)
                self.store.insert_chunks(document.id, chunks)
                for start in range(0, len(chunks), self.embedding_provider.model.batch_size):
                    batch = chunks[start:start + self.embedding_provider.model.batch_size]
                    vectors = asyncio.run(self.embedding_provider.embed([chunk.text for chunk in batch]))
                    points = [VectorPoint(chunk_id=chunk.id, vector=tuple(vector),
                                          knowledge_base_id=job.knowledge_base_id, document_id=document.id,
                                          document_hash=document.sha256, document_version=chunk.document_version,
                                          page=chunk.page, start=chunk.start, end=chunk.end, text=chunk.text)
                              for chunk, vector in zip(batch, vectors)]
                    asyncio.run(self.vector_store.upsert(job.collection_name, points))
                chunk_count += len(chunks)
            if self.store.complete_version(job, self.worker_id, chunk_count):
                logger.info('index_activated kb=%s version=%s chunks=%s', job.knowledge_base_id,
                            job.version, chunk_count)
            else:
                logger.info('index_lease_lost_or_cancelled kb=%s version=%s',
                            job.knowledge_base_id, job.version)
        except Exception as error:
            retryable = isinstance(error, (EmbeddingUnavailable, BlobStoreUnavailable, BlobStoreError,
                                           VectorStoreError, psycopg.Error))
            if isinstance(error, VectorStoreError) and str(error) in (
                    'collection_dimension_mismatch', 'invalid_vector_point', 'vector_dimension_mismatch',
                    'invalid_vector_batch'):
                retryable = False
            if isinstance(error, (CorruptDocument, UnsupportedDocument, DocumentLimit, UnsupportedBackend,
                                  DocumentError, ChunkingError)):
                retryable = False
            if isinstance(error, EmbeddingError) and not isinstance(error, EmbeddingUnavailable):
                retryable = False
            try:
                asyncio.run(self.vector_store.delete_collection(job.collection_name))
            except Exception:
                pass
            self.store.fail_version(job, self.worker_id, safe_code(error), retryable, self.max_attempts)
            logger.warning('index_failed kb=%s version=%s code=%s retryable=%s',
                           job.knowledge_base_id, job.version, safe_code(error), retryable)

    def _cleanup(self, job: CleanupJob) -> None:
        try:
            for collection in self.store.collections(job.knowledge_base_id):
                asyncio.run(self.vector_store.delete(collection, job.chunk_ids))
            self.store.complete_cleanup(job, self.worker_id)
        except Exception as error:
            self.store.fail_cleanup(job, self.worker_id, safe_code(error), True, self.max_attempts)


__all__ = ['CleanupJob', 'DocumentSource', 'IndexBuilder', 'IndexJob', 'IndexStore']
