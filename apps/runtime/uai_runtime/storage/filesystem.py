"""Filesystem blob store with server-owned keys and atomic publication."""
import asyncio
import errno
import os
import stat
from pathlib import Path
from uuid import uuid4

from uai_core.storage import BlobNotFound, BlobStoreError, validate_blob_key

_O_NOFOLLOW = getattr(os, 'O_NOFOLLOW', 0)


class FilesystemBlobStore:
    def __init__(self, root: str | os.PathLike[str]):
        path = Path(root).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass
        if not path.is_dir():
            raise ValueError('invalid_blob_root')
        self._root = path.resolve()

    def _path(self, key: str) -> Path:
        validate_blob_key(key)
        candidate = self._root.joinpath(*key.split('/'))
        parent = candidate.parent.resolve()
        if parent != self._root and self._root not in parent.parents:
            raise ValueError('invalid_blob_path')
        return candidate

    def _put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        # Re-check after directory creation: a linked parent must not escape root.
        resolved = parent.resolve()
        if resolved != self._root and self._root not in resolved.parents:
            raise ValueError('invalid_blob_path')
        temporary = parent / f'.tmp-{uuid4().hex}'
        fd = None
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                fd = None
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            dir_fd = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except BaseException:
            if fd is not None:
                os.close(fd)
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
            raise

    def _get(self, key: str) -> bytes:
        path = self._path(key)
        try:
            fd = os.open(path, os.O_RDONLY | _O_NOFOLLOW)
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
                raise BlobNotFound('blob_not_found') from None
            raise BlobStoreError('blob_read_failed') from None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise BlobNotFound('blob_not_found')
            with os.fdopen(fd, 'rb') as stream:
                fd = None
                return stream.read()
        finally:
            if fd is not None:
                os.close(fd)

    def _delete(self, key: str) -> None:
        path = self._path(key)
        try:
            os.unlink(path)
        except FileNotFoundError:
            return
        except IsADirectoryError:
            raise BlobStoreError('blob_delete_failed') from None
        except OSError:
            raise BlobStoreError('blob_delete_failed') from None

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self._put, key, data)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete, key)
