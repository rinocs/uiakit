"""Explicit outbound allowlist for admin-configured provider/plugin endpoints.

The deployment declares every reachable host and port in
``UAI_EGRESS_ALLOW=host:port,...``. An unset variable keeps the historical
behaviour (no allowlist); an empty value denies every outbound endpoint.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

_DEFAULT_PORTS = {'http': 80, 'https': 443}


class EgressError(ValueError):
    def __init__(self, code: str = 'egress_denied'):
        self.code = code
        super().__init__(code)


def _validate_host(host: str, *, allow_colon: bool = False) -> str:
    host = host.strip().lower().rstrip('.')
    if (not host or len(host) > 253 or host.startswith('-') or host.endswith('-')
            or any(not (char.isalnum() or char in ('.-:' if allow_colon else '.-'))
                   for char in host)):
        raise EgressError('invalid_egress_allowlist')
    return host


def parse_allowlist(raw: str) -> frozenset[tuple[str, int]]:
    entries: set[tuple[str, int]] = set()
    for item in raw.split(','):
        item = item.strip()
        if not item:
            continue
        if item.startswith('['):
            end = item.find(']')
            if end < 0 or item[end + 1:end + 2] != ':':
                raise EgressError('invalid_egress_allowlist')
            host, port_text, allow_colon = item[1:end], item[end + 2:], True
        else:
            host, separator, port_text = item.rpartition(':')
            if not separator:
                raise EgressError('invalid_egress_allowlist')
            allow_colon = False
        if not port_text.isdigit():
            raise EgressError('invalid_egress_allowlist')
        port = int(port_text)
        if not 0 < port < 65536:
            raise EgressError('invalid_egress_allowlist')
        entries.add((_validate_host(host, allow_colon=allow_colon), port))
    return frozenset(entries)


def endpoint(url: str) -> tuple[str, int]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise EgressError('invalid_egress_url') from None
    if (parsed.scheme not in _DEFAULT_PORTS or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise EgressError('invalid_egress_url')
    host = parsed.hostname.lower().rstrip('.')
    return host, port or _DEFAULT_PORTS[parsed.scheme]


class EgressPolicy:
    def __init__(self, allowed: frozenset[tuple[str, int]]):
        self.allowed = allowed

    @classmethod
    def from_env(cls, name: str = 'UAI_EGRESS_ALLOW') -> EgressPolicy | None:
        raw = os.environ.get(name)
        if raw is None:
            return None
        return cls(parse_allowlist(raw))

    def allows(self, url: str) -> bool:
        try:
            return endpoint(url) in self.allowed
        except EgressError:
            return False

    def require(self, url: str) -> str:
        if not self.allows(url):
            raise EgressError('egress_denied')
        return url
