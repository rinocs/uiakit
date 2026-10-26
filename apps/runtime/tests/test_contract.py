import json
from pathlib import Path

from fastapi.openapi.models import OpenAPI

from uai_runtime.app import create_app
from uai_runtime.provider import OpenAIProvider

CONTRACTS = Path(__file__).resolve().parents[3] / 'packages' / 'api-contract'


def test_openapi_contracts_and_internal_snapshot():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    internal = json.loads((CONTRACTS / 'internal.openapi.json').read_text())
    OpenAPI.model_validate(public)
    OpenAPI.model_validate(internal)
    assert public['openapi'] == '3.1.0'
    assert public['security'] == [{'operatorKey': []}]
    app = create_app('internal-secret', OpenAIProvider('http://provider/v1', ''))
    assert app.openapi() == internal


def test_credentials_contract_does_not_expose_persisted_key_material():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    props = public['components']['schemas']['Credential']['properties']
    assert 'api_key' not in props
    assert 'key_digest' not in props
    assert public['paths']['/v1/credentials']['post']['operationId'] == 'createCredential'
    assert '403' in public['paths']['/v1/assistants']['post']['responses']


def test_version_and_model_public_contracts_match_config_fields():
    from uai_core.configuration import AssistantConfig
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    schemas = public['components']['schemas']
    assert set(AssistantConfig.model_fields) == set(schemas['Assistant']['properties'])
    assert public['paths']['/v1/assistants/{id}']['patch']['parameters'][0]['name'] == 'If-Match'
    assert '412' in public['paths']['/v1/assistants/{id}']['patch']['responses']
    assert not {'secret_ref', 'api_key', 'base_url'} & schemas['ModelDefinition']['properties'].keys()


def test_metadata_lifecycle_schema_matches_core_and_enforces_phase_payload_pairing():
    from uai_core.events import LifecycleEvent, LIFECYCLE_PAYLOADS
    schema = LifecycleEvent.model_json_schema()
    schema['$schema'] = 'https://json-schema.org/draft/2020-12/schema'
    assert json.loads((CONTRACTS / 'lifecycle.schema.json').read_text()) == schema
    assert len(schema['allOf']) == len(LIFECYCLE_PAYLOADS) == 18
    assert {'request.received', 'agent.cancelled', 'memory.write'} <= set(schema['properties']['event_type']['enum'])
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    # Observability is a distinct metadata contract, not new public SSE frames.
    event = public['components']['schemas']['RuntimeEvent']
    assert set(event['properties']['event_type']['enum']) == {
        'agent.started', 'response.delta', 'response.completed', 'agent.failed', 'agent.cancelled'}


def test_public_tool_catalog_matches_core_metadata_and_has_no_execution_endpoint():
    from uai_core.tools import ToolDefinition
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    metadata = public['components']['schemas']['ToolDefinition']['properties']
    assert set(metadata) == set(ToolDefinition.model_fields)
    assert public['paths']['/v1/tools']['get']['operationId'] == 'listTools'
    assert set(public['paths']['/v1/tools']) == {'get'}
    assert {'401','403','503'} <= public['paths']['/v1/tools']['get']['responses'].keys()
    assert not {'handler','module','api_key','base_url'} & metadata.keys()


def test_plugin_administration_is_versioned_and_has_no_install_route():
    from uai_plugin_sdk.manifest import PluginManifest
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    schemas = public['components']['schemas']
    assert set(schemas['PluginManifest']['properties']) == set(PluginManifest.model_fields)
    assert set(public['paths']['/v1/plugins']) == {'get'}
    route = public['paths']['/v1/plugins/{id}']
    assert set(route) == {'put', 'delete'}
    for method in route.values():
        assert any(p['name'] == 'If-Match' and p['required'] for p in method['parameters'])
        assert {'200', '202', '403', '412', '428', '503'} <= method['responses'].keys()
    assert 'config' not in schemas['PluginCatalog']['properties']
    assert not any('install' in path or 'reload' in path for path in public['paths'])


def test_knowledge_base_contract_allows_bounded_associations_and_versions():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    schemas = public['components']['schemas']
    assert schemas['Assistant']['properties']['knowledge_base_ids']['maxItems'] == 64
    assert public['paths']['/v1/knowledge-bases']['get']['operationId'] == 'listKnowledgeBases'
    assert public['paths']['/v1/knowledge-bases']['post']['operationId'] == 'createKnowledgeBase'
    route = public['paths']['/v1/knowledge-bases/{id}']
    assert set(route) == {'parameters', 'get', 'patch', 'delete'}
    for method in ('patch', 'delete'):
        assert any(p['name'] == 'If-Match' and p['required'] for p in route[method]['parameters'])
        assert {'401', '403', '404', '412', '422', '428', '503'} <= route[method]['responses'].keys()
    versions = public['paths']['/v1/knowledge-bases/{id}/versions']
    assert set(versions) == {'parameters', 'get', 'post'}
    assert versions['post']['responses']['201']['headers']['ETag']
    assert set(schemas['KnowledgeBaseVersion']['properties']['state']['enum']) == {
        'active', 'reindexing', 'building', 'ready', 'failed', 'superseded'}
    assert set(schemas['KnowledgeBase']['properties']) == {
        'id', 'name', 'description', 'revision', 'active_version', 'created_at', 'updated_at'}


def test_document_upload_contract_limits_formats_and_hides_blob_paths():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    schemas = public['components']['schemas']
    assert schemas['Document']['properties']['size_bytes']['maximum'] == 20971520
    assert 'blob_key' in schemas['Document']['properties']
    assert set(schemas['Document']['properties']['mime_type']['enum']) == {
        'text/plain', 'text/markdown', 'text/html', 'application/pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
    upload = schemas['DocumentUpload']
    assert upload['required'] == ['knowledge_base_id', 'file']
    assert public['paths']['/v1/documents']['post']['requestBody']['content']['multipart/form-data']
    assert '413' in public['paths']['/v1/documents']['post']['responses']
    assert '415' in public['paths']['/v1/documents']['post']['responses']
    assert set(public['paths']['/v1/documents/{id}']) == {'parameters', 'get', 'delete'}


def test_document_job_contract_is_authorized_and_has_cancellation():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    job = public['components']['schemas']['DocumentJob']
    assert set(job['properties']['state']['enum']) == {
        'queued', 'running', 'completed', 'failed', 'cancelled'}
    assert public['paths']['/v1/documents/{id}/job']['get']['operationId'] == 'getDocumentJob'
    assert public['paths']['/v1/documents/{id}/job/cancel']['post']['operationId'] == 'cancelDocumentJob'
    assert '409' in public['paths']['/v1/documents/{id}/job/cancel']['post']['responses']


def test_index_version_and_export_contract():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    schemas = public['components']['schemas']
    assert set(schemas['KnowledgeBaseVersion']['properties']['state']['enum']) == {
        'active', 'reindexing', 'building', 'ready', 'failed', 'superseded'}
    assert {'embedding', 'collection_name', 'chunk_count', 'ready_at', 'attempts'} <= set(
        schemas['KnowledgeBaseVersion']['properties'])
    export = public['paths']['/v1/knowledge-bases/{id}/export']['get']
    assert export['operationId'] == 'exportKnowledgeBase' and '413' in export['responses']
    assert 'embedding' in schemas['KnowledgeBaseInput']['properties']


def test_rag_citation_contract_requires_verifiable_provenance():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    citation = public['components']['schemas']['Citation']
    assert set(citation['required']) == {
        'citation_id', 'chunk_id', 'knowledge_base_id', 'document_id', 'document_hash',
        'document_version', 'page', 'start', 'end'}
    assert 'citations' in public['components']['schemas']['RuntimeEvent']['properties']['payload']['description']


def test_agent_run_contract_state_cancel_and_ownership():
    public = json.loads((CONTRACTS / 'public.openapi.json').read_text())
    run = public['components']['schemas']['AgentRun']
    assert set(run['properties']['status']['enum']) == {
        'queued', 'running', 'waiting_approval', 'completed', 'failed', 'cancelled'}
    assert public['paths']['/v1/agent-runs/{id}/cancel']['post']['operationId'] == 'cancelAgentRun'
    assert '409' in public['paths']['/v1/agent-runs/{id}/cancel']['post']['responses']
    assert 'agent.cancelled' in public['components']['schemas']['RuntimeEvent']['properties']['event_type']['enum']
