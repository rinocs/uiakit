"""HTTP tool executor behind an administrator-defined connector boundary."""
import json
from collections.abc import AsyncIterable, Callable
from typing import Literal

import httpcore
import httpx
from pydantic import BaseModel, ConfigDict, Field

from uai_core.tools import ToolDefinition, ToolExecutionError
from ..egress import EgressError, EgressPolicy
from .connectors import (ConnectorDefinition, ConnectorID, ConnectorRegistry, ConnectorTargetError,
                         Resolver, resolve_connector_address)


class HTTPToolBinding(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    connector: ConnectorID
    method: Literal['GET', 'HEAD', 'POST']
    path: str = Field(min_length=1, max_length=2000)


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Send the validated address to the socket while preserving the URL host for TLS."""

    def __init__(self, host: str, address: str, *, backend: httpcore.AsyncNetworkBackend | None = None):
        self._host = host
        self._address = address
        self._backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(self, host: str, port: int, timeout: float | None = None,
                          local_address: str | None = None, socket_options=None):
        if host != self._host:
            raise OSError('unexpected_host')
        return await self._backend.connect_tcp(self._address, port, timeout=timeout,
                                               local_address=local_address, socket_options=socket_options)

    async def connect_unix_socket(self, *args, **kwargs):
        raise OSError('unix_socket_disabled')

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _AsyncStream(httpx.AsyncByteStream):
    def __init__(self, stream: AsyncIterable[bytes]):
        self._stream = stream

    async def __aiter__(self):
        async for chunk in self._stream:
            yield chunk

    async def aclose(self) -> None:
        await self._stream.aclose()


class PinnedTransport(httpx.AsyncBaseTransport):
    """Tiny HTTP/1.1 transport with a DNS-pinned network backend and no proxy."""

    def __init__(self, host: str, address: str):
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(), network_backend=PinnedNetworkBackend(host, address),
            http2=False, retries=0, max_connections=1, max_keepalive_connections=0, keepalive_expiry=0)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        core_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(scheme=request.url.raw_scheme, host=request.url.raw_host,
                             port=request.url.port, target=request.url.raw_path),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        response = await self._pool.handle_async_request(core_request)
        return httpx.Response(status_code=response.status, headers=response.headers,
                              stream=_AsyncStream(response.stream), extensions=response.extensions)

    async def aclose(self) -> None:
        await self._pool.aclose()


class HTTPToolExecutor:
    def __init__(self, connectors: ConnectorRegistry, *, resolver: Resolver | None = None,
                 transport_factory: Callable[[str, str], httpx.AsyncBaseTransport] | None = None,
                 egress: EgressPolicy | None = None):
        self._connectors = connectors
        self._resolver = resolver
        self._transport_factory = transport_factory
        self._egress = egress

    def register(self, registry, definition: ToolDefinition, *, binding: HTTPToolBinding,
                 input_model: type[BaseModel], output_model: type[BaseModel]) -> None:
        connector = self._connectors.get(binding.connector)
        expected_permission = f'connector:{binding.connector}'
        connector_permissions = {permission for permission in definition.permissions
                                 if permission.startswith('connector:')}
        if connector_permissions != {expected_permission}:
            raise ValueError('connector_permission_required')
        if binding.method not in connector.methods:
            raise ValueError('connector_method_not_allowed')
        if binding.path not in connector.paths:
            raise ValueError('connector_path_not_allowed')
        if connector.timeout > definition.timeout:
            raise ValueError('connector_timeout_exceeds_tool')
        registry.register(definition, input_model=input_model, output_model=output_model,
                          handler=self._handler(connector, binding))

    def _handler(self, connector: ConnectorDefinition, binding: HTTPToolBinding):
        async def handler(params: BaseModel):
            return await self.execute(connector, binding, params.model_dump(mode='json'))
        return handler

    async def execute(self, connector: ConnectorDefinition, binding: HTTPToolBinding, payload: dict):
        if self._egress is not None:
            try:
                self._egress.require(connector.base_url)
            except EgressError:
                raise ToolExecutionError('connector_forbidden_target') from None
        base_url = httpx.URL(connector.base_url)
        host = base_url.host
        port = base_url.port or (443 if base_url.scheme == 'https' else 80)
        try:
            address = await resolve_connector_address(connector, host, port, resolver=self._resolver)
        except ConnectorTargetError as exc:
            raise ToolExecutionError(exc.code) from None

        try:
            headers = {name: reference.resolve() for name, reference in connector.headers.items()}
        except ConnectorTargetError as exc:
            raise ToolExecutionError(exc.code) from None
        secrets = tuple(headers.values())
        if not any(name.lower() == 'accept' for name in headers):
            headers['Accept'] = 'application/json'

        try:
            params = _query_parameters(payload)
        except ValueError:
            raise ToolExecutionError('connector_invalid_input') from None

        url = base_url.copy_with(path=binding.path)
        transport = (self._transport_factory(host, address) if self._transport_factory is not None
                     else PinnedTransport(host, address))
        try:
            async with httpx.AsyncClient(transport=transport, timeout=connector.timeout,
                                         follow_redirects=False, trust_env=False) as client:
                if binding.method == 'POST':
                    response = await client.request(binding.method, url, json=payload, headers=headers)
                else:
                    response = await client.request(binding.method, url, params=params, headers=headers)
                try:
                    return await _read_response(response, connector.max_response_bytes, secrets,
                                                head=binding.method == 'HEAD')
                finally:
                    await response.aclose()
        except (httpx.TimeoutException, httpcore.TimeoutException):
            raise ToolExecutionError('tool_timeout') from None
        except (httpx.TransportError, httpcore.NetworkError, httpcore.ProtocolError):
            raise ToolExecutionError('connector_unavailable') from None


def _query_parameters(payload: dict) -> list[tuple[str, str]]:
    params: list[tuple[str, str]] = []
    for key, value in payload.items():
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, bool):
                params.append((key, 'true' if item else 'false'))
            elif isinstance(item, (str, int, float)):
                params.append((key, str(item)))
            else:
                raise ValueError('invalid_query_value')
    return params


async def _read_response(response: httpx.Response, limit: int, secrets: tuple[str, ...] = (), *,
                         head: bool = False):
    if not 200 <= response.status_code < 300:
        raise ToolExecutionError('connector_http_error')
    if head:
        return {'status': response.status_code}
    raw_length = response.headers.get('content-length')
    if raw_length is not None:
        try:
            length = int(raw_length)
        except ValueError:
            raise ToolExecutionError('connector_invalid_response') from None
        if length < 0 or length > limit:
            raise ToolExecutionError('connector_response_limit')
    body = bytearray()
    try:
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > limit:
                raise ToolExecutionError('connector_response_limit')
    except httpx.HTTPError:
        raise ToolExecutionError('connector_invalid_response') from None
    if not body:
        return {'status': response.status_code}
    if any(secret.encode() in body for secret in secrets):
        raise ToolExecutionError('connector_secret_leak')
    try:
        return json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ToolExecutionError('connector_invalid_response') from None
