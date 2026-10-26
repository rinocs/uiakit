"""Optional S3-compatible blob store. Credentials come from host config/secret refs."""
import asyncio
import os

from uai_core.storage import BlobNotFound, BlobStoreError, BlobStoreUnavailable, validate_blob_key
from ..secrets import secret_from_env


class S3BlobStore:
    def __init__(self, *, bucket: str, client=None, prefix: str = '', endpoint_url: str | None = None,
                 region: str = 'us-east-1', access_key: str | None = None,
                 secret_key: str | None = None):
        if not bucket or len(bucket) > 255:
            raise ValueError('invalid_s3_bucket')
        if prefix:
            validate_blob_key(prefix)
        if client is None:
            try:
                import boto3
            except ImportError:
                raise BlobStoreUnavailable('s3_dependency_missing') from None
            kwargs = {'region_name': region}
            if endpoint_url:
                kwargs['endpoint_url'] = endpoint_url
            if access_key is not None or secret_key is not None:
                if not access_key or not secret_key:
                    raise ValueError('invalid_s3_credentials')
                kwargs['aws_access_key_id'] = access_key
                kwargs['aws_secret_access_key'] = secret_key
            client = boto3.client('s3', **kwargs)
        self._client = client
        self._bucket = bucket
        self._prefix = prefix

    def __repr__(self):
        return f'S3BlobStore(bucket={self._bucket!r}, prefix={self._prefix!r})'

    def _key(self, key: str) -> str:
        validate_blob_key(key)
        return f'{self._prefix}/{key}' if self._prefix else key

    def _put(self, key: str, data: bytes) -> None:
        mapped = self._key(key)
        try:
            self._client.put_object(Bucket=self._bucket, Key=mapped, Body=data,
                                    ContentLength=len(data),
                                    ContentType='application/octet-stream')
        except Exception:
            raise BlobStoreError('s3_write_failed') from None

    def _get(self, key: str) -> bytes:
        mapped = self._key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=mapped)
            return response['Body'].read()
        except Exception as error:
            code = str(getattr(error, 'response', {}).get('Error', {}).get('Code', ''))
            if code in ('NoSuchKey', 'NotFound', '404'):
                raise BlobNotFound('blob_not_found') from None
            raise BlobStoreError('s3_read_failed') from None

    def _delete(self, key: str) -> None:
        mapped = self._key(key)
        try:
            self._client.delete_object(Bucket=self._bucket, Key=mapped)
        except Exception as error:
            code = str(getattr(error, 'response', {}).get('Error', {}).get('Code', ''))
            if code in ('NoSuchKey', 'NotFound', '404'):
                return
            raise BlobStoreError('s3_delete_failed') from None

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._put, key, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete, key)

    @classmethod
    def from_env(cls):
        bucket = os.environ.get('UAI_S3_BUCKET', '')
        if not bucket:
            raise ValueError('invalid_s3_bucket')
        access = secret_from_env('UAI_S3_ACCESS_KEY')
        secret = secret_from_env('UAI_S3_SECRET_KEY')
        if (access is None) != (secret is None):
            raise ValueError('invalid_s3_credentials')
        return cls(bucket=bucket, prefix=os.environ.get('UAI_S3_PREFIX', ''),
                   endpoint_url=os.environ.get('UAI_S3_ENDPOINT') or None,
                   region=os.environ.get('UAI_S3_REGION', 'us-east-1'),
                   access_key=access, secret_key=secret)
