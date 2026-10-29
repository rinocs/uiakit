"""Paths that must never enter a source distribution or package archive."""
from pathlib import PurePosixPath

LOCAL_DIRECTORIES = {
    '.git', '.aws', '.codex', '.agents', '.worktrees', '.superpowers',
    '.venv', 'node_modules', '__pycache__', '.pytest_cache', '.svelte-kit',
}
LOCAL_ROOTS = {'release', 'backups', 'data', 'site'}


def forbidden_release_path(name: str) -> bool:
    path = PurePosixPath(name)
    parts = path.parts
    return (not parts or path.is_absolute() or '\\' in name or '..' in parts
            or any(part in LOCAL_DIRECTORIES for part in parts)
            or parts[0] in LOCAL_ROOTS
            or any(part == '.bootstrap-admin-key' or part == '.env'
                   or part.startswith('.env.') and part != '.env.example'
                   or part.endswith(('.pem', '.key')) for part in parts))
