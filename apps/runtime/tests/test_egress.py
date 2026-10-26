import pytest

from uai_runtime.egress import EgressError, EgressPolicy, endpoint, parse_allowlist


def test_unset_policy_is_disabled(monkeypatch):
    monkeypatch.delenv('UAI_EGRESS_ALLOW', raising=False)
    assert EgressPolicy.from_env() is None


def test_empty_policy_denies_everything(monkeypatch):
    monkeypatch.setenv('UAI_EGRESS_ALLOW', '')
    policy = EgressPolicy.from_env()
    assert policy is not None
    assert not policy.allows('https://api.example.test/v1')
    with pytest.raises(EgressError, match='egress_denied'):
        policy.require('https://api.example.test/v1')


def test_allowed_host_and_port(monkeypatch):
    monkeypatch.setenv('UAI_EGRESS_ALLOW', 'api.example.test:8443, [2001:db8::1]:443')
    policy = EgressPolicy.from_env()
    assert policy.allows('https://api.example.test:8443/v1/chat/completions')
    assert policy.allows('https://[2001:db8::1]/v1')
    assert not policy.allows('https://api.example.test/v1')
    assert not policy.allows('https://other.example.test:8443/v1')


def test_default_ports_are_normalized():
    assert endpoint('https://api.example.test/v1') == ('api.example.test', 443)
    assert endpoint('http://api.example.test/v1') == ('api.example.test', 80)
    assert endpoint('https://API.Example.Test./v1') == ('api.example.test', 443)


@pytest.mark.parametrize('raw', [
    'api.example.test', 'https://api.example.test:443', 'api.example.test:0',
    'api.example.test:70000', 'api.example.test:abc', '*.example.test:443',
    'api.example.test:443/path', 'api.example.test:443:444', '[::1]',
])
def test_invalid_allowlists(raw):
    with pytest.raises(EgressError):
        parse_allowlist(raw)


@pytest.mark.parametrize('url', [
    'ftp://api.example.test:21', 'https://user:pass@api.example.test',
    'https://api.example.test:99999', 'not-a-url', 'https:///path',
])
def test_invalid_urls_are_denied(url):
    policy = EgressPolicy(parse_allowlist('api.example.test:443'))
    assert not policy.allows(url)
    with pytest.raises(EgressError):
        policy.require(url)


def test_embedding_factory_denies_host_outside_egress(monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'ollama')
    monkeypatch.setenv('EMBEDDING_BASE_URL', 'http://blocked:11434')
    from uai_runtime.providers import embedding_provider_from_env
    with pytest.raises(ValueError, match='egress_denied'):
        embedding_provider_from_env(EgressPolicy(parse_allowlist('allowed:11434')))


def test_embedding_factory_allows_declared_host(monkeypatch):
    monkeypatch.setenv('EMBEDDING_PROVIDER', 'ollama')
    monkeypatch.setenv('EMBEDDING_BASE_URL', 'http://allowed:11434')
    from uai_runtime.providers import embedding_provider_from_env
    provider = embedding_provider_from_env(EgressPolicy(parse_allowlist('allowed:11434')))
    assert provider.model.dimension > 0


def test_require_returns_url():
    policy = EgressPolicy(parse_allowlist('api.example.test:443'))
    assert policy.require('https://api.example.test') == 'https://api.example.test'
