"""Worker process: poll PostgreSQL, claim one job at a time, process documents."""
import logging
import os
import signal
import socket
import time

from .telemetry import configure

from uai_runtime.egress import EgressPolicy
from uai_runtime.providers import embedding_provider_from_env
from uai_runtime.rag import QdrantVectorStore, default_processor
from uai_runtime.secrets import secret_from_env
from uai_runtime.storage import S3BlobStore, filesystem_from_env

from .ingestion import IndexBuilder, IndexStore
from .jobs import JobStore, JobWorker

logger = logging.getLogger(__name__)
_stop = False


def _handle_stop(signum, frame):
    global _stop
    _stop = True


def build_worker() -> tuple[JobWorker, IndexBuilder]:
    backend = os.environ.get('UAI_STORAGE_BACKEND', 'filesystem')
    if backend == 'filesystem':
        blob_store = filesystem_from_env()
    elif backend == 's3':
        blob_store = S3BlobStore.from_env()
    else:
        raise ValueError('invalid_storage_backend')
    worker_id = os.environ.get('UAI_WORKER_ID', f'{socket.gethostname()}:{os.getpid()}')
    dsn = secret_from_env('DATABASE_URL', required=True)
    max_attempts = int(os.environ.get('UAI_WORKER_MAX_ATTEMPTS', '3'))
    lease_seconds = int(os.environ.get('UAI_WORKER_LEASE_SECONDS', '300'))
    processor = default_processor()
    worker = JobWorker(JobStore(dsn), blob_store, worker_id=worker_id,
                       max_attempts=max_attempts, lease_seconds=lease_seconds, processor=processor)
    embedding = embedding_provider_from_env(EgressPolicy.from_env())
    vector_store = QdrantVectorStore(os.environ.get('QDRANT_URL', 'http://qdrant:6333'),
                                     embedding.model.dimension)
    indexer = IndexBuilder(IndexStore(dsn), blob_store, vector_store, embedding,
                           worker_id=worker_id, max_attempts=max_attempts,
                           lease_seconds=lease_seconds, processor=processor)
    return worker, indexer


def main() -> None:
    configure()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    worker, indexer = build_worker()
    poll = float(os.environ.get('UAI_WORKER_POLL_SECONDS', '2'))
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    once = os.environ.get('UAI_WORKER_ONCE') == '1'
    while not _stop:
        worked = worker.run_once()
        if _stop or (worked and once):
            break
        indexed = indexer.run_once()
        worked = worked or indexed
        if not worked:
            if once:
                break
            time.sleep(poll)
        elif once:
            break


if __name__ == '__main__':
    main()
