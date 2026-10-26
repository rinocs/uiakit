import asyncio

import httpx

from uai_runtime.app import create_app
from uai_runtime.provider import OpenAIProvider
from uai_runtime.storage.filesystem import FilesystemBlobStore


def request(app, method, path, body=None, key='internal-secret'):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url='http://runtime') as client:
            headers = {'Authorization': 'Bearer ' + key} if key else {}
            return await client.request(method, path, content=body, headers=headers)
    return asyncio.run(send())


def app_with(store):
    return create_app('internal-secret', OpenAIProvider('http://provider/v1', ''),
                      blob_store=store)


def test_internal_storage_roundtrip_requires_auth_and_valid_key(tmp_path):
    app = app_with(FilesystemBlobStore(tmp_path))
    assert request(app, 'PUT', '/internal/v1/storage/documents/a', b'data', key='').status_code == 401
    assert request(app, 'PUT', '/internal/v1/storage/documents/a', b'data').status_code == 204
    assert request(app, 'GET', '/internal/v1/storage/documents/a').content == b'data'
    assert request(app, 'DELETE', '/internal/v1/storage/documents/a').status_code == 204
    assert request(app, 'GET', '/internal/v1/storage/documents/a').status_code == 404
    assert request(app, 'DELETE', '/internal/v1/storage/documents/a').status_code == 204
    assert request(app, 'PUT', '/internal/v1/storage/bad!', b'data').status_code == 422


def test_internal_storage_unavailable_without_adapter():
    app = create_app('internal-secret', OpenAIProvider('http://provider/v1', ''))
    assert request(app, 'PUT', '/internal/v1/storage/documents/a', b'data').status_code == 503
    assert request(app, 'GET', '/internal/v1/storage/documents/a').status_code == 503
    assert request(app, 'DELETE', '/internal/v1/storage/documents/a').status_code == 503
