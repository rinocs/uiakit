import pytest

from uai_runtime.secrets import SecretError, read_secret_file, secret_from_env


def test_environment_secret(monkeypatch):
    monkeypatch.setenv('EXAMPLE_TOKEN', 'value')
    assert secret_from_env('EXAMPLE_TOKEN', required=True) == 'value'


def test_missing_optional_secret(monkeypatch):
    monkeypatch.delenv('EXAMPLE_TOKEN', raising=False)
    monkeypatch.delenv('EXAMPLE_TOKEN_FILE', raising=False)
    assert secret_from_env('EXAMPLE_TOKEN') is None
    with pytest.raises(SecretError, match='missing_secret'):
        secret_from_env('EXAMPLE_TOKEN', required=True)


def test_empty_environment_value_is_unset(monkeypatch):
    monkeypatch.setenv('EXAMPLE_TOKEN', '')
    assert secret_from_env('EXAMPLE_TOKEN') is None
    with pytest.raises(SecretError, match='missing_secret'):
        secret_from_env('EXAMPLE_TOKEN', required=True)


def test_file_secret_strips_one_newline(monkeypatch, tmp_path):
    path = tmp_path / 'token'
    path.write_bytes(b'file-value\n')
    monkeypatch.setenv('EXAMPLE_TOKEN_FILE', str(path))
    assert secret_from_env('EXAMPLE_TOKEN', required=True) == 'file-value'


def test_file_and_environment_conflict(monkeypatch, tmp_path):
    path = tmp_path / 'token'
    path.write_text('file-value')
    monkeypatch.setenv('EXAMPLE_TOKEN', 'env-value')
    monkeypatch.setenv('EXAMPLE_TOKEN_FILE', str(path))
    with pytest.raises(SecretError, match='ambiguous_secret_source'):
        secret_from_env('EXAMPLE_TOKEN')


def test_file_secret_rotates_without_restart(monkeypatch, tmp_path):
    path = tmp_path / 'token'
    path.write_text('first')
    monkeypatch.setenv('EXAMPLE_TOKEN_FILE', str(path))
    assert secret_from_env('EXAMPLE_TOKEN') == 'first'
    path.write_text('second')
    assert secret_from_env('EXAMPLE_TOKEN') == 'second'


@pytest.mark.parametrize('content', [b'', b'line\nbreak', b'with\x00nul', b'\xff'])
def test_invalid_file_content(monkeypatch, tmp_path, content):
    path = tmp_path / 'token'
    path.write_bytes(content)
    monkeypatch.setenv('EXAMPLE_TOKEN_FILE', str(path))
    with pytest.raises(SecretError):
        secret_from_env('EXAMPLE_TOKEN')


def test_invalid_file_paths(monkeypatch):
    for value in ('relative', '/run/secrets/../token', '/run/secret token', ''):
        monkeypatch.setenv('EXAMPLE_TOKEN_FILE', value)
        if not value:
            monkeypatch.delenv('EXAMPLE_TOKEN_FILE')
        with pytest.raises(SecretError):
            secret_from_env('EXAMPLE_TOKEN', required=True)


def test_missing_file_is_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv('EXAMPLE_TOKEN_FILE', str(tmp_path / 'absent'))
    with pytest.raises(SecretError, match='secret_file_unreadable'):
        secret_from_env('EXAMPLE_TOKEN')


def test_invalid_names():
    for name in ('example', 'EXAMPLE-TOKEN', ''):
        with pytest.raises(SecretError, match='invalid_secret_name'):
            secret_from_env(name)


def test_read_secret_file_directly(tmp_path):
    path = tmp_path / 'token'
    path.write_text('direct')
    assert read_secret_file(str(path)) == 'direct'
