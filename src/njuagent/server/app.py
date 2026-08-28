"""FastAPI application for njuagent (M2: SSE streaming, approval, tree/file/pending APIs)."""

from __future__ import annotations

import asyncio
import difflib
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agent.client import DeepSeekClient
from ..agent.loop import AgentLoop
from ..agent.prompts import PLAN_MODE_PREFIX, build_main_prompt
from ..agent.session import Session
from ..agent.skills import load_skills
from ..approval import ApprovalGate, ApprovalMode
from ..config import Config
from ..store.persistence import SessionStore
from ..store.snapshots import PendingChanges
from ..tools import build_tool_registry
from ..tools.fs import list_entries, resolve
from .events import EventBus

STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    task_id: str


class StopRequest(BaseModel):
    task_id: str


class ApprovalRequest(BaseModel):
    approved: bool


class SettingsRequest(BaseModel):
    auto_approve: bool | None = None
    plan_mode: bool | None = None


class FileRequest(BaseModel):
    path: str
    content: str


class PendingAction(BaseModel):
    path: str | None = None
    all: bool = False


class EditMessageRequest(BaseModel):
    index: int
    content: str


class TaskState:
    def __init__(self) -> None:
        self.stop_event = asyncio.Event()
        self.bus = EventBus()


def _diff(previous: str, current: str) -> str:
    return "".join(
        difflib.unified_diff(
            previous.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )


class AgentApp:
    """Holds session-scoped shared state plus per-task state."""

    def __init__(self, workdir: str, config: Config) -> None:
        self.workdir = workdir
        self.config = config
        self.store = SessionStore(workdir)
        meta = self.store.load_meta()
        self.auto_approve = bool(meta.get("auto_approve", False))
        self.plan_mode = bool(meta.get("plan_mode", False))
        self.pending = PendingChanges(
            on_change=lambda: self.store.save_pending(self.pending.dump())
        )
        self.pending.restore(self.store.load_pending())
        self.approval = ApprovalGate(
            ApprovalMode.AUTO if self.auto_approve else ApprovalMode.REQUIRE
        )
        self.session = Session(workdir, build_main_prompt())
        loaded = self.store.load_messages()
        if loaded:
            if loaded[0].get("role") == "system":
                loaded[0] = {"role": "system", "content": build_main_prompt()}
            self.session.messages = loaded
        self.client = DeepSeekClient(config.api_key, config.base_url, config.model)
        self.registry = build_tool_registry(
            workdir, self.pending, client=self.client, approval=self.approval
        )
        self.tasks: dict[str, TaskState] = {}

    def _save_state(self) -> None:
        self.store.save_messages(self.session.messages)
        self.store.save_pending(self.pending.dump())

    def _refresh_system_prompt(self) -> None:
        """Rebuild the system prompt from the latest skill files."""
        prompt = build_main_prompt(skills=load_skills(self.workdir))
        if self.session.messages and self.session.messages[0].get("role") == "system":
            self.session.messages[0]["content"] = prompt
        else:
            self.session.messages.insert(0, {"role": "system", "content": prompt})

    def _save_settings(self) -> None:
        self.store.save_meta(
            {"auto_approve": self.auto_approve, "plan_mode": self.plan_mode}
        )

    def _sync_approval(self) -> None:
        self.approval.set_mode(
            ApprovalMode.AUTO if self.auto_approve else ApprovalMode.REQUIRE
        )

    def build_loop(self, task: TaskState) -> AgentLoop:
        return AgentLoop(
            self.session,
            self.client,
            self.registry,
            self.approval,
            self.pending,
            stop_event=task.stop_event,
            emit=task.bus.emit,
            on_state_change=self._save_state,
            context_limit=self.config.context_limit,
        )


def create_app(workdir: str, config: Config) -> FastAPI:
    app_state = AgentApp(workdir, config)
    app = FastAPI(title="njuagent")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/state")
    async def state() -> dict:
        return {
            "workdir": app_state.workdir,
            "messages": app_state.session.messages,
            "pending": app_state.pending.list_pending(),
            "auto_approve": app_state.auto_approve,
            "plan_mode": app_state.plan_mode,
            "ui_manifest": app_state.registry.manifest(),
        }

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        task_id = uuid.uuid4().hex
        task = TaskState()
        app_state.tasks[task_id] = task

        async def _run() -> None:
            try:
                app_state._refresh_system_prompt()
                message = req.message
                if app_state.plan_mode:
                    message = f"{PLAN_MODE_PREFIX}\n{message}"
                await app_state.build_loop(task).run(message)
            except Exception as exc:  # noqa: BLE001 - surface to UI
                task.bus.emit({"type": "error", "message": str(exc)})
            finally:
                task.bus.emit({"type": "ended"})
                task.bus.finish()

        asyncio.create_task(_run())
        return ChatResponse(task_id=task_id)

    @app.get("/api/stream/{task_id}")
    async def stream(task_id: str) -> StreamingResponse:
        task = app_state.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="unknown task")
        return StreamingResponse(task.bus.stream(), media_type="text/event-stream")

    @app.post("/api/stop")
    async def stop(req: StopRequest) -> dict:
        task = app_state.tasks.get(req.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="unknown task")
        task.stop_event.set()
        return {"ok": True}

    @app.post("/api/approval")
    async def approval(req: ApprovalRequest) -> dict:
        app_state.approval.resolve(req.approved)
        return {"ok": True}

    @app.get("/api/settings")
    async def get_settings() -> dict:
        return {"auto_approve": app_state.auto_approve, "plan_mode": app_state.plan_mode}

    @app.post("/api/settings")
    async def set_settings(req: SettingsRequest) -> dict:
        if req.auto_approve is not None:
            app_state.auto_approve = req.auto_approve
            app_state._sync_approval()
        if req.plan_mode is not None:
            app_state.plan_mode = req.plan_mode
        app_state._save_settings()
        return {"auto_approve": app_state.auto_approve, "plan_mode": app_state.plan_mode}

    @app.get("/api/list")
    async def list_dir_api(path: str = ".") -> dict:
        base = resolve(app_state.workdir, path)
        if not base.is_dir():
            raise HTTPException(status_code=404, detail="not a directory")
        entries = [
            {"name": name, "type": "dir" if is_dir else "file"}
            for name, is_dir in list_entries(base)
        ]
        return {"path": str(base), "entries": entries}

    @app.get("/api/file")
    async def get_file(path: str) -> dict:
        p = resolve(app_state.workdir, path)
        if not p.is_file():
            raise HTTPException(status_code=404, detail="not a file")
        content = p.read_text(encoding="utf-8", errors="replace")
        return {
            "path": str(p),
            "content": content,
            "pending": app_state.pending.is_pending(str(p)),
        }

    @app.post("/api/file")
    async def save_file(req: FileRequest) -> dict:
        p = resolve(app_state.workdir, req.path)
        if app_state.pending.is_pending(str(p)):
            raise HTTPException(
                status_code=409,
                detail="file has pending changes; accept or rollback first",
            )
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(req.content, encoding="utf-8")
        return {"ok": True}

    @app.get("/api/pending")
    async def pending() -> dict:
        files = []
        for path in app_state.pending.list_pending():
            previous = app_state.pending.snapshot_of(path) or ""
            current = Path(path).read_text(encoding="utf-8", errors="replace")
            files.append({"path": path, "diff": _diff(previous, current)})
        return {"files": files}

    @app.post("/api/messages/edit")
    async def edit_message(req: EditMessageRequest) -> dict:
        """Edit a past user message and drop everything after it (rewind).

        Only the conversation state is changed (no file side effects). Any
        unresolved pending changes must be resolved first.
        """
        if app_state.pending.list_pending():
            raise HTTPException(
                status_code=409,
                detail="resolve pending file changes (accept or rollback) first",
            )
        messages = app_state.session.messages
        if not 0 <= req.index < len(messages):
            raise HTTPException(status_code=404, detail="message index out of range")
        if messages[req.index].get("role") != "user":
            raise HTTPException(status_code=400, detail="only user messages can be edited")
        messages[req.index]["content"] = req.content
        del messages[req.index + 1 :]
        app_state._save_state()
        return {"ok": True}

    @app.post("/api/pending/accept")
    async def accept(req: PendingAction) -> dict:
        if req.all:
            app_state.pending.accept_all()
        elif req.path:
            app_state.pending.accept(req.path)
        else:
            raise HTTPException(status_code=400, detail="path or all required")
        return {"ok": True}

    @app.post("/api/pending/rollback")
    async def rollback(req: PendingAction) -> dict:
        if req.all:
            app_state.pending.rollback_all()
        elif req.path:
            app_state.pending.rollback(req.path)
        else:
            raise HTTPException(status_code=400, detail="path or all required")
        return {"ok": True}

    return app
