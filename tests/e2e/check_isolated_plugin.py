"""Container-isolated plugin: authenticated catalog, health, activation and removal."""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get('UAI_TEST_URL', 'http://127.0.0.1:8000')
KEY = os.environ.get('UAI_TEST_INTERNAL_KEY') or os.environ['INTERNAL_API_KEY']
PLUGIN = '/internal/v1/plugins/org.uai.isolated'


def request(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={'Authorization': 'Bearer ' + KEY,
                                          'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as response:
        return response.code, response.read().decode()


assert request('/internal/v1/plugins')[0] == 200
catalog = json.loads(request('/internal/v1/plugins')[1])
entry = next(item for item in catalog if item['manifest']['id'] == 'org.uai.isolated')
assert entry['manifest']['runtime'] == 'isolated_http'
assert entry['state'] == 'inactive'
assert request(PLUGIN + '/health')[0] == 200
if json.loads(request(PLUGIN + '/health')[1])['status'] != 'unavailable':
    raise AssertionError('inactive isolated plugin should be unavailable')

plugin_base = os.environ['ISOLATED_PLUGIN_URL'].rstrip('/')
for headers in ({'Authorization': 'Bearer wrong', 'X-UAI-Plugin-Protocol': '1'},
                {'Authorization': 'Bearer ' + os.environ['INTERNAL_API_KEY'],
                 'X-UAI-Plugin-Protocol': '1'}):
    try:
        urllib.request.urlopen(urllib.request.Request(plugin_base + '/v1/tools',
                                                     headers=headers), timeout=5)
        raise AssertionError('isolated plugin accepted an invalid connector token')
    except urllib.error.HTTPError as error:
        assert error.code == 401, error.code
try:
    urllib.request.urlopen(urllib.request.Request(
        plugin_base + '/v1/tools',
        headers={'Authorization': 'Bearer ' + os.environ['ISOLATED_PLUGIN_TOKEN']}), timeout=5)
    raise AssertionError('isolated plugin accepted a missing protocol version')
except urllib.error.HTTPError as error:
    assert error.code == 401, error.code
assert request(PLUGIN + '/activate', {})[0] == 204
tools = json.loads(request('/internal/v1/tools')[1])
tool = next(item for item in tools if item['id'] == 'org.uai.isolated.echo')
assert tool['executor'] == 'isolated' and tool['risk_level'] == 'read_only'
assert sorted(tool['permissions']) == ['connector:isolated_example', 'tools:execute']
health = json.loads(request(PLUGIN + '/health')[1])
assert health['status'] == 'ok', health
assert request(PLUGIN + '/deactivate', method='POST')[0] == 204
assert not any(item['id'] == 'org.uai.isolated.echo'
               for item in json.loads(request('/internal/v1/tools')[1]))
print('Isolated HTTP plugin catalog, auth, health, activation and removal: passed')
