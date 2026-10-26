"""Qdrant REST adapter with mandatory server-side knowledge-base filters."""
import math
import uuid

import httpx

from uai_core.vector_store import (VectorHit, VectorPoint, VectorStoreError, collection_for,
                                   validate_collection_name, validate_delete_ids, validate_points,
                                   validate_search, validate_vector)

_MAX_RESPONSE = 8 * 1024 * 1024
_NAMESPACE = uuid.UUID('6ba7b811-9dad-11d1-80b4-00c04fd430c8')


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, 'uai-chunk:' + chunk_id))


class QdrantVectorStore:
    def __init__(self, base_url: str, dimension: int, *, api_key: str = '', timeout: float = 30,
                 transport: httpx.AsyncBaseTransport | None = None):
        url = httpx.URL(base_url)
        if url.scheme not in ('http', 'https') or not url.host or url.userinfo:
            raise ValueError('invalid_qdrant_url')
        if type(dimension) is not int or not 1 <= dimension <= 8192:
            raise ValueError('invalid_qdrant_dimension')
        self._base_url = base_url.rstrip('/')
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport
        self.dimension = dimension

    async def _request(self, method: str, path: str, body=None, *, allowed=(200,)):
        headers = {'api-key': self._api_key} if self._api_key else {}
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout,
                                         trust_env=False, follow_redirects=False) as client:
                response = await client.request(method, self._base_url + path, headers=headers, json=body)
        except (httpx.TimeoutException, httpx.TransportError):
            raise VectorStoreError('vector_store_unavailable') from None
        if response.status_code == 404 and 404 in allowed:
            return None
        if response.status_code not in allowed:
            if response.status_code == 404:
                raise VectorStoreError('collection_missing')
            raise VectorStoreError('vector_store_unavailable')
        if len(response.content) > _MAX_RESPONSE:
            raise VectorStoreError('vector_store_response_too_large')
        if not response.content:
            return None
        try:
            data = response.json()
        except ValueError:
            raise VectorStoreError('invalid_vector_store_response') from None
        if not isinstance(data, dict):
            raise VectorStoreError('invalid_vector_store_response')
        return data

    async def ensure_collection(self, collection: str) -> None:
        validate_collection_name(collection)
        try:
            data = await self._request('GET', f'/collections/{collection}', allowed=(200, 404))
        except VectorStoreError:
            raise
        if data is not None:
            try:
                config = data['result']['config']['params']['vectors']
                size = config['size'] if isinstance(config, dict) else None
            except (KeyError, TypeError):
                raise VectorStoreError('invalid_vector_store_response') from None
            if size != self.dimension:
                raise VectorStoreError('collection_dimension_mismatch')
            return
        await self._request('PUT', f'/collections/{collection}',
                            {'vectors': {'size': self.dimension, 'distance': 'Cosine'}})

    async def upsert(self, collection: str, points) -> None:
        validate_collection_name(collection)
        clean = validate_points(points, self.dimension)
        await self.ensure_collection(collection)
        body = {'points': [{
            'id': _point_id(point.chunk_id),
            'vector': list(point.vector),
            'payload': {
                'chunk_id': point.chunk_id,
                'knowledge_base_id': point.knowledge_base_id,
                'document_id': point.document_id,
                'document_hash': point.document_hash,
                'document_version': point.document_version,
                'page': point.page,
                'start': point.start,
                'end': point.end,
                'text': point.text,
            },
        } for point in clean]}
        await self._request('PUT', f'/collections/{collection}/points?wait=true', body)

    async def search(self, collection: str, vector, *, knowledge_base_ids, limit: int = 10):
        values, allowed = validate_search(collection, vector, self.dimension, knowledge_base_ids, limit)
        try:
            data = await self._request('POST', f'/collections/{collection}/points/search', {
                'vector': list(values), 'limit': limit, 'with_payload': True,
                'filter': {'must': [{'key': 'knowledge_base_id', 'match': {'any': list(allowed)}}]},
            })
        except VectorStoreError as error:
            if str(error) == 'collection_missing':
                raise VectorStoreError('index_not_ready') from None
            raise
        results = data.get('result')
        if not isinstance(results, list):
            raise VectorStoreError('invalid_vector_store_response')
        hits = []
        for item in results:
            try:
                payload = item['payload']
                score = item['score']
                hit = VectorHit(
                    chunk_id=payload['chunk_id'], score=float(score),
                    knowledge_base_id=payload['knowledge_base_id'], document_id=payload['document_id'],
                    document_hash=payload['document_hash'], document_version=payload['document_version'],
                    page=payload['page'], start=payload['start'], end=payload['end'], text=payload['text'])
            except (KeyError, TypeError, ValueError):
                raise VectorStoreError('invalid_vector_store_response') from None
            if (not math.isfinite(hit.score) or hit.knowledge_base_id not in allowed
                    or len(hit.text) != hit.end - hit.start):
                raise VectorStoreError('invalid_vector_store_response')
            hits.append(hit)
        return hits

    async def delete(self, collection: str, chunk_ids) -> None:
        validate_collection_name(collection)
        clean = validate_delete_ids(chunk_ids)
        if not clean:
            return
        try:
            await self._request('POST', f'/collections/{collection}/points/delete?wait=true',
                                {'points': [_point_id(chunk_id) for chunk_id in clean]})
        except VectorStoreError as error:
            if str(error) == 'collection_missing':
                return
            raise

    async def delete_collection(self, collection: str) -> None:
        validate_collection_name(collection)
        try:
            await self._request('DELETE', f'/collections/{collection}')
        except VectorStoreError as error:
            if str(error) == 'collection_missing':
                return
            raise


__all__ = ['QdrantVectorStore', 'collection_for']
