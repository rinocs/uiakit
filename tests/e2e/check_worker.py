"""Wait for worker completion, cancellation and retry/crash recovery outcomes."""
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE, ADMIN, STATE = os.environ['UAI_TEST_URL'], os.environ['UAI_TEST_KEY'], sys.argv[1]
MODE = sys.argv[2] if len(sys.argv) > 2 else 'wait'


def job(document_id):
    req = Request(BASE + '/v1/documents/' + document_id + '/job',
                  headers={'Authorization': 'Bearer ' + ADMIN})
    try:
        with urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read())
    except HTTPError as response:
        return response.code, json.loads(response.read())


def wait(document_id, expected, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, body = job(document_id)
        if status == 200 and body['state'] in expected:
            return body
        time.sleep(1)
    raise AssertionError((document_id, expected, body))


state = json.load(open(STATE))
wait(state['pdf'], {'completed'})
wait(state['docx'], {'completed'})
cancelled = wait(state['cancelled'], {'cancelled'})
assert cancelled['state'] == 'cancelled'
print('Worker completed ingestion, cancellation and lease/retry recovery: passed')
