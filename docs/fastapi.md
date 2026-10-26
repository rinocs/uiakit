# FastAPI chat widget

`uai-fastapi` provides an authenticated same-origin session endpoint for the existing `<uai-chat>` Web Component. It creates a fresh gateway conversation and a short-lived token bound to your server-configured assistant, exact page origin and authenticated user. Browser message requests and SSE go directly to the gateway with that limited token.

## Run the repository example

Use Python 3.12+ and Node 20+. From the repository root:

```sh
npm --prefix packages/sdk-typescript ci
npm --prefix packages/sdk-typescript run build
npm --prefix packages/chat-widget ci
npm --prefix packages/chat-widget run build
python -m venv .venv
.venv/bin/pip install -e packages/fastapi 'uvicorn>=0.30,<1'
export UAI_GATEWAY_URL=http://localhost:8080
export UAI_PUBLIC_GATEWAY_URL=http://localhost:8080
export UAI_ASSISTANT_ID='<existing assistant UUID>'
export UAI_API_KEY='<server-side gateway API key>'
export WIDGET_ORIGIN=http://localhost:8000
export WIDGET_DEMO_USERNAME='<your demo username>'
export WIDGET_DEMO_PASSWORD='<your demo password>'
.venv/bin/uvicorn examples.fastapi.app:create_app --factory
```

Open `http://localhost:8000` and sign in with those credentials. All credential variables are required; the example supplies no default login. The HTTP Basic dependency gates both `/` and `/widget/session`. The gateway key must be authorized to create conversations and widget tokens for the configured assistant. Keep it exclusively on the server and configure secrets through your deployment's secret store.

Set **`UAI_WIDGET_ORIGINS=http://localhost:8000` on the gateway** and restart it as required by its configuration. This explicit allowlist authorizes the browser's direct message/SSE traffic. Use the exact scheme, hostname and port; `localhost` and `127.0.0.1` differ. `WIDGET_ORIGIN` must match the actual page origin with no trailing slash or path. Do not add permissive CORS middleware to the host session endpoint. The gateway already handles widget message CORS and authorization preflights.

The example serves built repository assets from `packages/chat-widget/dist` and `packages/sdk-typescript/dist`, with an import map and an external `/static/bootstrap.js`. Build both before startup. Frontend assets are deliberately not bundled in the Python wheel; deploy the shared assets through your application's asset pipeline for production. The example is a repository development example, not an installed application entry point.

## Integrate with an application

```python
import httpx
from fastapi import FastAPI, HTTPException, Request
from uai_fastapi import create_widget_router

async def authenticated_subject(request: Request) -> str:
    # Populate this from your application's verified session/auth middleware.
    user = getattr(request.state, 'user', None)
    if user is None:
        raise HTTPException(401, 'Authentication required')
    return str(user.id)

# Create this client in application setup and close it in application lifespan.
client = httpx.AsyncClient(
    base_url='https://gateway.internal',
    headers={'Authorization': 'Bearer <server-side key>'},
    timeout=30,
)
app = FastAPI()
app.include_router(create_widget_router(
    client=client,
    assistant_id='11111111-1111-4111-8111-111111111111',
    public_gateway_url='https://gateway.example.com',
    origin='https://app.example.com',
    subject_dependency=authenticated_subject,
    expires_in_seconds=900,
), prefix='/chat')
```

Call `connectChat(element, { sessionUrl: '/chat/widget/session' })` from your browser module. See `examples/fastapi/app.py` for a complete lifespan that closes the client. The client supplies gateway credentials and the internal gateway address; `public_gateway_url` is the browser-reachable address and may differ. Configure finite client timeouts.

The dependency must return a nonblank string of at most 200 UTF-8 bytes, matching the gateway limit. Authentication failures must raise an HTTP exception. The router refuses missing, `null`, duplicate or mismatched Origin headers before gateway requests. Browser request bodies cannot select an assistant, subject, conversation or token. Successful responses contain only `baseUrl`, `token`, `conversationId`, `expiresAt`, with `Cache-Control: no-store`. Gateway HTTP, transport and malformed-response errors become a sanitized 502 response.

TTL defaults to 900 seconds and must be an integer from 60 to 86400. Tokens remain in widget memory. On expiry or reconnect, start a new widget session to obtain a fresh conversation; automatic renewal, conversation history persistence and resuming an earlier conversation are outside this integration. Do not put the gateway key or widget token into markup, local storage or logs.

The host owns authentication, authorization to use the assistant, rate limiting and any session-specific CSRF controls. Use stable opaque subjects, enforce quotas on the session endpoint, and use HTTPS for both host and gateway in production (especially for Basic authentication). Adapt the example login to your real authentication system. Exact Origin enforcement complements your authentication and CSRF controls.

## Test

```sh
PYTHONPATH=packages/fastapi/src apps/runtime/.venv/bin/python -m pytest packages/fastapi/tests -q
```
