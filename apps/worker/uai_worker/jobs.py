"""Durable job claim, lease, retry and checkpointed chunk publication."""
import asyncio
import logging

from uai_core.telemetry import get_telemetry
from dataclasses import dataclass
from typing import Protocol

import psycopg
from psycopg.rows import dict_row

from uai_core.chunks import Chunker, ChunkingError
from uai_core.documents import (CorruptDocument, DocumentError, DocumentLimit, DocumentProcessor,
                                UnsupportedBackend, UnsupportedDocument)
from uai_core.storage import BlobNotFound, BlobStoreError, BlobStoreUnavailable
from uai_runtime.rag import default_processor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Job:
    id: str
    document_id: str
    attempts: int


@dataclass(frozen=True)
class DocumentPayload:
    id: str
    knowledge_base_id: str
    sha256: str
    blob_key: str
    mime_type: str
    filename: str
    chunk_size: int
    chunk_overlap: int


class JobBackend(Protocol):
    def claim(self, worker_id: str, lease_seconds: int) -> Job | None: ...

    def load_document(self, document_id: str) -> DocumentPayload: ...

    def insert_chunks_and_complete(self, job_id: str, document_id: str, chunks, worker_id: str) -> bool: ...

    def fail(self, job_id: str, worker_id: str, code: str, retryable: bool, max_attempts: int) -> None: ...


def safe_code(error: Exception) -> str:
    code = str(error).strip().lower().replace(' ', '_')
    return code[:100] if code else 'worker_error'


class JobStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def claim(self, worker_id: str, lease_seconds: int) -> Job | None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute(
                    """WITH candidate AS (
                           SELECT id FROM document_jobs
                           WHERE state='queued'
                              OR (state='running' AND (lease_until IS NULL OR lease_until < now()))
                           ORDER BY created_at,id
                           FOR UPDATE SKIP LOCKED LIMIT 1
                       )
                       UPDATE document_jobs j
                       SET state='running', attempts=attempts+1, lease_owner=%s,
                           lease_until=now()+make_interval(secs => %s), updated_at=now()
                       FROM candidate c WHERE j.id=c.id
                       RETURNING j.id::text,j.document_id::text,j.attempts""",
                    (worker_id, lease_seconds)).fetchone()
        return Job(id=row['id'], document_id=row['document_id'], attempts=row['attempts']) if row else None

    def load_document(self, document_id: str) -> DocumentPayload:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            row = conn.execute(
                """SELECT d.id::text,d.knowledge_base_id::text,d.sha256,d.blob_key,d.mime_type,d.filename,
                          (kv.config->>'chunk_size') AS chunk_size,(kv.config->>'chunk_overlap') AS chunk_overlap
                   FROM documents d
                   JOIN knowledge_bases k ON k.id=d.knowledge_base_id
                   JOIN knowledge_base_versions kv
                     ON kv.knowledge_base_id=k.id AND kv.version=k.active_version
                   WHERE d.id=%s""", (document_id,)).fetchone()
        if not row:
            raise DocumentError('document_missing')
        try:
            chunk_size = int(row['chunk_size'])
            overlap = int(row['chunk_overlap'])
        except (TypeError, ValueError):
            raise DocumentError('invalid_kb_configuration') from None
        return DocumentPayload(id=row['id'], knowledge_base_id=row['knowledge_base_id'],
                               sha256=row['sha256'], blob_key=row['blob_key'],
                               mime_type=row['mime_type'], filename=row['filename'],
                               chunk_size=chunk_size, chunk_overlap=overlap)

    def insert_chunks_and_complete(self, job_id: str, document_id: str, chunks, worker_id: str) -> bool:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute(
                    """SELECT state,lease_owner FROM document_jobs WHERE id=%s FOR UPDATE""",
                    (job_id,)).fetchone()
                if not row or row['state'] != 'running' or row['lease_owner'] != worker_id:
                    return False
                rows = [(chunk.id, document_id, chunk.document_hash, chunk.document_version,
                         chunk.index, chunk.page, chunk.start, chunk.end, chunk.text,
                         chunk.chunk_size, chunk.overlap) for chunk in chunks]
                if rows:
                    with conn.cursor() as cursor:
                        cursor.executemany(
                            """INSERT INTO document_chunks(chunk_id,document_id,document_hash,document_version,
                                   chunk_index,page,start_offset,end_offset,text,chunk_size,overlap)
                               VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                               ON CONFLICT (chunk_id) DO NOTHING""", rows)
                updated = conn.execute(
                    """UPDATE document_jobs SET state='completed',lease_owner=NULL,lease_until=NULL,
                           error_code=NULL,updated_at=now()
                       WHERE id=%s AND state='running' AND lease_owner=%s""",
                    (job_id, worker_id)).rowcount
                return updated == 1

    def fail(self, job_id: str, worker_id: str, code: str, retryable: bool, max_attempts: int) -> None:
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                row = conn.execute(
                    """SELECT state,attempts,lease_owner FROM document_jobs WHERE id=%s FOR UPDATE""",
                    (job_id,)).fetchone()
                if not row or row['state'] != 'running' or row['lease_owner'] != worker_id:
                    return
                if retryable and row['attempts'] < max_attempts:
                    conn.execute(
                        """UPDATE document_jobs SET state='queued',lease_owner=NULL,lease_until=NULL,
                               error_code=%s,updated_at=now() WHERE id=%s""", (code, job_id))
                else:
                    conn.execute(
                        """UPDATE document_jobs SET state='failed',lease_owner=NULL,lease_until=NULL,
                               error_code=%s,dead_lettered_at=now(),updated_at=now() WHERE id=%s""",
                        (code, job_id))


class JobWorker:
    def __init__(self, backend: JobBackend, blob_store, *, worker_id: str,
                 max_attempts: int = 3, lease_seconds: int = 300,
                 processor: DocumentProcessor | None = None):
        if max_attempts < 1 or lease_seconds < 1:
            raise ValueError('invalid_worker_configuration')
        self.backend = backend
        self.blob_store = blob_store
        self.worker_id = worker_id
        self.max_attempts = max_attempts
        self.lease_seconds = lease_seconds
        self.processor = processor or default_processor()

    def run_once(self) -> bool:
        job = self.backend.claim(self.worker_id, self.lease_seconds)
        if job is None:
            return False
        telemetry = get_telemetry('uai-worker')
        span = None
        if telemetry.tracer is not None:
            span = telemetry.tracer.start_span('ingestion.document', attributes={
                'document_id': job.document_id,
                'attempts': job.attempts,
            })
        try:
            document = self.backend.load_document(job.document_id)
            try:
                data = asyncio.run(self.blob_store.get(document.blob_key))
            except BlobNotFound:
                raise DocumentError('blob_not_found') from None
            except BlobStoreUnavailable:
                raise
            except BlobStoreError:
                raise
            parsed = self.processor.process(data, document.mime_type, document.filename)
            chunks = Chunker(document.chunk_size, document.chunk_overlap).split(
                parsed, document_hash=document.sha256, document_version=1)
            if self.backend.insert_chunks_and_complete(job.id, document.id, chunks, self.worker_id):
                logger.info('job_completed id=%s chunks=%s', job.id, len(chunks))
            else:
                logger.info('job_lease_lost_or_cancelled id=%s', job.id)
        except (CorruptDocument, UnsupportedDocument, DocumentLimit, UnsupportedBackend,
                DocumentError, ChunkingError) as error:
            self._fail(job, safe_code(error), retryable=False)
        except BlobStoreUnavailable as error:
            self._fail(job, safe_code(error), retryable=True)
        except BlobStoreError as error:
            self._fail(job, safe_code(error), retryable=True)
        except Exception:
            logger.warning('job_failed id=%s code=worker_error', job.id)
            self._fail(job, 'worker_error', retryable=True)
        finally:
            if span is not None:
                span.end()
        return True

    def _fail(self, job: Job, code: str, *, retryable: bool) -> None:
        try:
            self.backend.fail(job.id, self.worker_id, code, retryable, self.max_attempts)
            logger.warning('job_failed id=%s code=%s retryable=%s', job.id, code, retryable)
        except Exception:
            logger.warning('job_failure_not_persisted id=%s', job.id)


__all__ = ['DocumentPayload', 'Job', 'JobBackend', 'JobStore', 'JobWorker', 'safe_code']
