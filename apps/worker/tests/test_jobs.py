import hashlib

import pytest

from uai_core.storage import BlobStoreUnavailable
from uai_worker.jobs import DocumentPayload, Job, JobWorker, safe_code


class FakeBlobStore:
    def __init__(self, data=None, error=None):
        self.data = data
        self.error = error

    async def get(self, key):
        if self.error:
            raise self.error
        return self.data


class FakeBackend:
    def __init__(self, payload, insert_result=True):
        self.payload = payload
        self.insert_result = insert_result
        self.claimed = []
        self.inserted = []
        self.failures = []

    def claim(self, worker_id, lease_seconds):
        return self.claimed.pop(0) if self.claimed else None

    def load_document(self, document_id):
        return self.payload

    def insert_chunks_and_complete(self, job_id, document_id, chunks, worker_id):
        self.inserted.append((job_id, tuple(chunks)))
        return self.insert_result

    def fail(self, job_id, worker_id, code, retryable, max_attempts):
        self.failures.append((job_id, code, retryable))


def payload(text='abcdef', chunk_size=3, overlap=1):
    return DocumentPayload(id='doc', knowledge_base_id='kb', sha256=hashlib.sha256(text.encode()).hexdigest(),
                           blob_key='documents/kb/blob', mime_type='text/plain', filename='x.txt',
                           chunk_size=chunk_size, chunk_overlap=overlap)


def worker(backend, store):
    return JobWorker(backend, store, worker_id='worker-1', max_attempts=3, lease_seconds=60)


def test_valid_document_creates_chunks_and_completes():
    backend = FakeBackend(payload())
    backend.claimed = [Job('job-1', 'doc', 1)]
    w = worker(backend, FakeBlobStore(b'abcdef'))
    assert w.run_once() is True
    assert backend.failures == []
    chunks = backend.inserted[0][1]
    assert [chunk.text for chunk in chunks] == ['abc', 'cde', 'ef']
    assert all(chunk.document_hash == backend.payload.sha256 for chunk in chunks)


def test_corrupt_document_is_permanent_failure():
    backend = FakeBackend(payload())
    backend.claimed = [Job('job-1', 'doc', 1)]
    w = worker(backend, FakeBlobStore(b'\xff'))
    w.run_once()
    assert backend.failures == [('job-1', 'invalid_text_encoding', False)]


def test_transient_storage_failure_is_retryable():
    backend = FakeBackend(payload())
    backend.claimed = [Job('job-1', 'doc', 1)]
    w = worker(backend, FakeBlobStore(error=BlobStoreUnavailable('storage_unavailable')))
    w.run_once()
    assert backend.failures == [('job-1', 'storage_unavailable', True)]


def test_cancelled_or_lease_lost_job_does_not_fail_or_publish():
    backend = FakeBackend(payload(), insert_result=False)
    backend.claimed = [Job('job-1', 'doc', 1)]
    w = worker(backend, FakeBlobStore(b'abcdef'))
    assert w.run_once() is True
    assert backend.failures == []
    assert backend.inserted


def test_run_once_returns_false_without_job_and_safe_code_is_bounded():
    backend = FakeBackend(payload())
    assert worker(backend, FakeBlobStore()).run_once() is False
    assert safe_code(ValueError('Bad Code')) == 'bad_code'
    assert len(safe_code(ValueError('x' * 500))) == 100
    with pytest.raises(ValueError):
        JobWorker(backend, FakeBlobStore(), worker_id='w', max_attempts=0)
