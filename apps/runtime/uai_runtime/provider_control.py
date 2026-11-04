"""Provider configuration control plane: validation, hot apply and discovery.

Only administrative references to secrets cross this boundary; values are
resolved in the runtime from the deployment environment or mounted files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from uai_core.capabilities import ModelDefinition
from .egress import EgressError, EgressPolicy
from .provider import ModelProvider, OpenAIProvider
from .providers import OllamaProvider
from .secrets import SecretError, secret_from_env

log = logging.getLogger('uai.runtime.provider')

ProviderKind = Literal['openai-compatible', 'ollama']
ExtraCapability = Literal['tool_calling', 'structured_output']
_SECRET_REF = re.compile(r'^(MODEL_API_KEY|PROVIDER_API_KEY_[A-Z0-9_]{1,63})$')
# Aggregator catalogs include descriptions and pricing alongside model IDs.
_MAX_DISCOVERY_BYTES = 4 * 1024 * 1024
_MAX_DISCOVERY_MODELS = 500

# Only references owned by the provider integration may be resolved here. A
# caller must never be able to point the provider Authorization header at
# INTERNAL_API_KEY or another service secret.
def _valid_secret_ref(value: str) -> bool:
    return value == '' or _SECRET_REF.fullmatch(value) is not None


def _valid_base_url(value: str) -> bool:
    try:
        url = httpx.URL(value)
    except Exception:
        return False
    return (url.scheme in ('http', 'https') and bool(url.host)
            and not url.userinfo and not url.query and not url.fragment)


class ProviderConfigError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ProviderModelInput(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    id: str = Field(min_length=1, max_length=200)
    capabilities: frozenset[ExtraCapability] = frozenset()
    context_window: int | None = Field(default=None, gt=0)

    @field_serializer('capabilities')
    def serialize_capabilities(self, capabilities: frozenset[ExtraCapability]) -> list[str]:
        return sorted(capabilities)


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    revision: int = Field(default=0, ge=0)
    provider: ProviderKind
    base_url: str = Field(min_length=1, max_length=2000)
    api_key_ref: str = Field(default='', max_length=80)
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    models: list[ProviderModelInput] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def validate_configuration(self):
        if not _valid_base_url(self.base_url):
            raise ValueError('invalid_provider_url')
        if not _valid_secret_ref(self.api_key_ref):
            raise ValueError('invalid_api_key_ref')
        if self.provider == 'ollama' and self.api_key_ref:
            raise ValueError('api_key_ref_not_supported')
        seen: set[str] = set()
        for model in self.models:
            if model.id != model.id.strip() or any(c in model.id for c in '\r\n\x00'):
                raise ValueError('invalid_model_id')
            if model.id in seen:
                raise ValueError('duplicate_model_id')
            seen.add(model.id)
            if self.provider == 'ollama' and model.capabilities:
                raise ValueError('capability_not_supported')
        return self


class ProviderDiscoveryConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    provider: ProviderKind
    base_url: str = Field(min_length=1, max_length=2000)
    api_key: str = ''
    api_key_ref: str = Field(default='', max_length=80)

    @model_validator(mode='after')
    def validate_configuration(self):
        if not _valid_base_url(self.base_url):
            raise ValueError('invalid_provider_url')
        if not _valid_secret_ref(self.api_key_ref):
            raise ValueError('invalid_api_key_ref')
        if self.provider == 'ollama' and (self.api_key or self.api_key_ref):
            raise ValueError('api_key_ref_not_supported')
        return self


class ProviderState(BaseModel):
    revision: int
    provider: ProviderKind
    base_url: str
    api_key_ref: str
    api_key_configured: bool
    max_output_tokens: int
    models: list[ModelDefinition]


class ProviderValidation(BaseModel):
    api_key_configured: bool


class ModelDiscovery(BaseModel):
    models: list[str]


@dataclass(frozen=True)
class ActiveProvider:
    provider: ModelProvider
    definitions: Mapping[str, ModelDefinition]
    config: ProviderConfig
    api_key_configured: bool


class ProviderRegistry:
    """Swap provider snapshots atomically; in-flight runs keep their snapshot."""

    def __init__(self, active: ActiveProvider):
        self._active = active
        self._lock = threading.Lock()

    def snapshot(self) -> ActiveProvider:
        return self._active

    def replace(self, active: ActiveProvider) -> ActiveProvider:
        with self._lock:
            if active.config.revision < self._active.config.revision:
                return self._active
            self._active = active
            return active


def resolve_api_key(ref: str) -> tuple[str, bool]:
    if not ref:
        return '', False
    try:
        value = secret_from_env(ref)
    except SecretError as error:
        raise ProviderConfigError(error.code) from None
    return (value or ''), bool(value)


def make_active(config: ProviderConfig, egress: EgressPolicy | None,
                *, transport: httpx.AsyncBaseTransport | None = None) -> ActiveProvider:
    secret, configured = resolve_api_key(config.api_key_ref)
    try:
        if egress is not None:
            egress.require(config.base_url)
    except EgressError as error:
        raise ProviderConfigError(error.code) from None
    try:
        if config.provider == 'ollama':
            provider = OllamaProvider(config.base_url, transport=transport,
                                      max_tokens=config.max_output_tokens)
        else:
            provider = OpenAIProvider(config.base_url, secret, transport=transport,
                                      max_tokens=config.max_output_tokens)
    except ValueError:
        raise ProviderConfigError('invalid_provider_configuration') from None
    definitions = {
        model.id: ModelDefinition(
            id=model.id,
            provider=config.provider,
            capabilities=frozenset({'chat', 'streaming'}) | model.capabilities,
            max_output_tokens=config.max_output_tokens,
            context_window=model.context_window,
        )
        for model in config.models
    }
    return ActiveProvider(provider=provider, definitions=MappingProxyType(definitions),
                          config=config, api_key_configured=configured)


def state_of(active: ActiveProvider) -> ProviderState:
    return ProviderState(
        revision=active.config.revision,
        provider=active.config.provider,
        base_url=active.config.base_url,
        api_key_ref=active.config.api_key_ref,
        api_key_configured=active.api_key_configured,
        max_output_tokens=active.config.max_output_tokens,
        models=[active.definitions[key] for key in sorted(active.definitions)],
    )


async def discover_models(config: ProviderDiscoveryConfig, egress: EgressPolicy | None,
                          *, transport: httpx.AsyncBaseTransport | None = None) -> list[str]:
    secret = config.api_key or resolve_api_key(config.api_key_ref)[0]
    try:
        if egress is not None:
            egress.require(config.base_url)
    except EgressError as error:
        raise ProviderConfigError(error.code) from None
    base = config.base_url.rstrip('/')
    url = f'{base}/models' if config.provider == 'openai-compatible' else f'{base}/api/tags'
    headers = {'Authorization': f'Bearer {secret}'} if secret else {}
    try:
        async with httpx.AsyncClient(transport=transport, timeout=10, trust_env=False,
                                     follow_redirects=False) as client:
            async with client.stream('GET', url, headers=headers) as response:
                if response.status_code != 200:
                    raise ProviderConfigError('provider_models_failed')
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > _MAX_DISCOVERY_BYTES:
                        raise ProviderConfigError('provider_models_too_large')
                    chunks.append(chunk)
    except httpx.HTTPError:
        raise ProviderConfigError('provider_unreachable') from None
    try:
        payload = json.loads(b''.join(chunks))
    except (ValueError, UnicodeDecodeError):
        raise ProviderConfigError('provider_models_invalid') from None
    entries = payload.get('data') if config.provider == 'openai-compatible' else payload.get('models')
    if not isinstance(entries, list):
        raise ProviderConfigError('provider_models_invalid')
    found: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get('id') if config.provider == 'openai-compatible' else entry.get('name', entry.get('model'))
        if not isinstance(value, str) or not 1 <= len(value) <= 200:
            continue
        if value != value.strip() or any(char in value for char in '\r\n\x00'):
            continue
        found.add(value)
        if len(found) >= _MAX_DISCOVERY_MODELS:
            break
    return sorted(found)


async def fetch_desired(gateway_url: str, internal_key: str) -> dict | None:
    headers = {'Authorization': f'Bearer {internal_key}'}
    async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
        response = await client.get(f'{gateway_url.rstrip("/")}/internal/v1/provider/desired',
                                    headers=headers)
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ProviderConfigError('control_plane_unavailable')
    return response.json()


async def notify_applied(gateway_url: str, internal_key: str, revision: int) -> None:
    headers = {'Authorization': f'Bearer {internal_key}'}
    async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
        response = await client.post(f'{gateway_url.rstrip("/")}/internal/v1/provider/applied',
                                     headers=headers, json={'revision': revision})
    if response.status_code not in (200, 204):
        raise ProviderConfigError('control_plane_unavailable')


async def control_loop(app, gateway_url: str, internal_key: str) -> None:
    while True:
        try:
            payload = await fetch_desired(gateway_url, internal_key)
            if payload is not None:
                config = ProviderConfig.model_validate(payload)
                active = app.state.providers.snapshot()
                if config.revision > active.config.revision:
                    app.state.providers.replace(make_active(config, app.state.egress))
                    active = app.state.providers.snapshot()
                if active.config.revision == config.revision and app.state.notified_revision != config.revision:
                    await notify_applied(gateway_url, internal_key, config.revision)
                    app.state.notified_revision = config.revision
        except asyncio.CancelledError:
            raise
        except Exception as error:
            log.warning('provider control reconciliation failed: %s', type(error).__name__)
        await asyncio.sleep(2)
