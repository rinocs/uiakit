"""Runtime-side mutating HTTP effect through approval + durable journal."""
import asyncio
import json
import os
import urllib.request
from uuid import UUID

from uai_runtime.approvals import arguments_digest
from uai_runtime.tool_executor import (DurableToolRunner, GatewayExecutionJournal,
                                       ToolExecutionRequest)
from uai_runtime.tools.connectors import ConnectorDefinition, ConnectorRegistry
from uai_runtime.tools.http import HTTPToolBinding, HTTPToolExecutor

ARGS = {'value': 'effect'}
CONNECTOR = ConnectorDefinition(id='mocktool', base_url='http://mock-tool:9100',
                                methods={'POST'}, paths=('/write',), timeout=3,
                                max_response_bytes=4096,
                                private_networks=('172.16.0.0/12', '10.0.0.0/8'))
HTTP = HTTPToolExecutor(ConnectorRegistry([CONNECTOR]))
BINDING = HTTPToolBinding(connector='mocktool', method='POST', path='/write')


async def main():
    journal = GatewayExecutionJournal(os.environ['GATEWAY_URL'],
                                      os.environ['INTERNAL_API_KEY'])
    request = ToolExecutionRequest(
        run_id=UUID(os.environ['MUTATION_RUN']), tool_id='example.write',
        tool_version='1.0.0', arguments_digest=arguments_digest(ARGS),
        approval_id=UUID(os.environ['MUTATION_APPROVAL']), risk_level='write',
        idempotency_key='mutation-e2e', max_attempts=1)
    runner = DurableToolRunner(journal)

    async def invoke():
        return await HTTP.execute(CONNECTOR, BINDING, ARGS)

    first = await runner.run(request, invoke)
    replay = await runner.run(request, invoke)
    assert first == replay == {'written': 'effect', 'duplicate': False}, (first, replay)
    with urllib.request.urlopen('http://mock-tool:9100/stats', timeout=5) as response:
        stats = json.loads(response.read().decode())
    assert stats['writes'] == 1 and stats['effects'] == ['effect'], stats

    req = urllib.request.Request(
        os.environ['GATEWAY_URL'] + '/v1/approvals/' + os.environ['MUTATION_APPROVAL'],
        headers={'Authorization': 'Bearer ' + os.environ['UAI_TEST_KEY']})
    with urllib.request.urlopen(req, timeout=5) as response:
        approval = json.loads(response.read().decode())
    assert approval['status'] == 'consumed', approval


asyncio.run(main())
print('Mutating HTTP tool, immutable approval, journal replay without duplicate effect: passed')
