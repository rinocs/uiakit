import asyncio
import json
import os
import uuid

import httpx
import pytest

from uai_core.vector_store import (VectorPoint, VectorStoreError, collection_for,
                                   validate_authorized_kbs)
from uai_runtime.rag import QdrantVectorStore


def run(coro):
    return asyncio.run(coro)


def point(kb, chunk='a' * 64, vector=(1.0, 0.0, 0.0)):
    return VectorPoint(chunk_id=chunk, vector=vector, knowledge_base_id=kb,
                       document_id='00000000-0000-4000-8000-000000000002',
                       document_hash='b' * 64, document_version=1, page=1,
                       start=0, end=5, text='hello')


def test_collection_and_filter_requirements():
    kb = '00000000-0000-4000-8000-000000000001'
    name = collection_for(kb, 'c' * 64)
    assert name.startswith('uai_') and len(name) <= 64
    with pytest.raises(VectorStoreError, match='missing_authorized_filter'):
        validate_authorized_kbs(frozenset())
    with pytest.raises(VectorStoreError, match='invalid_collection'):
        collection_for('../escape', 'c' * 64)


def test_search_requires_filter_and_sends_server_side_any():
    seen = {}

    async def handler(request):
        seen['path'] = request.url.path
        seen['body'] = json.loads(request.content)
        return httpx.Response(200, json={'result': [{
            'id': '00000000-0000-0000-0000-000000000001', 'score': 0.9,
            'payload': {'chunk_id': 'a' * 64, 'knowledge_base_id': '00000000-0000-4000-8000-000000000001',
                        'document_id': '00000000-0000-4000-8000-000000000002', 'document_hash': 'b' * 64,
                        'document_version': 1, 'page': 1, 'start': 0, 'end': 5, 'text': 'hello'}}]})

    store = QdrantVectorStore('http://qdrant:6333', 3, transport=httpx.MockTransport(handler))
    with pytest.raises(VectorStoreError, match='missing_authorized_filter'):
        run(store.search('uai_test', [1, 0, 0], knowledge_base_ids=frozenset()))
    assert seen == {}
    hits = run(store.search('uai_test', [1, 0, 0],
                            knowledge_base_ids=frozenset({'00000000-0000-4000-8000-000000000001'})))
    assert hits[0].chunk_id == 'a' * 64 and hits[0].score == 0.9
    assert seen['path'] == '/collections/uai_test/points/search'
    assert seen['body']['filter']['must'][0]['match']['any'] == ['00000000-0000-4000-8000-000000000001']


def test_upsert_creates_collection_and_uses_stable_uuid():
    calls = []
    kb = '00000000-0000-4000-8000-000000000001'

    async def handler(request):
        calls.append((request.method, request.url.path, request.content))
        if request.method == 'GET':
            return httpx.Response(404, request=request)
        return httpx.Response(200, request=request, json={'result': True})

    store = QdrantVectorStore('http://qdrant:6333', 3, transport=httpx.MockTransport(handler))
    run(store.upsert('uai_test', [point(kb)]))
    assert [(method, path) for method, path, _ in calls] == [
        ('GET', '/collections/uai_test'),
        ('PUT', '/collections/uai_test'),
        ('PUT', '/collections/uai_test/points'),
    ]
    body = json.loads(calls[-1][2])
    assert body['points'][0]['payload']['chunk_id'] == 'a' * 64
    assert body['points'][0]['payload']['text'] == 'hello'
    assert str(uuid.UUID(body['points'][0]['id'])) == body['points'][0]['id']


def test_dimension_mismatch_and_delete_idempotency():
    async def existing(request):
        if request.method == 'GET':
            return httpx.Response(200, request=request, json={'result': {'config': {'params': {'vectors': {'size': 4}}}}})
        return httpx.Response(200, request=request, json={'result': True})

    store = QdrantVectorStore('http://qdrant:6333', 3, transport=httpx.MockTransport(existing))
    with pytest.raises(VectorStoreError, match='collection_dimension_mismatch'):
        run(store.ensure_collection('uai_test'))
    with pytest.raises(VectorStoreError, match='vector_dimension_mismatch'):
        run(store.search('uai_test', [1, 0], knowledge_base_ids=frozenset({'00000000-0000-4000-8000-000000000001'})))

    calls = []

    async def missing_then_ok(request):
        calls.append(request.method)
        if request.url.path == '/collections/uai_test/points/delete':
            return httpx.Response(200, request=request, json={'result': {}})
        return httpx.Response(404, request=request)

    store = QdrantVectorStore('http://qdrant:6333', 3, transport=httpx.MockTransport(missing_then_ok))
    run(store.delete('uai_test', []))
    assert calls == []
    run(store.delete('uai_test', ['a' * 64]))
    run(store.delete('uai_test', ['a' * 64]))
    assert calls == ['POST', 'POST']


def test_missing_index_fails_closed_and_bad_payload_is_rejected():
    async def missing(request):
        return httpx.Response(404, request=request)

    store = QdrantVectorStore('http://qdrant:6333', 3, transport=httpx.MockTransport(missing))
    with pytest.raises(VectorStoreError, match='index_not_ready'):
        run(store.search('uai_test', [1, 0, 0],
                         knowledge_base_ids=frozenset({'00000000-0000-4000-8000-000000000001'})))

    async def bad(request):
        return httpx.Response(200, request=request, json={'result': [{'score': 1, 'payload': {}}]})

    store = QdrantVectorStore('http://qdrant:6333', 3, transport=httpx.MockTransport(bad))
    with pytest.raises(VectorStoreError, match='invalid_vector_store_response'):
        run(store.search('uai_test', [1, 0, 0],
                         knowledge_base_ids=frozenset({'00000000-0000-4000-8000-000000000001'})))


@pytest.mark.skipif(not os.environ.get('UAI_QDRANT_TEST_URL'), reason='Qdrant endpoint not configured')
def test_qdrant_two_knowledge_bases_are_isolated():
    kb_a = '00000000-0000-4000-8000-000000000001'
    kb_b = '00000000-0000-4000-8000-000000000002'
    collection = 'uai_' + uuid.uuid4().hex
    store = QdrantVectorStore(os.environ['UAI_QDRANT_TEST_URL'], 3)
    run(store.ensure_collection(collection))
    try:
        run(store.upsert(collection, [
            point(kb_a, chunk='a' * 64, vector=(1, 0, 0)),
            point(kb_b, chunk='b' * 64, vector=(0, 1, 0)),
        ]))
        assert [hit.knowledge_base_id for hit in run(store.search(
            collection, [1, 0, 0], knowledge_base_ids=frozenset({kb_a})))] == [kb_a]
        assert [hit.knowledge_base_id for hit in run(store.search(
            collection, [1, 0, 0], knowledge_base_ids=frozenset({kb_b})))] == [kb_b]
        both = run(store.search(collection, [1, 0, 0], knowledge_base_ids=frozenset({kb_a, kb_b})))
        assert {hit.knowledge_base_id for hit in both} == {kb_a, kb_b}
        with pytest.raises(VectorStoreError, match='missing_authorized_filter'):
            run(store.search(collection, [1, 0, 0], knowledge_base_ids=frozenset()))
        run(store.delete(collection, ['a' * 64]))
        run(store.delete(collection, ['a' * 64]))
        assert run(store.search(collection, [1, 0, 0], knowledge_base_ids=frozenset({kb_a}))) == []
        assert len(run(store.search(collection, [1, 0, 0], knowledge_base_ids=frozenset({kb_b})))) == 1
    finally:
        run(store.delete_collection(collection))
    with pytest.raises(VectorStoreError, match='index_not_ready'):
        run(store.search(collection, [1, 0, 0], knowledge_base_ids=frozenset({kb_a})))
