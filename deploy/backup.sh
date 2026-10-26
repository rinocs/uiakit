#!/usr/bin/env bash
# Consistent backup of PostgreSQL, filesystem blobs and non-secret configuration.
# Secrets are never included. Qdrant is intentionally excluded: it is rebuildable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/.env"
PROJECT=""
OUTPUT=""
QUIESCE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --no-quiesce) QUIESCE=0; shift ;;
    -h|--help) echo "usage: $0 [--env-file .env] [--project name] [--output dir] [--no-quiesce]"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
if [ ! -f "$ENV_FILE" ]; then echo "env file not found: $ENV_FILE" >&2; exit 2; fi
if [ -z "$OUTPUT" ]; then OUTPUT="$ROOT/backups/$(date -u +%Y%m%dT%H%M%SZ)"; fi
mkdir -p "$OUTPUT"
OUTPUT="$(cd "$OUTPUT" && pwd)"
umask 077
compose=(docker compose --env-file "$ENV_FILE")
if [ -n "$PROJECT" ]; then compose+=(-p "$PROJECT"); fi
if [ -z "$PROJECT" ]; then
  PROJECT=$("${compose[@]}" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name","uai"))')
fi
blob_volume="${PROJECT}_blob-data"
if ! docker volume inspect "$blob_volume" >/dev/null 2>&1; then
  echo "blob volume not found: $blob_volume" >&2
  exit 2
fi

started=$(date +%s)
was_running=()
if [ "$QUIESCE" = 1 ]; then
  mapfile -t was_running < <("${compose[@]}" ps --services --filter status=running)
  if [ "${#was_running[@]}" -gt 0 ]; then
    "${compose[@]}" stop gateway runtime worker >/dev/null 2>&1 || true
  fi
fi
restore_services() {
  if [ "$QUIESCE" = 1 ] && [ "${#was_running[@]}" -gt 0 ]; then
    "${compose[@]}" start "${was_running[@]}" >/dev/null 2>&1 || true
  fi
}
trap restore_services EXIT

schema_version=$("${compose[@]}" exec -T postgres psql -U uai -d uai -tAc 'SELECT COALESCE(max(version),0) FROM schema_migrations')
if [ -z "$schema_version" ] || [ "$schema_version" -lt 1 ]; then
  echo "database schema is not initialized" >&2
  exit 2
fi

dump_start=$(date +%s)
"${compose[@]}" exec -T postgres pg_dump -U uai -d uai -Fc > "$OUTPUT/postgres.dump"
dump_end=$(date +%s)

blob_start=$(date +%s)
docker run --rm -v "$blob_volume:/data:ro" -v "$OUTPUT:/backup" alpine:3.20 \
  tar czf /backup/blobs.tar.gz -C /data .
blob_end=$(date +%s)

tar czf "$OUTPUT/configs.tar.gz" compose.yaml .env.example configs deploy
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
end=$(date +%s)
python3 - "$OUTPUT" "$created_at" "$schema_version" "$((dump_end-dump_start))" "$((blob_end-blob_start))" "$((end-started))" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
out = Path(sys.argv[1])
created, schema, dump_seconds, blob_seconds, total_seconds = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
files = ['postgres.dump', 'blobs.tar.gz', 'configs.tar.gz']
checksums = {}
for name in files:
    h = hashlib.sha256()
    with open(out / name, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    checksums[name] = h.hexdigest()
manifest = {
    'format': 'uai-backup-v1',
    'created_at': created,
    'application': 'universal-ai-kit',
    'schema_version': schema,
    'secrets_included': False,
    'qdrant_included': False,
    'files': files,
    'checksums': checksums,
    'timing': {
        'dump_seconds': dump_seconds,
        'blob_seconds': blob_seconds,
        'backup_seconds': total_seconds,
        'rpo_upper_bound_seconds': total_seconds,
    },
}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
PY
(cd "$OUTPUT" && sha256sum postgres.dump blobs.tar.gz configs.tar.gz manifest.json > SHA256SUMS)
echo "backup written to $OUTPUT"
echo "schema_version=$schema_version rpo_upper_bound_seconds=$((end-started))"
