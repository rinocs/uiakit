"""Administrator-owned HTTP connectors and fail-closed target validation."""
import asyncio
import inspect
import ipaddress
import os
import socket
from collections.abc import Awaitable, Callable, Iterable
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..secrets import SecretError, read_secret_file

ConnectorID = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,99}$')]
HeaderName = Annotated[str, Field(pattern=r'^[A-Za-z0-9-]{1,64}$')]
Resolver = Callable[[str, int], Awaitable[list[str]] | list[str]]

_FORBIDDEN_HEADERS = {'host', 'content-length', 'transfer-encoding', 'connection', 'proxy-authorization',
                      'proxy-authenticate', 'te', 'trailer', 'upgrade'}
_METADATA_ADDRESSES = frozenset({'169.254.169.254', 'fd00:ec2::254', 'fd20:ce::254', '100.100.100.200'})
_TRANSITION_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                             ('64:ff9b::/96', '64:ff9b:1::/48', '2002::/16', '2001::/32'))


class ConnectorTargetError(Exception):
    def __init__(self, code: str = 'connector_forbidden_target'):
        self.code = code
        super().__init__(code)


class SecretRef(BaseModel):
    """Only references are persisted; header values are resolved at request time."""
    model_config = ConfigDict(extra='forbid', frozen=True)
    env: str | None = Field(default=None, pattern=r'^[A-Z][A-Z0-9_]{0,127}$')
    file: str | None = Field(default=None, min_length=1, max_length=1024)

    @model_validator(mode='after')
    def exactly_one_source(self) -> "SecretRef":
        if (self.env is None) == (self.file is None):
            raise ValueError('secret_reference_requires_one_source')
        return self

    def resolve(self) -> str:
        if self.file is not None:
            try:
                return read_secret_file(self.file)
            except SecretError as exc:
                code = ('connector_secret_missing'
                        if exc.code in ('secret_file_unreadable', 'missing_secret')
                        else 'connector_secret_invalid')
                raise ConnectorTargetError(code) from None
        try:
            value = os.environ[self.env]
        except KeyError:
            raise ConnectorTargetError('connector_secret_missing') from None
        if not value or len(value) > 8192 or any(char in '\r\n\x00' for char in value):
            raise ConnectorTargetError('connector_secret_invalid')
        return value


class ConnectorDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    id: ConnectorID
    base_url: str
    methods: frozenset[Literal['GET', 'HEAD', 'POST']] = Field(default_factory=lambda: frozenset({'GET'}),
                                                              min_length=1, max_length=3)
    paths: tuple[str, ...] = Field(min_length=1, max_length=32)
    headers: dict[HeaderName, SecretRef] = Field(default_factory=dict, max_length=16)
    timeout: float = Field(default=5, gt=0, le=30)
    max_response_bytes: int = Field(default=65536, gt=0, le=1048576)
    retry_policy: Literal['never'] = 'never'
    private_networks: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            raise ValueError('invalid_connector_url') from None
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or port is not None and not 0 < port < 65536
                or any(char.isspace() or ord(char) < 32 for char in value)):
            raise ValueError('invalid_connector_url')
        return value.rstrip('/')

    @field_validator('paths')
    @classmethod
    def validate_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError('duplicate_connector_path')
        for path in values:
            if (not path.startswith('/') or path.startswith('//') or '..' in path or '\\' in path
                    or '?' in path or '#' in path or '{' in path or '}' in path
                    or len(path) > 2000 or any(char.isspace() or ord(char) < 32 for char in path)):
                raise ValueError('invalid_connector_path')
        return values

    @field_validator('headers')
    @classmethod
    def validate_headers(cls, values: dict[str, SecretRef]) -> dict[str, SecretRef]:
        seen = set()
        for name in values:
            if name.lower() in _FORBIDDEN_HEADERS or name.lower() in seen:
                raise ValueError('invalid_connector_header')
            seen.add(name.lower())
        return values

    @field_validator('private_networks')
    @classmethod
    def validate_private_networks(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            try:
                network = ipaddress.ip_network(value, strict=False)
            except ValueError:
                raise ValueError('invalid_private_network') from None
            if (network.is_loopback or network.is_link_local or network.is_multicast
                    or network.is_unspecified or network.is_reserved):
                raise ValueError('invalid_private_network')
        return values


class ConnectorRegistry:
    def __init__(self, connectors: Iterable[ConnectorDefinition] = ()):
        self._connectors: dict[str, ConnectorDefinition] = {}
        for connector in connectors:
            if connector.id in self._connectors:
                raise ValueError('duplicate_connector')
            self._connectors[connector.id] = connector

    def get(self, connector_id: str) -> ConnectorDefinition:
        try:
            return self._connectors[connector_id]
        except KeyError:
            raise ValueError('unknown_connector') from None

    def __len__(self) -> int:
        return len(self._connectors)


def validate_connector_address(address: str, private_networks: Iterable[str] = ()) -> str:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        raise ConnectorTargetError('connector_dns_error') from None
    mapped = getattr(parsed, 'ipv4_mapped', None)
    if mapped is not None:
        parsed = mapped
    if (parsed.is_loopback or parsed.is_link_local or parsed.is_multicast
            or parsed.is_unspecified or parsed.is_reserved or str(parsed) in _METADATA_ADDRESSES
            or any(parsed in network for network in _TRANSITION_NETWORKS)):
        raise ConnectorTargetError()
    if parsed.is_global:
        return str(parsed)
    if any(parsed in ipaddress.ip_network(network, strict=False) for network in private_networks):
        return str(parsed)
    raise ConnectorTargetError()


async def resolve_connector_address(connector: ConnectorDefinition, host: str, port: int, *,
                                    resolver: Resolver | None = None) -> str:
    async def default_resolver(name: str, target_port: int) -> list[str]:
        infos = await asyncio.get_running_loop().getaddrinfo(name, target_port, type=socket.SOCK_STREAM)
        return [info[4][0] for info in infos]

    try:
        resolve = resolver or default_resolver
        result = resolve(host, port)
        addresses = await result if inspect.isawaitable(result) else result
    except OSError:
        raise ConnectorTargetError('connector_dns_error') from None
    addresses = list(dict.fromkeys(str(address) for address in addresses))
    if not addresses:
        raise ConnectorTargetError('connector_dns_error')
    # Validate every answer before choosing one: a mixed DNS response must not
    # let a later connection race to an internal address.
    validated = [validate_connector_address(address, connector.private_networks) for address in addresses]
    return validated[0]
