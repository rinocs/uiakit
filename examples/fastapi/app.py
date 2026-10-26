"""Run from the repository root: uvicorn examples.fastapi.app:create_app --factory."""
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from uai_fastapi import create_widget_router


def create_app() -> FastAPI:
    # No default credentials: missing secrets/configuration fail startup.
    username = os.environ['WIDGET_DEMO_USERNAME']
    password = os.environ['WIDGET_DEMO_PASSWORD']
    api_key = os.environ['UAI_API_KEY']
    if not username or not password or not api_key:
        raise ValueError('Demo credentials and UAI_API_KEY must be nonempty')
    client = httpx.AsyncClient(
        base_url=os.environ['UAI_GATEWAY_URL'],
        headers={'Authorization': f'Bearer {api_key}'}, timeout=30,
    )
    security = HTTPBasic()

    async def subject(credentials: HTTPBasicCredentials = Depends(security)) -> str:
        valid_user = secrets.compare_digest(credentials.username.encode(), username.encode())
        valid_password = secrets.compare_digest(credentials.password.encode(), password.encode())
        if not (valid_user and valid_password):
            raise HTTPException(401, 'Authentication required', headers={'WWW-Authenticate': 'Basic'})
        return credentials.username

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await client.aclose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(create_widget_router(
        client=client, assistant_id=os.environ['UAI_ASSISTANT_ID'],
        public_gateway_url=os.environ['UAI_PUBLIC_GATEWAY_URL'],
        origin=os.environ['WIDGET_ORIGIN'], subject_dependency=subject,
    ))
    root = Path(__file__).resolve().parents[2]
    app.mount('/assets/widget', StaticFiles(directory=root / 'packages/chat-widget/dist'), name='widget')
    app.mount('/assets/sdk', StaticFiles(directory=root / 'packages/sdk-typescript/dist'), name='sdk')
    app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')

    @app.get('/', dependencies=[Depends(subject)], include_in_schema=False)
    async def index():
        return FileResponse(Path(__file__).parent / 'static/index.html', headers={'Cache-Control': 'no-store'})

    return app
