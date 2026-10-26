import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from uai_fastapi import create_widget_router

ASSISTANT = '11111111-1111-4111-8111-111111111111'
CONVERSATION = '22222222-2222-4222-8222-222222222222'
ORIGIN = 'https://host.example'


def run_request(subject='user-1', origin=ORIGIN, upstream_status=201, body=None, failure=None):
    calls = []

    async def scenario():
        def upstream(request):
            calls.append((request.url.path, json.loads(request.content)))
            if failure == 'network':
                raise httpx.ConnectError('private-server-key')
            if failure == 'conversation':
                return httpx.Response(201, json={'id': 'private-server-key'})
            if failure == 'token' and request.url.path.endswith('tokens'):
                return httpx.Response(201, json={'token': 'private-server-key', 'expires_at': 'invalid'})
            if failure == 'json':
                return httpx.Response(201, text='private-server-key')
            if upstream_status != 201:
                return httpx.Response(upstream_status, text='private-server-key')
            if request.url.path.endswith('conversations'):
                return httpx.Response(201, json={'id': CONVERSATION})
            return httpx.Response(201, json={'token': 'uai_widget_secret', 'expires_at': '2026-10-26T12:00:00Z', 'created_by': 'private-server-key'})

        async def authenticate():
            if subject == 'unauthorized':
                raise HTTPException(401)
            return subject

        async with httpx.AsyncClient(base_url='https://internal.example', transport=httpx.MockTransport(upstream)) as client:
            app = FastAPI()
            app.include_router(create_widget_router(client=client, assistant_id=ASSISTANT, public_gateway_url='https://gateway.example', origin=ORIGIN, subject_dependency=authenticate))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as browser:
                return await browser.post('/widget/session', headers={} if origin is None else {'Origin': origin}, json=body or {})
    return asyncio.run(scenario()), calls


@pytest.mark.parametrize('subject', ['unauthorized', '', ' ', None, 123, 'x' * 201, 'é' * 101])
def test_authentication_rejects_without_upstream(subject):
    response, calls = run_request(subject=subject)
    assert response.status_code == 401
    assert calls == []


@pytest.mark.parametrize('origin', [None, 'null', 'https://evil.example', ORIGIN + '/'])
def test_origin_rejects_without_upstream(origin):
    response, calls = run_request(origin=origin)
    assert response.status_code == 403
    assert calls == []


def test_fixed_bindings_and_minimal_response():
    response, calls = run_request(body={'assistant_id': 'evil', 'conversation_id': 'evil', 'token': 'browser-token'})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert calls == [('/v1/conversations', {'assistant_id': ASSISTANT}), ('/v1/widget/tokens', {'assistant_id': ASSISTANT, 'conversation_id': CONVERSATION, 'subject': 'user-1', 'origin': ORIGIN, 'expires_in_seconds': 900})]
    assert response.json() == {'baseUrl': 'https://gateway.example', 'token': 'uai_widget_secret', 'conversationId': CONVERSATION, 'expiresAt': '2026-10-26T12:00:00Z'}


@pytest.mark.parametrize('status', [301, 401, 422, 500])
def test_upstream_failure_sanitized(status):
    response, _ = run_request(upstream_status=status)
    assert response.status_code == 502
    assert 'private-server-key' not in response.text
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('override', [{'assistant_id': 'bad'}, {'origin': 'null'}, {'origin': ORIGIN + '/'}, {'public_gateway_url': '//evil'}, {'public_gateway_url': 'https://user:secret@host'}, {'expires_in_seconds': 59}, {'expires_in_seconds': 86401}, {'expires_in_seconds': True}, {'subject_dependency': None}])
def test_configuration_rejected_early(override):
    config = dict(client=httpx.AsyncClient(), assistant_id=ASSISTANT, public_gateway_url='https://gateway.example', origin=ORIGIN, subject_dependency=lambda: 'user')
    config.update(override)
    with pytest.raises(ValueError):
        create_widget_router(**config)


@pytest.mark.parametrize('failure', ['network', 'conversation', 'token', 'json'])
def test_malformed_or_unreachable_upstream(failure):
    response, _ = run_request(failure=failure)
    assert response.status_code == 502
    assert 'private-server-key' not in response.text
