#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
task_tmp=$(mktemp -d)
task_project="uai-e2e-$$"
compose=(docker compose --env-file "$task_tmp/env" -p "$task_project" -f compose.yaml -f tests/e2e/compose.yaml)
cleanup() {
    code=$?
    if [ "$code" -ne 0 ]; then
        "${compose[@]}" logs --no-color 2>&1 || true
    fi
    "${compose[@]}" --profile worker --profile rag down -v >/dev/null 2>&1 || true
    rm -rf "$task_tmp"
}
trap cleanup EXIT
python3 - "$task_tmp" <<'PY'
import hashlib, secrets, socket, sys
from pathlib import Path
p=Path(sys.argv[1]); key=secrets.token_hex(32)
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
with socket.socket() as s:
    s.bind(('127.0.0.1', 0))
    qdrant_port = s.getsockname()[1]
(p/'key').write_text(key)
(p/'env').write_text(f'POSTGRES_PASSWORD={secrets.token_hex(32)}\nINTERNAL_API_KEY={secrets.token_hex(32)}\nRUSTFS_ACCESS_KEY={secrets.token_hex(16)}\nRUSTFS_SECRET_KEY={secrets.token_hex(16)}\nISOLATED_PLUGIN_TOKEN={secrets.token_hex(32)}\nUAI_API_KEY_SHA256={hashlib.sha256(key.encode()).hexdigest()}\nMODEL_NAME=test\nMODEL_BASE_URL=http://mock-provider:9000/v1\nUAI_BIND_ADDRESS=127.0.0.1\nUAI_PORT={port}\nUAI_RATE_LIMIT=10000\nUAI_RATE_LIMIT_PER_PRINCIPAL=10000\nUAI_WIDGET_ORIGINS=http://widget.e2e\nUAI_WIDGET_RATE_LIMIT=1000\nUAI_RETENTION_CONVERSATION_DAYS=30\nUAI_RETENTION_AUDIT_DAYS=30\nUAI_RETENTION_APPROVAL_DAYS=30\nUAI_RETENTION_CLEANUP_DAYS=30\nUAI_OTEL_ENDPOINT=http://127.0.0.1:4318\nQDRANT_TEST_PORT={qdrant_port}\n')
PY
"${compose[@]}" --profile worker build
"${compose[@]}" up -d --wait --wait-timeout 180 postgres runtime
"${compose[@]}" up -d --wait --wait-timeout 120 gateway
export UAI_TEST_URL="http://$("${compose[@]}" port gateway 8080)"
export UAI_TEST_KEY="$(cat "$task_tmp/key")"
export UAI_TEST_INTERNAL_KEY="$(grep '^INTERNAL_API_KEY=' "$task_tmp/env" | cut -d= -f2)"
export UAI_TEST_WIDGET_ORIGIN="http://widget.e2e"
python3 tests/e2e/check.py initial "$task_tmp/state"
python3 tests/e2e/check_auth.py
python3 tests/e2e/check_integrations.py
python3 tests/e2e/check_observability.py
python3 tests/e2e/check_versions.py
python3 tests/e2e/check_directives.py "$task_tmp/directive-runs.json"
python3 tests/e2e/check_builtins.py
python3 tests/e2e/check_tools.py
"${compose[@]}" exec -T runtime python /app/uai_e2e_tools.py
"${compose[@]}" exec -T runtime python /app/uai_e2e_plugin_sdk.py
"${compose[@]}" exec -T runtime python /app/uai_e2e_plugins.py
"${compose[@]}" exec -T runtime python /app/uai_e2e_isolated.py
python3 tests/e2e/check_plugin_admin.py initial "$task_tmp/plugin-state.json"
python3 tests/e2e/check_knowledge_bases.py
python3 tests/e2e/check_documents.py "$task_tmp/documents.json"
deletion_assistant=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['assistant'])" "$task_tmp/state")
deletion_kb=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['kb'])" "$task_tmp/documents.json")
deletion_conversation=$(python3 -c 'import uuid; print(uuid.uuid4())')
deletion_live_conversation=$(python3 -c 'import uuid; print(uuid.uuid4())')
deletion_run=$(python3 -c 'import uuid; print(uuid.uuid4())')
deletion_approval=$(python3 -c 'import uuid; print(uuid.uuid4())')
deletion_audit_target=$(python3 -c 'import uuid; print(uuid.uuid4())')
deletion_cleanup=$(python3 -c 'import uuid; print(uuid.uuid4())')
deletion_document=$(python3 -c 'import uuid; print(uuid.uuid4())')
"${compose[@]}" exec -T postgres psql -U uai -d uai -v ON_ERROR_STOP=1 <<SQL
INSERT INTO conversations(id,assistant_id,owner_id,created_at)
 VALUES ('$deletion_conversation','$deletion_assistant','bootstrap-operator',now()-interval '90 days');
INSERT INTO conversations(id,assistant_id,owner_id)
 VALUES ('$deletion_live_conversation','$deletion_assistant','bootstrap-operator');
INSERT INTO agent_runs(id,conversation_id,idempotency_key,content,status,assistant_id,assistant_version,assistant_config,model_snapshot,created_at)
 VALUES ('$deletion_run','$deletion_live_conversation','retention-e2e','old','completed','$deletion_assistant',1,'{}','{}',now()-interval '90 days');
INSERT INTO approvals(id,run_id,tool_id,tool_version,arguments_digest,policy_digest,policy_snapshot,requested_by,status,created_at,expires_at,decided_at,decided_by)
 VALUES ('$deletion_approval','$deletion_run','example.write','1.0.0',repeat('d',64),repeat('e',64),'{}'::jsonb,'bootstrap-operator','approved',now()-interval '90 days',now()-interval '89 days',now()-interval '89 days','bootstrap-operator');
INSERT INTO audit_events(actor_principal_id,action,target_id,target_type,created_at)
 VALUES ('bootstrap-operator','old.retention','$deletion_audit_target','conversation',now()-interval '90 days');
INSERT INTO vector_cleanup_jobs(id,document_id,knowledge_base_id,chunk_ids,state,attempts,created_at,updated_at)
 VALUES ('$deletion_cleanup','$deletion_document','$deletion_kb',ARRAY['a'],'completed',1,now()-interval '90 days',now()-interval '90 days');
SQL
python3 tests/e2e/check_deletion.py
"${compose[@]}" exec -T postgres psql -U uai -d uai -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
 IF EXISTS (SELECT 1 FROM conversations WHERE id='$deletion_conversation') THEN RAISE EXCEPTION 'retention left conversation'; END IF;
 IF NOT EXISTS (SELECT 1 FROM deletion_tombstones WHERE resource_type='conversation' AND resource_id='$deletion_conversation' AND reason='retention') THEN RAISE EXCEPTION 'retention tombstone missing'; END IF;
 IF EXISTS (SELECT 1 FROM approvals WHERE id='$deletion_approval') THEN RAISE EXCEPTION 'retention left approval'; END IF;
 IF EXISTS (SELECT 1 FROM audit_events WHERE action='old.retention') THEN RAISE EXCEPTION 'retention left audit'; END IF;
 IF EXISTS (SELECT 1 FROM vector_cleanup_jobs WHERE id='$deletion_cleanup') THEN RAISE EXCEPTION 'retention left cleanup job'; END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE action='retention.applied') THEN RAISE EXCEPTION 'retention audit missing'; END IF;
END \$\$;
SQL
"${compose[@]}" exec -T postgres psql -U uai -d uai -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM plugin_configuration WHERE singleton AND revision>=2 AND settings->'org.uai.hello'->>'enabled'='true')
 OR NOT EXISTS (SELECT 1 FROM plugin_configuration_audit WHERE revision=2 AND actor_id='bootstrap-operator' AND changed_plugin_ids=ARRAY['org.uai.hello'])
 OR (SELECT count(*) FROM schema_migrations WHERE version BETWEEN 1 AND 10)<>10
 OR NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version=14)
 OR to_regclass('public.widget_tokens') IS NULL
 OR NOT EXISTS (SELECT 1 FROM knowledge_bases)
 OR NOT EXISTS (SELECT 1 FROM knowledge_base_versions WHERE state='active')
 OR NOT EXISTS (SELECT 1 FROM documents)
 OR NOT EXISTS (SELECT 1 FROM document_jobs WHERE state='queued')
 OR to_regclass('public.document_chunks') IS NULL
 OR to_regclass('public.vector_cleanup_jobs') IS NULL
 THEN RAISE EXCEPTION 'plugin desired state, audit or migration tracking missing'; END IF;
END $$;
SQL
"${compose[@]}" --profile worker --profile rag up -d --wait --wait-timeout 180 qdrant worker
python3 tests/e2e/check_worker.py "$task_tmp/documents.json"
"${compose[@]}" --profile worker stop worker
pdf_id=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['pdf'])" "$task_tmp/documents.json")
docx_id=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['docx'])" "$task_tmp/documents.json")
pdf_before=$("${compose[@]}" exec -T postgres psql -U uai -d uai -tAc "SELECT count(*) FROM document_chunks WHERE document_id='$pdf_id'")
"${compose[@]}" exec -T postgres psql -U uai -d uai -v ON_ERROR_STOP=1 <<SQL
UPDATE document_jobs SET state='queued',attempts=1,lease_owner=NULL,lease_until=NULL,error_code='e2e_retry',updated_at=now() WHERE document_id='$pdf_id';
UPDATE document_jobs SET state='running',attempts=1,lease_owner='dead-worker',lease_until=now()-interval '1 minute',error_code='e2e_crash',updated_at=now() WHERE document_id='$docx_id';
DELETE FROM document_chunks WHERE document_id='$docx_id';
SQL
"${compose[@]}" --profile worker start worker
python3 tests/e2e/check_worker.py "$task_tmp/documents.json"
pdf_after=$("${compose[@]}" exec -T postgres psql -U uai -d uai -tAc "SELECT count(*) FROM document_chunks WHERE document_id='$pdf_id'")
docx_after=$("${compose[@]}" exec -T postgres psql -U uai -d uai -tAc "SELECT count(*) FROM document_chunks WHERE document_id='$docx_id'")
cancel_id=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['cancelled'])" "$task_tmp/documents.json")
cancel_chunks=$("${compose[@]}" exec -T postgres psql -U uai -d uai -tAc "SELECT count(*) FROM document_chunks WHERE document_id='$cancel_id'")
[ "$pdf_before" = "$pdf_after" ] && [ "$docx_after" -gt 0 ] && [ "$cancel_chunks" = "0" ] || { echo "worker retry/crash/cancel chunk verification failed"; exit 1; }
export UAI_QDRANT_TEST_URL="http://127.0.0.1:$(grep '^QDRANT_TEST_PORT=' "$task_tmp/env" | cut -d= -f2)"
python3 tests/e2e/check_ingestion.py "$task_tmp/documents.json"
python3 tests/e2e/check_rag.py "$task_tmp/documents.json"
python3 tests/e2e/check_agent_runs.py
"${compose[@]}" exec -T -e UAI_TEST_URL=http://gateway:8080 -e UAI_TEST_KEY="$UAI_TEST_KEY" -e MOCK_TOOL_URL=http://mock-tool:9100 runtime python /app/uai_e2e_agents.py
python3 tests/e2e/check_approvals.py seed "$task_tmp/approvals.json"
approval_state="$task_tmp/approvals.json"
approval_assistant=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['assistant'])" "$approval_state")
approval_conversation_1=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['conversations'][0])" "$approval_state")
approval_conversation_2=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['conversations'][1])" "$approval_state")
approval_conversation_3=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['conversations'][2])" "$approval_state")
approval_run_1=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['runs'][0])" "$approval_state")
approval_run_2=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['runs'][1])" "$approval_state")
approval_run_3=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['runs'][2])" "$approval_state")
approval_id_1=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['approvals'][0])" "$approval_state")
approval_id_2=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['approvals'][1])" "$approval_state")
approval_id_3=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['approvals'][2])" "$approval_state")
mutation_approval=$(python3 -c 'import uuid; print(uuid.uuid4())')
"${compose[@]}" exec -T postgres psql -U uai -d uai -v ON_ERROR_STOP=1 <<SQL
INSERT INTO agent_runs(id,conversation_id,idempotency_key,content,status,assistant_id,assistant_version,assistant_config,model_snapshot)
 VALUES ('$approval_run_1','$approval_conversation_1','approval-e2e-1','approval','waiting_approval','$approval_assistant',1,'{}','{}');
INSERT INTO agent_runs(id,conversation_id,idempotency_key,content,status,assistant_id,assistant_version,assistant_config,model_snapshot)
 VALUES ('$approval_run_2','$approval_conversation_2','approval-e2e-2','approval','waiting_approval','$approval_assistant',1,'{}','{}');
INSERT INTO agent_runs(id,conversation_id,idempotency_key,content,status,assistant_id,assistant_version,assistant_config,model_snapshot)
 VALUES ('$approval_run_3','$approval_conversation_3','approval-e2e-3','approval','waiting_approval','$approval_assistant',1,'{}','{}');
INSERT INTO approvals(id,run_id,tool_id,tool_version,arguments_digest,policy_digest,policy_snapshot,requested_by,status,created_at,expires_at)
 VALUES ('$approval_id_1','$approval_run_1','example.write','1.0.0',repeat('a',64),repeat('b',64),'{"assistant":{"version":1},"tool":{"id":"example.write"}}'::jsonb,'bootstrap-operator','pending',now(),now()+interval '10 minutes');
INSERT INTO approvals(id,run_id,tool_id,tool_version,arguments_digest,policy_digest,policy_snapshot,requested_by,status,created_at,expires_at)
 VALUES ('$approval_id_2','$approval_run_2','example.write','1.0.0',repeat('a',64),repeat('b',64),'{"assistant":{"version":1},"tool":{"id":"example.write"}}'::jsonb,'bootstrap-operator','pending',now()-interval '11 minutes',now()-interval '1 minute');
INSERT INTO approvals(id,run_id,tool_id,tool_version,arguments_digest,policy_digest,policy_snapshot,requested_by,status,created_at,expires_at)
 VALUES ('$approval_id_3','$approval_run_3','example.write','1.0.0',repeat('a',64),repeat('b',64),'{"assistant":{"version":1},"tool":{"id":"example.write"}}'::jsonb,'bootstrap-operator','pending',now(),now()+interval '10 minutes');
INSERT INTO approvals(id,run_id,tool_id,tool_version,arguments_digest,policy_digest,policy_snapshot,requested_by,status,created_at,expires_at,decided_at,decided_by)
 VALUES ('$mutation_approval','$approval_run_1','example.write','1.0.0','88e6a2f04974d62032840187527896fbe6e46f7ef4b5c1e7ac54c090e409fe14',repeat('c',64),'{}'::jsonb,'bootstrap-operator','approved',now(),now()+interval '10 minutes',now(),'bootstrap-operator');
SQL
python3 tests/e2e/check_approvals.py decide "$task_tmp/approvals.json"
python3 tests/e2e/check_tool_executions.py "$task_tmp/approvals.json"
"${compose[@]}" exec -T -e MUTATION_RUN="$approval_run_1" -e MUTATION_APPROVAL="$mutation_approval" -e UAI_TEST_KEY="$UAI_TEST_KEY" runtime python /app/uai_e2e_mutating.py
"${compose[@]}" exec -T postgres psql -U uai -d uai -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE version=13) THEN
  RAISE EXCEPTION 'audit migration missing';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE action='approval.approved'
   AND target_id='$approval_id_1' AND run_id='$approval_run_1'
   AND digest=repeat('a',64) AND outcome='approved'
   AND correlation_id=(SELECT correlation_id FROM agent_runs WHERE id='$approval_run_1')) THEN
  RAISE EXCEPTION 'approval audit is not reconstructable';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE action='approval.expired'
   AND target_id='$approval_id_2' AND outcome='expired') THEN
  RAISE EXCEPTION 'expired approval audit missing';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE action='approval.rejected'
   AND target_id='$approval_id_3' AND outcome='rejected') THEN
  RAISE EXCEPTION 'rejected approval audit missing';
 END IF;
 IF (SELECT count(DISTINCT action) FROM audit_events
   WHERE run_id='$approval_run_1' AND action LIKE 'tool_execution.%') < 6 THEN
  RAISE EXCEPTION 'tool execution audit transitions missing';
 END IF;
 IF EXISTS (SELECT 1 FROM audit_events WHERE run_id='$approval_run_1'
   AND (digest IS NULL OR correlation_id IS NULL OR
        details::text ~* '(authorization|bearer|api[_-]?key|password|secret|token)')) THEN
  RAISE EXCEPTION 'audit binding or redaction invalid';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE action='agent_run.started'
   AND actor_principal_id='bootstrap-operator' AND outcome='success') THEN
  RAISE EXCEPTION 'authorized run audit missing';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM tool_executions WHERE run_id='$approval_run_1'
   AND tool_id='example.write' AND approval_id='$mutation_approval' AND status='completed') THEN
  RAISE EXCEPTION 'mutating execution record incoherent';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM approvals WHERE id='$mutation_approval' AND status='consumed') THEN
  RAISE EXCEPTION 'approval was not consumed exactly once';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE run_id='$approval_run_1'
   AND action='tool_execution.completed' AND details->>'tool_id'='example.write'
   AND digest='88e6a2f04974d62032840187527896fbe6e46f7ef4b5c1e7ac54c090e409fe14') THEN
  RAISE EXCEPTION 'mutating tool audit missing';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE action='assistant.created'
   AND target_type='assistant' AND digest IS NOT NULL AND details ? 'model') THEN
  RAISE EXCEPTION 'assistant configuration audit missing';
 END IF;
 IF NOT EXISTS (SELECT 1 FROM audit_events WHERE action='credential.created'
   AND target_type='credential' AND details ? 'role') THEN
  RAISE EXCEPTION 'credential configuration audit missing';
 END IF;
END \$\$;
SQL
"${compose[@]}" exec -T runtime python -c "from pathlib import Path; print(Path('/tmp/uai-e2e-trace.jsonl').read_text(), end='')" > "$task_tmp/observations.jsonl"
python3 tests/e2e/check_hooks.py "$task_tmp/observations.jsonl" "$task_tmp/directive-runs.json"
"${compose[@]}" restart runtime
"${compose[@]}" up -d --wait --wait-timeout 60 runtime
python3 tests/e2e/check_plugin_admin.py runtime-restarted "$task_tmp/plugin-state.json"
"${compose[@]}" restart gateway
# Wait for startup without depending on a fixed sleep duration.
python3 - <<'PY'
import os,time,urllib.request
for _ in range(60):
    try:
        urllib.request.urlopen(os.environ['UAI_TEST_URL']+'/v1/health',timeout=1)
        break
    except OSError: time.sleep(1)
else: raise SystemExit('gateway did not recover')
PY
python3 tests/e2e/check.py restarted "$task_tmp/state"

python3 tests/e2e/check_plugin_admin.py restarted "$task_tmp/plugin-state.json"

export UAI_TEST_PROJECT="$task_project"
export UAI_TEST_ENVFILE="$task_tmp/env"
python3 tests/e2e/check_recovery.py --output "$task_tmp/recovery.json"
python3 tests/performance/run.py --output "$task_tmp/performance.json"
compare=()
if [ -n "${UAI_PERF_COMPARE:-}" ]; then
  compare=(--baseline "$UAI_PERF_COMPARE")
fi
python3 tests/performance/check_baseline.py "$task_tmp/performance.json" "${compare[@]}"
if [ -n "${UAI_PERF_OUTPUT:-}" ]; then
  cp "$task_tmp/performance.json" "$UAI_PERF_OUTPUT"
fi
