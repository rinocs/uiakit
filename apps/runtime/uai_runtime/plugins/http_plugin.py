"""Host-side HTTP proxy for an isolated plugin; remote code is never imported.

The host-approved manifest is authoritative. The remote service may only expose
metadata and tools that match that manifest; all tools stay read-only, namespaced
and deny-by-default behind the normal ToolPolicyDirective connector allowlist.
"""
import json
import logging
import os
import re
from pathlib import Path
from urllib.parse import quote

import httpx
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict
from uai_core.tools import ToolDefinition, ToolExecutionError
from uai_plugin_sdk.manifest import PluginManifest
from uai_plugin_sdk.plugin import Plugin, PluginHealth

from ..egress import EgressError, EgressPolicy
from ..secrets import secret_from_env

logger = logging.getLogger(__name__)
PROTOCOL_VERSION = 1
PROTOCOL_HEADER = 'X-UAI-Plugin-Protocol'
LOCAL_TOOL = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
SEMVER = re.compile(r'^[0-9]+\.[0-9]+\.[0-9]+$')


class IsolatedConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class IsolatedPluginError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _schema(value, code: str) -> dict:
    if not isinstance(value, dict) or value.get('type') != 'object':
        raise IsolatedPluginError(code)
    try:
        Draft202012Validator.check_schema(value)
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
    except Exception:
        raise IsolatedPluginError(code) from None
    if len(encoded) > 16384:
        raise IsolatedPluginError(code)
    return value


class IsolatedHTTPPlugin(Plugin):
    def __init__(self, manifest: PluginManifest, base_url: str, token: str, *,
                 allowed_connectors: frozenset[str], timeout: float = 5,
                 transport: httpx.AsyncBaseTransport | None = None,
                 egress: EgressPolicy | None = None):
        if manifest.runtime != 'isolated_http':
            raise ValueError('isolated_runtime_required')
        if not isinstance(base_url, str) or not base_url.startswith(('http://', 'https://')):
            raise ValueError('invalid_isolated_endpoint')
        if egress is not None:
            try:
                egress.require(base_url)
            except EgressError:
                raise ValueError('egress_denied') from None
        if not token or len(token) > 512:
            raise ValueError('isolated_token_required')
        connectors = manifest.permissions.network.connectors
        if not connectors or not connectors <= frozenset(allowed_connectors):
            raise ValueError('isolated_connector_not_allowed')
        super().__init__(manifest)
        self._base_url = base_url.rstrip('/')
        self._token = token
        self._connectors = connectors
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._tools = []
        self._prepared = False

    def _client_or_create(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={'Authorization': f'Bearer {self._token}',
                         PROTOCOL_HEADER: str(PROTOCOL_VERSION)},
                timeout=httpx.Timeout(self._timeout),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport)
        return self._client

    async def _request(self, method: str, path: str, body=None):
        try:
            async with self._client_or_create().stream(method, path, json=body) as response:
                if response.status_code == 401:
                    raise IsolatedPluginError('plugin_auth_failed')
                if response.status_code not in (200, 204):
                    raise IsolatedPluginError('plugin_protocol_error')
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > 262144:
                        raise IsolatedPluginError('plugin_response_limit')
                    chunks.extend(chunk)
                if response.status_code == 204:
                    return None
        except (httpx.HTTPError, TimeoutError, OSError):
            raise IsolatedPluginError('plugin_unavailable') from None
        try:
            data = json.loads(chunks)
        except (ValueError, TypeError):
            raise IsolatedPluginError('plugin_protocol_error') from None
        if not isinstance(data, dict) or data.get('protocol') != PROTOCOL_VERSION:
            raise IsolatedPluginError('plugin_protocol_mismatch')
        return data

    async def prepare(self) -> None:
        data = await self._request('GET', '/v1/manifest')
        remote = PluginManifest.model_validate(data.get('manifest'))
        if (remote.id, remote.version, remote.runtime, remote.capabilities,
                remote.permissions.network.connectors) != (
                self.manifest.id, self.manifest.version, self.manifest.runtime,
                self.manifest.capabilities, self.manifest.permissions.network.connectors):
            raise IsolatedPluginError('plugin_manifest_mismatch')
        catalog = await self._request('GET', '/v1/tools')
        entries = catalog.get('tools')
        if not isinstance(entries, list) or len(entries) > 64:
            raise IsolatedPluginError('plugin_tool_catalog_invalid')
        self._tools = [self._tool(entry) for entry in entries]
        if len({item['definition'].id for item in self._tools}) != len(self._tools):
            raise IsolatedPluginError('plugin_tool_catalog_invalid')
        self._prepared = True

    def _tool(self, entry) -> dict:
        if not isinstance(entry, dict):
            raise IsolatedPluginError('plugin_tool_catalog_invalid')
        local = entry.get('id')
        if not isinstance(local, str) or not LOCAL_TOOL.fullmatch(local):
            raise IsolatedPluginError('plugin_tool_catalog_invalid')
        connector = entry.get('connector')
        if connector is None and len(self._connectors) == 1:
            connector = next(iter(self._connectors))
        if connector not in self._connectors:
            raise IsolatedPluginError('plugin_connector_not_declared')
        version = entry.get('version')
        name = entry.get('name')
        description = entry.get('description', '')
        timeout = entry.get('timeout', 5)
        if (not isinstance(version, str) or not SEMVER.fullmatch(version)
                or not isinstance(name, str) or not 1 <= len(name) <= 200
                or not isinstance(description, str) or len(description) > 4000
                or type(timeout) not in (int, float) or not 0 < timeout <= 30):
            raise IsolatedPluginError('plugin_tool_catalog_invalid')
        definition = ToolDefinition(
            id=f'{self.manifest.id}.{local}', name=name, description=description,
            version=version, input_schema=_schema(entry.get('input_schema'),
                                                  'plugin_tool_schema_invalid'),
            output_schema=_schema(entry.get('output_schema'), 'plugin_tool_schema_invalid'),
            permissions={'tools:execute', f'connector:{connector}'},
            risk_level='read_only', timeout=timeout, retry_policy='never', executor='isolated')
        return {'local': local, 'definition': definition}

    def register(self, registrar) -> None:
        if not self._prepared:
            raise ValueError('plugin_not_prepared')
        for item in self._tools:
            async def handler(params, local=item['local']):
                return await self._execute(local, params)
            registrar.add_tool(item['definition'], handler=handler)

    async def activate(self, config) -> None:
        await self._request('POST', '/v1/activate', {'config': config})

    async def deactivate(self) -> None:
        try:
            await self._request('POST', '/v1/deactivate', {})
        except IsolatedPluginError:
            logger.warning('plugin_failed plugin_id=%s phase=deactivate', self.manifest.id)
        finally:
            self._prepared = False
            if self._client is not None:
                await self._client.aclose()
                self._client = None

    async def health(self) -> PluginHealth:
        try:
            data = await self._request('GET', '/v1/health')
        except IsolatedPluginError:
            return PluginHealth(status='unavailable')
        return PluginHealth(status='ok' if data.get('status') == 'ok' else 'degraded')

    async def _execute(self, local: str, params):
        try:
            data = await self._request('POST', f'/v1/tools/{quote(local, safe="")}/execute',
                                       {'arguments': params})
        except IsolatedPluginError as exc:
            raise ToolExecutionError(exc.code) from None
        if 'result' not in data:
            raise ToolExecutionError('plugin_protocol_error')
        return data['result']


def isolated_plugin_from_env(allowed_connectors: frozenset[str], *,
                             egress: EgressPolicy | None = None):
    base_url = os.environ.get('ISOLATED_PLUGIN_URL', '').strip()
    if not base_url:
        return None
    token = secret_from_env('ISOLATED_PLUGIN_TOKEN') or ''
    manifest_source = os.environ.get('ISOLATED_PLUGIN_MANIFEST', '').strip()
    if not token or not manifest_source:
        raise ValueError('isolated_plugin_configuration_required')
    try:
        raw = Path(manifest_source).read_text()
    except OSError:
        raw = manifest_source
    manifest = PluginManifest.model_validate_json(raw)
    return IsolatedHTTPPlugin(manifest, base_url, token,
                              allowed_connectors=allowed_connectors, egress=egress)
