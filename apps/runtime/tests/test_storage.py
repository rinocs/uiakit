import asyncio
import errno
import os
from pathlib import Path

import pytest

from uai_core.storage import BlobNotFound, new_blob_key, validate_blob_key
from uai_runtime.storage.filesystem import FilesystemBlobStore
from uai_runtime.storage.s3 import S3BlobStore


def run(coro):
    return asyncio.run(coro)


def test_server_generated_keys_and_validation():
    key = new_blob_key('documents/kb-1')
    assert key.startswith('documents/kb-1/') and len(key.split('/')) == 3
    assert key != new_blob_key('documents/kb-1')
    assert validate_blob_key(key) == key
    for bad in ('', '/abs', '../x', 'a//b', 'a/./b', 'a/../b', 'a\\b', 'C:/x',
                '.hidden', 'a/.tmp', 'a/' + 'x' * 65, 'a/b/c/d/e/f/g/h/i', 'a\x00b'):
        with pytest.raises(ValueError):
            validate_blob_key(bad)
    with pytest.raises(ValueError):
        new_blob_key('../escape')


def test_filesystem_roundtrip_persistence_and_idempotent_delete(tmp_path):
    store = FilesystemBlobStore(tmp_path)
    key = new_blob_key()
    run(store.put(key, b'hello'))
    assert run(store.get(key)) == b'hello'
    assert run(FilesystemBlobStore(tmp_path).get(key)) == b'hello'
    run(store.delete(key))
    run(store.delete(key))
    with pytest.raises(BlobNotFound):
        run(store.get(key))


def test_filesystem_rejects_traversal_absolute_and_symlink_parents(tmp_path):
    root, outside = tmp_path / 'root', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    store = FilesystemBlobStore(root)
    for bad in ('../x', '/etc/passwd', 'a//b', 'a/./b', 'a\\b', 'C:/x'):
        with pytest.raises(ValueError):
            run(store.put(bad, b'x'))
    (root / 'linkdir').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        run(store.put('linkdir/x', b'nope'))
    assert not (outside / 'x').exists()


def test_filesystem_does_not_follow_final_symlink(tmp_path):
    root, outside = tmp_path / 'root', tmp_path / 'outside'
    root.mkdir()
    outside.write_bytes(b'secret')
    (root / 'link').symlink_to(outside)
    store = FilesystemBlobStore(root)
    with pytest.raises(BlobNotFound):
        run(store.get('link'))
    run(store.put('link', b'replaced'))
    assert outside.read_bytes() == b'secret'
    assert run(store.get('link')) == b'replaced'


def test_filesystem_partial_write_is_not_visible(tmp_path, monkeypatch):
    store = FilesystemBlobStore(tmp_path)
    key = new_blob_key()

    def fail(*args, **kwargs):
        raise OSError(errno.ENOSPC, 'full')

    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError):
        run(store.put(key, b'partial'))
    monkeypatch.undo()
    with pytest.raises(BlobNotFound):
        run(store.get(key))
    assert not list(Path(tmp_path).rglob('.tmp-*'))


class FakeBody:
    def __init__(self, data):
        self._data = data

    def read(self):
        return self._data


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(('put', kwargs['Key']))
        self.objects[kwargs['Key']] = kwargs['Body']

    def get_object(self, **kwargs):
        self.calls.append(('get', kwargs['Key']))
        if kwargs['Key'] not in self.objects:
            error = Exception('missing')
            error.response = {'Error': {'Code': 'NoSuchKey'}}
            raise error
        return {'Body': FakeBody(self.objects[kwargs['Key']])}

    def delete_object(self, **kwargs):
        self.calls.append(('delete', kwargs['Key']))
        self.objects.pop(kwargs['Key'], None)


def test_s3_adapter_put_get_delete_prefix_and_not_found():
    client = FakeS3()
    store = S3BlobStore(client=client, bucket='bucket', prefix='documents')
    key = new_blob_key('kb-1')
    mapped = 'documents/' + key
    run(store.put(key, b'data'))
    assert client.objects[mapped] == b'data'
    assert run(store.get(key)) == b'data'
    run(store.delete(key))
    run(store.delete(key))
    with pytest.raises(BlobNotFound):
        run(store.get(key))
    with pytest.raises(ValueError):
        run(store.put('../escape', b'x'))
    assert 'secret' not in repr(S3BlobStore(client=client, bucket='b', secret_key='secret'))


def test_s3_from_env_requires_bucket_and_key_pair(monkeypatch):
    monkeypatch.delenv('UAI_S3_BUCKET', raising=False)
    with pytest.raises(ValueError):
        S3BlobStore.from_env()
    monkeypatch.setenv('UAI_S3_BUCKET', 'bucket')
    monkeypatch.setenv('UAI_S3_ACCESS_KEY', 'only-access')
    monkeypatch.delenv('UAI_S3_SECRET_KEY', raising=False)
    with pytest.raises(ValueError):
        S3BlobStore.from_env()


@pytest.mark.skipif(not os.environ.get('UAI_S3_TEST_ENDPOINT'), reason='S3-compatible endpoint not configured')
def test_s3_compatible_roundtrip():
    import boto3
    from botocore.exceptions import ClientError

    endpoint = os.environ['UAI_S3_TEST_ENDPOINT']
    bucket = os.environ.get('UAI_S3_TEST_BUCKET', 'uai-storage-test')
    access = os.environ.get('UAI_S3_TEST_ACCESS_KEY', 'uai-minio')
    secret = os.environ.get('UAI_S3_TEST_SECRET_KEY', 'uai-minio-test')
    client = boto3.client('s3', endpoint_url=endpoint, region_name='us-east-1',
                          aws_access_key_id=access, aws_secret_access_key=secret)
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as error:
        if error.response['Error']['Code'] not in ('BucketAlreadyOwnedByYou', 'BucketAlreadyExists'):
            raise
    store = S3BlobStore(client=client, bucket=bucket, prefix='documents')
    key = new_blob_key('kb')
    run(store.put(key, b'minio-data'))
    assert run(store.get(key)) == b'minio-data'
    run(store.delete(key))
    run(store.delete(key))
    with pytest.raises(BlobNotFound):
        run(store.get(key))
