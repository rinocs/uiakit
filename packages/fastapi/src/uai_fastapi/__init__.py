"""Host-authenticated sessions for the shared Universal AI Kit chat widget."""
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

__all__ = ['create_widget_router']


def _url(value: str, *, origin: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        valid = (
            isinstance(value, str) and value == value.strip()
            and not any(c.isspace() or ord(c) < 32 for c in value)
            and parsed.scheme in ('http', 'https') and parsed.hostname
            and parsed.username is None and parsed.password is None and '\\' not in value
            and not parsed.query and not parsed.fragment and '?' not in value and '#' not in value
            and (not origin or (not parsed.path and len(value.encode()) <= 500))
        )
        parsed.port  # Validate malformed port values at configuration time.
        if not valid:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Expected an absolute HTTP(S) URL without credentials, query or fragment') from None
    return value.rstrip('/')


def create_widget_router(
    *, client: httpx.AsyncClient, assistant_id: str, public_gateway_url: str,
    origin: str, subject_dependency: Callable, expires_in_seconds: int = 900,
) -> APIRouter:
    """Create POST /widget/session; the host owns client lifetime and authentication.

    The client's base_url identifies the gateway and its headers carry server
    credentials. The public URL may differ, e.g. an externally reachable proxy.
    """
    try:
        if str(UUID(assistant_id)) != assistant_id.lower():
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError('assistant_id must be a UUID') from None
    public_gateway_url = _url(public_gateway_url)
    origin = _url(origin, origin=True)
    if type(expires_in_seconds) is not int or not 60 <= expires_in_seconds <= 86400:
        raise ValueError('expires_in_seconds must be an integer between 60 and 86400')
    if not callable(subject_dependency):
        raise ValueError('subject_dependency must be an explicit authentication dependency')
    router = APIRouter()

    @router.post('/widget/session')
    async def session(request: Request, subject=Depends(subject_dependency)):
        if not isinstance(subject, str) or not subject.strip() or len(subject.encode()) > 200:
            raise HTTPException(401, 'Authentication required', headers={'Cache-Control': 'no-store'})
        if request.headers.getlist('origin') != [origin]:
            raise HTTPException(403, 'Origin forbidden', headers={'Cache-Control': 'no-store'})
        try:
            conversation_response = await client.post('/v1/conversations', json={'assistant_id': assistant_id}, follow_redirects=False)
            conversation_response.raise_for_status()
            conversation_id = conversation_response.json()['id']
            UUID(conversation_id)
            token_response = await client.post('/v1/widget/tokens', json={
                'assistant_id': assistant_id, 'conversation_id': conversation_id,
                'subject': subject, 'origin': origin, 'expires_in_seconds': expires_in_seconds,
            }, follow_redirects=False)
            token_response.raise_for_status()
            token = token_response.json()
            if not isinstance(token['token'], str) or not token['token'].startswith('uai_widget_'):
                raise ValueError
            expiry = datetime.fromisoformat(token['expires_at'].replace('Z', '+00:00'))
            if expiry.tzinfo is None:
                raise ValueError
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            raise HTTPException(502, 'Widget session unavailable', headers={'Cache-Control': 'no-store'}) from None
        return JSONResponse({
            'baseUrl': public_gateway_url, 'token': token['token'],
            'conversationId': conversation_id, 'expiresAt': token['expires_at'],
        }, headers={'Cache-Control': 'no-store'})

    return router
