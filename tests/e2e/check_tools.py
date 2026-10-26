"""Public tool metadata and explicit credential scopes against real services."""
import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.environ['UAI_TEST_URL']
KEY = os.environ['UAI_TEST_KEY']


def request(path, body=None, *, key=KEY, method=None):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    req = Request(BASE + path, method=method, headers=headers,
                  data=json.dumps(body).encode() if body is not None else None)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read().decode()
    except HTTPError as response:
        return response.code, response.read().decode()


assert request('/v1/tools',key='')[0] == 401
status, raw = request('/v1/tools')
assert status == 200
catalog = json.loads(raw)
assert any(item['id'] == 'builtin.text_stats' for item in catalog)
assert any(item['id'] == 'mocktool.read' for item in catalog)
assert not any({'handler','module','api_key','base_url'} & item.keys() for item in catalog)
assert catalog[0]['risk_level'] == 'read_only' and catalog[0]['retry_policy'] == 'never'
assert catalog[0]['input_schema']['properties']['text']['type'] == 'string'
status, raw = request('/v1/credentials',{'role':'reader','scopes':['tools:read']})
assert status == 201
reader = json.loads(raw)['api_key']
assert request('/v1/tools',key=reader)[0] == 200
status, raw = request('/v1/credentials',{'role':'reader','scopes':['models:read']})
assert status == 201
assert request('/v1/tools',key=json.loads(raw)['api_key'])[0] == 403
assert request('/v1/tools',{'python':'arbitrary code'},method='POST')[0] in (404,405)
print('E2E tool catalog, credential scopes and absence of code installation: passed')
