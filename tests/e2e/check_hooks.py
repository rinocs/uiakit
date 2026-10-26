"""Validate metadata lifecycle recorded inside Docker, without exposing a new API."""
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text()
observations = [json.loads(line) for line in raw.splitlines()]
expected = json.loads(Path(sys.argv[2]).read_text())
assert all('text' not in e['payload'] and 'messages' not in e['payload'] for e in observations)
assert 'E2E directive:' not in raw and 'private fixture diagnostic' not in raw
for run_id, terminal in expected.items():
    events = [event for event in observations if event['run_id'] == run_id]
    kinds = [event['event_type'] for event in events]
    assert kinds == ['request.received', 'request.authorized', 'agent.started',
                     'context.building', 'context.ready', 'model.before',
                     'response.delta', 'model.after', terminal], kinds
    assert len({event['correlation_id'] for event in events}) == 1
    assert len({event['event_id'] for event in events}) == len(events)
    assert all(event['event_version'] == 1 for event in events)
print('E2E metadata lifecycle, terminal observations and replay isolation: passed')
