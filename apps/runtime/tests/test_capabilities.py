import asyncio
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from uai_core.capabilities import ModelDefinition
from uai_runtime.app import create_app
from uai_core.providers import ModelChunk


class Provider:
    async def stream(self, request):
        yield ModelChunk(text='Ciao')


def send(app, path, body=None, authorized=True):
    async def perform():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://runtime') as c:
            headers={'Authorization': 'Bearer internal-secret'} if authorized else {}
            return await (c.get(path,headers=headers) if body is None else c.post(path,json=body,headers=headers))
    return asyncio.run(perform())


def body():
    return dict(run_id=str(uuid4()),correlation_id=str(uuid4()),model='test',system_prompt='Prompt',
                messages=[dict(role='user',content='Hi')])


def test_catalog_is_authenticated_and_does_not_expose_provider_secrets():
    app=create_app('internal-secret',Provider())
    assert send(app,'/internal/v1/models',authorized=False).status_code==401
    result=send(app,'/internal/v1/models')
    assert result.status_code==200
    assert result.json()[0]['capabilities']==['chat','streaming']
    assert not {'api_key','base_url','secret_ref'} & result.json()[0].keys()


def test_missing_streaming_capability_rejected_before_provider():
    definition=ModelDefinition(id='test',provider='openai-compatible',capabilities={'chat'})
    app=create_app('internal-secret',Provider(),model_definition=definition)
    result=send(app,'/internal/v1/runs',body())
    assert result.status_code==422
    assert 'unsupported_capability' in result.text


def test_model_definition_is_immutable_and_rejects_unknown_capabilities():
    with pytest.raises(ValidationError):
        ModelDefinition(id='test',provider='openai-compatible',capabilities={'made_up'})
    definition=ModelDefinition(id='test',provider='openai-compatible',capabilities={'chat','streaming'})
    with pytest.raises(AttributeError):
        definition.capabilities.add('tool_calling')


def test_snapshot_mismatch_is_rejected():
    app=create_app('internal-secret',Provider())
    data=body()
    data['model_snapshot']={'id':'test','provider':'openai-compatible','capabilities':['chat','streaming'],
                            'max_output_tokens':999,'context_window':None}
    assert send(app,'/internal/v1/runs',data).status_code==409


def assistant_config():
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parents[3]/'packages/api-contract/fixtures/assistant-v1.json'
    return json.loads(path.read_text())


def test_assistant_snapshot_applies_limits_and_is_immutable():
    from uai_core.configuration import AssistantConfig
    config=assistant_config()
    snapshot=AssistantConfig(**config)
    config['limits']['max_output_chars']=999999
    assert snapshot.limits.max_output_chars==64000
    with pytest.raises(ValidationError):
        snapshot.version=2
    data=body();data['system_prompt']='Helpful';data['assistant']=assistant_config()
    data['assistant']['limits']['max_output_chars']=2
    result=send(create_app('internal-secret',Provider()),'/internal/v1/runs',data)
    assert result.status_code==200
    assert 'output_limit' in result.text


def test_snapshot_cannot_change_prompt_or_enable_future_capability():
    data=body();data['assistant']=assistant_config()
    assert send(create_app('internal-secret',Provider()),'/internal/v1/runs',data).status_code==422
    data['system_prompt']='Helpful';data['assistant']['tools']=['unauthorized']
    assert send(create_app('internal-secret',Provider()),'/internal/v1/runs',data).status_code==422


def test_with_messages_preserves_version_and_model_snapshot():
    from uai_core.configuration import AssistantConfig
    from uai_core.context import ExecutionContext,ExecutionAuthority,ExecutionLimits
    from uai_core.models import ModelInput,Message
    snapshot=AssistantConfig(**assistant_config())
    definition=ModelDefinition(id='test',capabilities={'chat','streaming'})
    context=ExecutionContext(run_id=uuid4(),correlation_id=uuid4(),authority=ExecutionAuthority(principal_id='operator'),limits=ExecutionLimits(),assistant=snapshot,model_definition=definition,model_input=ModelInput(model='test',system_prompt='Helpful',messages=(Message(role='user',content='Hi'),)))
    changed=context.with_messages((Message(role='user',content='New'),))
    assert changed.assistant==snapshot
    assert changed.model_definition==definition
    assert context.model_input.messages[0].content=='Hi'


def test_disabled_memory_does_not_pass_history_to_provider():
    data=body();data['system_prompt']='Helpful';data['assistant']=assistant_config()
    data['assistant']['memory']['conversation']=False
    data['messages'].insert(0,{'role':'assistant','content':'Old private turn'})
    assert send(create_app('internal-secret',Provider()),'/internal/v1/runs',data).status_code==422


def test_assistant_cannot_raise_global_runtime_output_limit():
    data=body();data['system_prompt']='Helpful';data['assistant']=assistant_config()
    app=create_app('internal-secret',Provider(),max_output_chars=2)
    result=send(app,'/internal/v1/runs',data)
    assert result.status_code==200
    assert 'output_limit' in result.text
    assert 'response.completed' not in result.text
