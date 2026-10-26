#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
name="uai-qdrant-$$"
port=$(python3 - <<'PY'
import socket
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    print(s.getsockname()[1])
PY
)
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run -d --rm --name "$name" -p "127.0.0.1:$port:6333" qdrant/qdrant:v1.15.0 >/dev/null
for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:$port/healthz" >/dev/null 2>&1; then break; fi
    sleep 1
done
UAI_QDRANT_TEST_URL="http://127.0.0.1:$port" python -m pytest apps/runtime/tests/test_vector_store.py -q
