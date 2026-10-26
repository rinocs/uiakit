"""Secret values from environment variables or mounted files.

Only the reference is configuration; values are never logged. ``NAME_FILE``
takes precedence over a missing ``NAME`` and both set is an error so a
misconfigured deployment cannot silently use the wrong source.
"""
from __future__ import annotations

import os
import re

_NAME = re.compile(r'^[A-Z][A-Z0-9_]{0,127}$')
_MAX_SECRET_BYTES = 65536
_MAX_SECRET_CHARS = 8192


class SecretError(ValueError):
    """Invalid, missing or ambiguous secret configuration."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise SecretError('invalid_secret_name')


def _clean(value: str) -> str:
    if value.endswith('\n'):
        value = value[:-1]
    if value.endswith('\r'):
        value = value[:-1]
    if (not value or len(value) > _MAX_SECRET_CHARS
            or any(char in '\r\n\x00' for char in value)):
        raise SecretError('invalid_secret_value')
    return value


def read_secret_file(path: str) -> str:
    """Read a mounted secret with a single trailing newline allowed."""
    if (not isinstance(path, str) or not path.startswith('/')
            or len(path) > 1024 or any(char.isspace() or ord(char) < 32 for char in path)):
        raise SecretError('invalid_secret_file')
    try:
        with open(path, 'rb') as handle:
            data = handle.read(_MAX_SECRET_BYTES + 1)
    except OSError:
        raise SecretError('secret_file_unreadable') from None
    if len(data) > _MAX_SECRET_BYTES:
        raise SecretError('secret_file_too_large')
    try:
        return _clean(data.decode('utf-8'))
    except UnicodeDecodeError:
        raise SecretError('secret_file_invalid') from None


def secret_from_env(name: str, *, required: bool = False) -> str | None:
    """Resolve ``NAME`` or ``NAME_FILE``; never returns a raw file path."""
    _validate_name(name)
    value = os.environ.get(name) or None
    path = os.environ.get(name + '_FILE') or None
    if value is not None and path is not None:
        raise SecretError('ambiguous_secret_source')
    if path is not None:
        return read_secret_file(path)
    if value is None:
        if required:
            raise SecretError('missing_secret')
        return None
    return _clean(value)
