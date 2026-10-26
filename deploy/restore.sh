#!/usr/bin/env bash
# Restore a verified uai-backup-v1 into an isolated/new installation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BACKUP=""
ENV_FILE="$ROOT/.env"
PROJECT=""
RESET=0
START=0
NO_CONFIGS=0
CONFIG_DIR=""
REPORT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --backup) BACKUP="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --reset-target) RESET=1; shift ;;
    --start) START=1; shift ;;
    --no-configs) NO_CONFIGS=1; shift ;;
    --config-dir) CONFIG_DIR="$2"; shift 2 ;;
    --report) REPORT="$2"; shift 2 ;;
    -h|--help) echo "usage: $0 --backup dir [--env-file .env] [--project name] [--reset-target] [--start] [--no-configs]"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
if [ -z "$BACKUP" ] || [ ! -f "$BACKUP/manifest.json" ]; then echo "backup directory with manifest.json required" >&2; exit 2; fi
BACKUP="$(cd "$BACKUP" && pwd)"
if [ ! -f "$ENV_FILE" ]; then echo "env file not found: $ENV_FILE" >&2; exit 2; fi
if [ -z "$REPORT" ]; then REPORT="$ROOT/restore-report-$(date -u +%Y%m%dT%H%M%SZ).json"; fi
if [ -z "$CONFIG_DIR" ]; then CONFIG_DIR="$ROOT/restored-config-$(date -u +%Y%m%dT%H%M%SZ)"; fi
started=$(date +%s)
compose=(docker compose --env-file "$ENV_FILE")
if [ -n "$PROJECT" ]; then compose+=(-p "$PROJECT"); fi
if [ -z "$PROJECT" ]; then
  PROJECT=$("${compose[@]}" config --format json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name","uai"))')
fi
blob_volume="${PROJECT}_blob-data"

# Verify before touching any target state.
(cd "$BACKUP" && sha256sum -c SHA256SUMS >/dev/null)
python3 - "$BACKUP/manifest.json" "$ROOT/apps/gateway/migrations" <<'PY'
import json, re, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
if manifest.get('format') != 'uai-backup-v1':
    raise SystemExit('unsupported backup format')
if manifest.get('secrets_included') is not False:
    raise SystemExit('backup manifest must declare secrets_included=false')
max_supported = max(int(re.match(r'(\d+)', p.name).group(1)) for p in Path(sys.argv[2]).glob('*.sql'))
schema = int(manifest.get('schema_version', 0))
if schema < 1 or schema > max_supported:
    raise SystemExit(f'incompatible schema version {schema} (supported <= {max_supported})')
print(f"backup schema={schema} supported<={max_supported}")
PY

"${compose[@]}" stop gateway runtime worker >/dev/null 2>&1 || true
"${compose[@]}" up -d --wait postgres
if [ "$RESET" = 1 ]; then
  echo "resetting target database and blob volume"
  "${compose[@]}" exec -T postgres dropdb -U uai --if-exists --force uai
  "${compose[@]}" exec -T postgres createdb -U uai uai
else
  exists=$("${compose[@]}" exec -T postgres psql -U uai -d postgres -tAc "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname='uai')")
  if [ "$exists" != "t" ]; then
    "${compose[@]}" exec -T postgres createdb -U uai uai
  fi
  tables=$("${compose[@]}" exec -T postgres psql -U uai -d uai -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
  if [ "$tables" != "0" ]; then
    echo "target database is not empty; use --reset-target only for a new/isolated installation" >&2
    exit 3
  fi
fi

"${compose[@]}" exec -T postgres pg_restore -U uai -d uai --no-owner --no-privileges < "$BACKUP/postgres.dump"
docker run --rm -v "$blob_volume:/data" -v "$BACKUP:/backup:ro" alpine:3.20 \
  sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null || true; tar xzf /backup/blobs.tar.gz -C /data'
if [ "$NO_CONFIGS" = 0 ]; then
  mkdir -p "$CONFIG_DIR"
  tar xzf "$BACKUP/configs.tar.gz" -C "$CONFIG_DIR"
fi
restored=$(date +%s)
python3 - "$REPORT" "$BACKUP/manifest.json" "$((restored-started))" "$CONFIG_DIR" <<'PY'
import json, sys
from pathlib import Path
report, manifest, seconds, config_dir = sys.argv[1], json.loads(Path(sys.argv[2]).read_text()), int(sys.argv[3]), sys.argv[4]
Path(report).write_text(json.dumps({
    'format': 'uai-restore-report-v1',
    'backup_created_at': manifest.get('created_at'),
    'backup_schema_version': manifest.get('schema_version'),
    'restore_seconds': seconds,
    'rto_seconds': seconds,
    'rpo_upper_bound_seconds': manifest.get('timing', {}).get('rpo_upper_bound_seconds'),
    'checksums_verified': True,
    'config_dir': config_dir,
}, indent=2) + '\n')
PY
if [ "$START" = 1 ]; then
  "${compose[@]}" up -d --wait --wait-timeout 120 gateway runtime
fi
echo "restore completed in $((restored-started))s; report=$REPORT"
echo "Qdrant is not restored by design: run a reindex for each KB (POST /v1/knowledge-bases/{id}/versions) to rebuild vectors."
