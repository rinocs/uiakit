"""Blob storage contracts. Adapters own persistence; keys are server-generated."""
import re
from typing import Protocol
from uuid import uuid4

_COMPONENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
_MAX_COMPONENTS = 8
_MAX_KEY_LENGTH = 512


class BlobStoreError(Exception):
    """Safe storage failure; details never include keys, paths or credentials."""


class BlobStoreUnavailable(BlobStoreError):
    """Optional storage backend is not installed or not configured."""


class BlobNotFound(BlobStoreError):
    """The blob does not exist (or is not a regular, authorized file)."""


def validate_blob_key(key: str) -> str:
    """Reject absolute paths, traversal, hidden names and unsafe components."""
    if not isinstance(key, str) or not key or len(key) > _MAX_KEY_LENGTH:
        raise ValueError('invalid_blob_key')
    if '\x00' in key or '\\' in key:
        raise ValueError('invalid_blob_key')
    parts = key.split('/')
    if len(parts) > _MAX_COMPONENTS or any(not _COMPONENT.fullmatch(part) for part in parts):
        raise ValueError('invalid_blob_key')
    return key


def new_blob_key(prefix: str = 'documents') -> str:
    """Generate a server-owned key; callers must not accept it from model output."""
    validate_blob_key(prefix)
    if len(prefix.split('/')) >= _MAX_COMPONENTS:
        raise ValueError('invalid_blob_key')
    return f'{prefix}/{uuid4().hex}'


class BlobStore(Protocol):
    async def put(self, key: str, data: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...
