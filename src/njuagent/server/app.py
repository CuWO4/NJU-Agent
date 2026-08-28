"""FastAPI application for njuagent (M1: minimal run endpoint)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent.client import DeepSeekClient
from ..agent.loop import AgentLoop
from ..agent.prompts import build_main_prompt
from ..agent.session import Session
from ..approval import ApprovalGate
from ..config import Config
from ..store.snapshots import PendingChanges
from ..tools import build_tool_registry

STATIC_DIR = Path(__file__).parent / "static"


class RunRequest(BaseModel):
    message: str


class RunResponse(BaseModel):
    result: str


def create_app(workdir: str, config: Config) -> FastAPI:
    pending = PendingChanges()
    approval = ApprovalGate()
    session = Session(workdir, build_main_prompt())
    registry = build_tool_registry(workdir, pending)
    client = DeepSeekClient(config.api_key, config.base_url, config.model)
    loop = AgentLoop(session, client, registry, approval, pending)

    app = FastAPI(title="njuagent")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/run", response_model=RunResponse)
    async def run(req: RunRequest) -> RunResponse:
        result = await loop.run(req.message)
        return RunResponse(result=result)

    return app
