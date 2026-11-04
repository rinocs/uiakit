#!/usr/bin/env python3
"""Create private first-run credentials without touching an existing installation."""
import hashlib
import os
from pathlib import Path
import secrets


def bootstrap(root: Path) -> str:
    try:
        template = (root / '.env.example').read_text()
    except OSError:
        raise SystemExit('bootstrap: .env.example is missing or unreadable') from None
    key = secrets.token_hex(32)
    values = {name: secrets.token_hex(32) for name in (
        'POSTGRES_PASSWORD', 'INTERNAL_API_KEY', 'RUSTFS_ACCESS_KEY', 'RUSTFS_SECRET_KEY')}
    values['UAI_API_KEY_SHA256'] = hashlib.sha256(key.encode()).hexdigest()
    lines = template.splitlines(keepends=True)
    for name, value in values.items():
        indexes = [index for index, line in enumerate(lines) if line.rstrip('\r\n') == name + '=']
        if len(indexes) != 1:
            raise SystemExit('bootstrap: template requires exactly one empty ' + name)
        lines[indexes[0]] = name + '=' + value + '\n'
    try:
        descriptor = os.open(root / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise SystemExit('bootstrap: .env already exists; existing credentials were not changed') from None
    except OSError:
        raise SystemExit('bootstrap: cannot create private .env') from None
    try:
        with os.fdopen(descriptor, 'w') as handle:
            handle.write(''.join(lines))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        raise SystemExit('bootstrap: configuration write failed; check .env before starting') from None
    return key


if __name__ == '__main__':
    admin_key = bootstrap(Path(__file__).resolve().parents[1])
    print('Created .env (0600). Store this admin API key in your secret manager; it is shown once:')
    print(admin_key)
    print('Configure your model in .env, then follow docs/installation.md.')
