#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
task_tmp=$(mktemp -d)
task_project="uai-storage-$$"
compose=(docker compose --env-file "$task_tmp/env" -p "$task_project" -f compose.yaml)
cleanup() {
    "${compose[@]}" --profile s3 down -v >/dev/null 2>&1 || true
    rm -rf "$task_tmp"
}
trap cleanup EXIT
python3 - "$task_tmp" <<'PY'
import secrets, socket, sys
from pathlib import Path
p = Path(sys.argv[1])
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
access, secret = secrets.token_hex(16), secrets.token_hex(16)
(p / 'env').write_text(
    f'POSTGRES_PASSWORD={secrets.token_hex(16)}\n'
    f'INTERNAL_API_KEY={secrets.token_hex(16)}\n'
    f'MODEL_BASE_URL=http://mock-provider:9000/v1\n'
    f'MODEL_NAME=test\n'
    f'RUSTFS_PORT={port}\n'
    f'RUSTFS_ACCESS_KEY={access}\n'
    f'RUSTFS_SECRET_KEY={secret}\n'
)
(p / 'port').write_text(str(port))
(p / 'creds').write_text(f'{access}\n{secret}\n')
PY
"${compose[@]}" --profile s3 up -d --wait --wait-timeout 180 rustfs
port=$(cat "$task_tmp/port")
UAI_S3_TEST_ENDPOINT="http://127.0.0.1:$port" \
UAI_S3_TEST_BUCKET="uai-storage-$$" \
UAI_S3_TEST_ACCESS_KEY="$(sed -n '1p' "$task_tmp/creds")" \
UAI_S3_TEST_SECRET_KEY="$(sed -n '2p' "$task_tmp/creds")" \
python -m pytest apps/runtime/tests/test_storage.py -q
