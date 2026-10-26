from uai_core.embeddings import EmbeddingError, EmbeddingModel, EmbeddingUnavailable
from uai_worker.ingestion import CleanupJob, DocumentSource, IndexBuilder, IndexJob


class FakeBlob:
    def __init__(self, data=b'hello world'):
        self.data = data

    async def get(self, key):
        return self.data


class FakeEmbedding:
    def __init__(self, error=None):
        self.model = EmbeddingModel(id='embed', provider='ollama', dimension=2, version='v1', batch_size=2)
        self.error = error

    async def embed(self, texts):
        if self.error:
            raise self.error
        return [[1.0, 0.0] for _ in texts]


class FakeVector:
    dimension = 2

    def __init__(self):
        self.deleted = []
        self.points = []
        self.ensured = []

    async def delete_collection(self, collection):
        self.deleted.append(collection)

    async def ensure_collection(self, collection):
        self.ensured.append(collection)

    async def upsert(self, collection, points):
        self.points.extend(points)

    async def delete(self, collection, chunk_ids):
        self.deleted.append((collection, tuple(chunk_ids)))


class FakeStore:
    def __init__(self, job=None, cleanup=None):
        self.job = job
        self.cleanup = cleanup
        self.completed = []
        self.failed = []
        self.cleanup_completed = []
        self.document_rows = [DocumentSource(id='00000000-0000-4000-8000-000000000002',
                                              sha256='b' * 64, blob_key='documents/kb/blob',
                                              mime_type='text/plain', filename='x.txt')]

    def claim_version(self, worker_id, lease_seconds):
        return self.job

    def documents(self, kb):
        return self.document_rows

    def insert_chunks(self, document_id, chunks):
        self.inserted = (document_id, tuple(chunks))

    def complete_version(self, job, worker_id, chunk_count):
        self.completed.append((job, chunk_count))
        return True

    def fail_version(self, job, worker_id, code, retryable, max_attempts):
        self.failed.append((code, retryable))

    def collections(self, kb):
        return ['uai_collection']

    def claim_cleanup(self, worker_id, lease_seconds):
        return self.cleanup

    def complete_cleanup(self, job, worker_id):
        self.cleanup_completed.append(job.id)

    def fail_cleanup(self, job, worker_id, code, retryable, max_attempts):
        self.failed.append((code, retryable))


def job(embedding=True):
    return IndexJob(knowledge_base_id='00000000-0000-4000-8000-000000000001', version=2,
                    chunk_size=3, chunk_overlap=1,
                    embedding=FakeEmbedding().model if embedding else None,
                    collection_name='uai_collection', attempts=1)


def builder(store, embedding=None, vector=None):
    return IndexBuilder(store, FakeBlob(), vector or FakeVector(), embedding or FakeEmbedding(),
                        worker_id='worker-1', max_attempts=3, lease_seconds=60)


def test_build_publishes_chunks_and_activates_version():
    store, vector = FakeStore(job()), FakeVector()
    assert builder(store, vector=vector).run_once() is True
    assert store.completed[0][1] == 5
    assert len(vector.points) == 5
    assert all(point.text == 'hel' for point in vector.points[:1])
    assert vector.deleted == ['uai_collection']


def test_build_dimension_mismatch_and_permanent_embedding_error_fail_closed():
    store, vector = FakeStore(job()), FakeVector()
    bad = FakeEmbedding(EmbeddingError('invalid_embedding_response'))
    builder(store, embedding=bad, vector=vector).run_once()
    assert store.failed == [('invalid_embedding_response', False)]
    assert vector.deleted == ['uai_collection', 'uai_collection']

    store, vector = FakeStore(job()), FakeVector()
    no_embedding = job(embedding=False)
    store.job = no_embedding
    builder(store, vector=vector).run_once()
    assert store.failed == [('embedding_configuration_missing', False)]


def test_transient_embedding_failure_is_retryable_and_cleanup_is_idempotent():
    store, vector = FakeStore(job()), FakeVector()
    transient = FakeEmbedding(EmbeddingUnavailable('embedding_unavailable'))
    builder(store, embedding=transient, vector=vector).run_once()
    assert store.failed == [('embedding_unavailable', True)]

    cleanup = CleanupJob(id='cleanup', knowledge_base_id='kb', chunk_ids=('a' * 64,), attempts=1)
    store = FakeStore(cleanup=cleanup)
    assert builder(store, vector=vector).run_once() is True
    assert vector.deleted[-1] == ('uai_collection', ('a' * 64,))
    assert store.cleanup_completed == ['cleanup']
