import asyncio
import json
import logging
import secrets
import sys
import time
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.app.agents.tutor import Tutor
from backend.app.context.tools import Tools
from backend.app.context.workspace import Workspace
from backend.app.core.config import Settings
from backend.app.core.security import AccessBoundary
from backend.app.llm.codex_cli import CodexCliProvider
from backend.app.llm.hybrid import HybridProvider
from backend.app.llm.ollama import ChatProvider, OllamaProvider, ProviderError
from backend.app.memory.store import MemoryStore
from backend.app.permissions.actions import Permissions
from backend.app.proactive.events import Proactive
from backend.app.schemas.messages import (
    ApprovalDecision,
    ChatRequest,
    EditorEvent,
    ExerciseInput,
    ExerciseReview,
    FocusCommand,
    FocusReview,
    FocusStepsInput,
    MemoryInput,
    Observation,
    TerminalObservation,
    ToolInput,
)
from backend.app.skills.catalog import SkillCatalog


class Runtime:
    def __init__(self, settings: Settings, provider: ChatProvider, providers=None):
        self.settings = settings
        self.memory = MemoryStore(settings.database, settings.retention)
        self.workspace = Workspace(settings.projects)
        self.skills = SkillCatalog(settings.skills_dir)
        self.tutor = Tutor(provider, self.memory, settings, self.skills, self.workspace, providers)
        self.editors: dict[str, EditorEvent] = {}
        self.terminals: dict[str, TerminalObservation] = {}
        self.paused = False
        self.connections = 0
        self.tasks: set[asyncio.Task] = set()
        self.modes: dict[str, str] = {}
        self.focus: dict[str, dict] = {}
        self.proactive = Proactive(settings.proactive)
        self.permissions = Permissions()
        self.tools = Tools(
            self.workspace,
            self.memory,
            self.permissions,
            self.editors,
            self.terminals,
            lambda: self.paused,
            settings,
        )


def create_app(settings: Settings | None = None, provider: ChatProvider | None = None) -> FastAPI:
    settings = settings or Settings()
    providers = {}
    if provider is None:
        local = OllamaProvider(settings)
        online = CodexCliProvider(settings)
        providers = {"ollama": local, "codex": online}
        if settings.provider == "codex":
            provider = online
        elif settings.provider == "hybrid":
            provider = HybridProvider(local, online)
        else:
            provider = local
    state = Runtime(settings, provider, providers)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        for task in list(state.tasks):
            task.cancel()
        await asyncio.gather(*state.tasks, return_exceptions=True)
        for item in providers.values() if providers else [provider]:
            await item.close()
        await asyncio.to_thread(state.memory.close)

    app = FastAPI(
        title="CodePet AI", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.runtime = state
    app.add_middleware(AccessBoundary, token=settings.token.get_secret_value())

    def project(name: str) -> None:
        try:
            state.workspace.root(name)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc

    @app.get("/health")
    async def health():
        return {
            "v": 1,
            "status": "ok",
            "paused": state.paused,
            "retention": settings.retention,
            "projects": list(settings.projects),
            "roots": {k: str(v) for k, v in settings.projects.items()},
            "screen": "enabled" if settings.screen_capture else "disabled",
            "terminal": "explicit_observation",
        }

    @app.get("/v1/model")
    async def model():
        try:
            return {"v": 1, "model": await provider.discover()}
        except (httpx.HTTPError, ValueError, KeyError, ProviderError) as exc:
            raise HTTPException(
                503, "Configured provider unavailable; check Codex login or Ollama model"
            ) from exc

    @app.get("/ready")
    async def ready():
        try:
            model_name = await provider.discover()
        except (httpx.HTTPError, OSError, ValueError, KeyError, ProviderError) as exc:
            return JSONResponse(
                status_code=503,
                content={"v": 1, "status": "not_ready", "reason": type(exc).__name__},
            )
        return {"v": 1, "status": "ready", "model": model_name}

    @app.get("/v1/skills")
    async def skills():
        return {"v": 1, "items": [skill.summary() for skill in state.skills.list()]}

    @app.post("/v1/observation")
    async def observation(payload: Observation):
        state.paused = payload.paused
        state.editors.clear()
        state.proactive.reset()
        if state.paused:
            tasks = list(state.tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return {"v": 1, "paused": state.paused}

    async def focus_snapshot(name: str) -> dict:
        current = state.focus.get(name)
        if current is None:
            return {"v": 1, "status": "idle", "project": name}
        snapshot = dict(current)
        if snapshot["status"] == "running":
            remaining = max(0, snapshot["ends_at"] - time.monotonic())
            snapshot["remaining_seconds"] = int(remaining + 0.999)
            if remaining <= 0:
                if not snapshot.get("recorded"):
                    await asyncio.to_thread(state.memory.record_focus, name, snapshot)
                    snapshot["recorded"] = True
                snapshot["status"] = "break"
                snapshot["phase"] = "break"
                snapshot["ends_at"] = time.monotonic() + snapshot["break_minutes"] * 60
                snapshot["remaining_seconds"] = snapshot["break_minutes"] * 60
                state.focus[name] = snapshot
        elif snapshot["status"] == "break":
            snapshot["remaining_seconds"] = max(
                0, int(snapshot["ends_at"] - time.monotonic() + 0.999)
            )
        return snapshot

    async def record_focus_if_needed(name: str, session: dict) -> None:
        if not session.get("recorded"):
            await asyncio.to_thread(state.memory.record_focus, name, session)
            session["recorded"] = True

    @app.get("/v1/learning/{name}")
    async def learning_progress(name: str):
        project(name)
        notes = await asyncio.to_thread(state.memory.notes, name)
        stats = await asyncio.to_thread(state.memory.focus_stats, name)
        return {
            "v": 1,
            "notes": notes,
            "focus": stats,
            "active_focus": await focus_snapshot(name),
            "exercises_due": await asyncio.to_thread(state.memory.list_exercises, name, True),
            "metrics": await asyncio.to_thread(state.memory.metric_summary, name),
        }

    @app.get("/v1/metrics/{name}")
    async def metrics(name: str, days: int = 14):
        project(name)
        return {"v": 1, **await asyncio.to_thread(state.memory.metric_summary, name, days)}

    @app.get("/v1/focus/{name}")
    async def focus_status(name: str):
        project(name)
        return await focus_snapshot(name)

    @app.get("/v1/focus/{name}/history")
    async def focus_history(name: str):
        project(name)
        return {"v": 1, "items": await asyncio.to_thread(state.memory.focus_history, name)}

    @app.get("/v1/focus/{name}/steps")
    async def focus_steps(name: str, goal: str):
        project(name)
        return {"v": 1, "steps": await asyncio.to_thread(state.memory.get_focus_steps, name, goal)}

    @app.put("/v1/focus/{name}/steps")
    async def save_focus_steps(name: str, payload: FocusStepsInput):
        project(name)
        goal = payload.goal.strip()
        cleaned = [{"text": step.text.strip(), "done": step.done} for step in payload.steps]
        return {"v": 1, "steps": await asyncio.to_thread(state.memory.save_focus_steps, name, goal, cleaned)}

    @app.post("/v1/focus/{name}")
    async def focus_command(name: str, payload: FocusCommand):
        project(name)
        now = time.monotonic()
        current = await focus_snapshot(name)
        if payload.action == "start":
            goal = payload.goal.strip()
            if not goal:
                raise HTTPException(422, "Defina uma meta pequena para começar")
            state.focus[name] = {
                "v": 1,
                "project": name,
                "status": "running",
                "phase": "focus",
                "goal": goal,
                "focus_minutes": payload.focus_minutes,
                "break_minutes": payload.break_minutes,
                "started_at": now,
                "started_at_wall": datetime.now(UTC).isoformat(),
                "ends_at": now + payload.focus_minutes * 60,
                "completed_sessions": current.get("completed_sessions", 0),
            }
            await asyncio.to_thread(state.memory.record_metric, name, "focus_started")
        elif payload.action == "pause":
            if current.get("status") != "running":
                raise HTTPException(409, "Nenhuma sessão de foco em andamento")
            current["status"] = "paused"
            current["remaining_seconds"] = max(0, int(current["ends_at"] - now + 0.999))
            state.focus[name] = current
        elif payload.action == "resume":
            if current.get("status") != "paused":
                raise HTTPException(409, "A sessão não está pausada")
            current["status"] = "running"
            current["phase"] = "focus"
            current["ends_at"] = now + current["remaining_seconds"]
            state.focus[name] = current
        elif payload.action == "complete":
            if current.get("status") not in {"running", "paused", "break"}:
                raise HTTPException(409, "Nenhuma sessão ativa para concluir")
            current["status"] = "completed"
            await record_focus_if_needed(name, current)
            await asyncio.to_thread(state.memory.record_metric, name, "focus_completed")
            current["completed_sessions"] = current.get("completed_sessions", 0) + 1
            current["remaining_seconds"] = 0
            state.focus[name] = current
        elif payload.action == "cancel":
            state.focus.pop(name, None)
        return await focus_snapshot(name)

    @app.post("/v1/focus/{name}/review")
    async def focus_review(name: str, payload: FocusReview):
        project(name)
        current = await focus_snapshot(name)
        goal = str(current.get("goal", "")).strip()
        if not goal:
            raise HTTPException(409, "Nenhuma sessão de foco para revisar")
        reviewed = await asyncio.to_thread(
            state.memory.review_focus, name, goal, payload.outcome, payload.next_step
        )
        if not reviewed:
            raise HTTPException(404, "Sessão de foco não encontrada")
        await asyncio.to_thread(state.memory.add, name, "focus_outcome",
                                f"Meta: {goal}\nResultado: {payload.outcome}\nPróximo passo: {payload.next_step}")
        await asyncio.to_thread(state.memory.record_metric, name, "focus_reviewed")
        return {"v": 1, "reviewed": True}

    @app.post("/v1/editor")
    async def editor(payload: EditorEvent):
        project(payload.project)
        if state.paused:
            return {"v": 1, "status": "paused"}
        try:
            state.workspace.path(payload.project, payload.path)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        state.editors[payload.project] = payload
        suggestion = state.proactive.observe(payload, state.modes.get(payload.project, "tutor"))
        return {"v": 1, "status": "accepted", "suggestion": suggestion}

    @app.post("/v1/terminal")
    async def terminal(payload: TerminalObservation):
        project(payload.project)
        if state.paused:
            return {"v": 1, "status": "paused"}
        state.terminals[payload.project] = payload
        return {"v": 1, "status": "accepted"}

    @app.get("/v1/memory/{name}")
    async def memory_list(name: str):
        project(name)
        return {"v": 1, "items": await asyncio.to_thread(state.memory.list, name)}

    @app.get("/v1/memory/{name}/export")
    async def memory_export(name: str):
        project(name)
        return {
            "v": 1,
            "project": name,
            "items": await asyncio.to_thread(state.memory.export, name),
        }

    @app.get("/v1/memory/{name}/search")
    async def memory_search(name: str, q: str):
        project(name)
        if not q.strip():
            raise HTTPException(422, "Informe um termo de busca")
        return {
            "v": 1,
            "items": await asyncio.to_thread(state.memory.search, name, q),
        }

    @app.post("/v1/memory/{name}")
    async def memory_add(name: str, payload: MemoryInput):
        project(name)
        if not settings.retention:
            raise HTTPException(409, "Retention disabled")
        return {
            "v": 1,
            "id": await asyncio.to_thread(state.memory.add, name, payload.kind, payload.content),
        }

    @app.put("/v1/memory/{name}/{identity}")
    async def memory_edit(name: str, identity: int, payload: MemoryInput):
        project(name)
        changed = await asyncio.to_thread(
            state.memory.edit, name, identity, payload.kind, payload.content
        )
        if not changed:
            raise HTTPException(404, "Memory not found")
        return {"v": 1, "updated": True}

    @app.delete("/v1/memory/{name}")
    async def memory_clear(name: str):
        project(name)
        return {"v": 1, "deleted": await asyncio.to_thread(state.memory.remove, name)}

    @app.delete("/v1/memory/{name}/{identity}")
    async def memory_remove(name: str, identity: int):
        project(name)
        return {"v": 1, "deleted": await asyncio.to_thread(state.memory.remove, name, identity)}

    @app.get("/v1/exercises/{name}")
    async def exercises_list(name: str, due_only: bool = False):
        project(name)
        return {
            "v": 1,
            "items": await asyncio.to_thread(state.memory.list_exercises, name, due_only),
        }

    @app.post("/v1/exercises/{name}")
    async def exercise_add(name: str, payload: ExerciseInput):
        project(name)
        if not settings.retention:
            raise HTTPException(409, "Retention disabled")
        identity = await asyncio.to_thread(
            state.memory.add_exercise, name, payload.prompt, payload.answer, payload.topic
        )
        return {"v": 1, "id": identity}

    @app.post("/v1/exercises/{name}/{identity}/review")
    async def exercise_review(name: str, identity: int, payload: ExerciseReview):
        project(name)
        reviewed = await asyncio.to_thread(
            state.memory.review_exercise, name, identity, payload.rating
        )
        if not reviewed:
            raise HTTPException(404, "Exercise not found")
        return {"v": 1, "reviewed": True}

    @app.delete("/v1/exercises/{name}/{identity}")
    async def exercise_remove(name: str, identity: int):
        project(name)
        removed = await asyncio.to_thread(state.memory.remove_exercise, name, identity)
        if not removed:
            raise HTTPException(404, "Exercise not found")
        return {"v": 1, "deleted": True}

    @app.post("/v1/tools")
    async def tool(payload: ToolInput):
        project(payload.project)
        try:
            return await state.tools.execute(payload)
        except (ValueError, OSError, UnicodeError) as exc:
            raise HTTPException(
                400, "Tool rejected input or could not access the authorized resource"
            ) from exc
        except TimeoutError as exc:
            raise HTTPException(408, "Tool timeout") from exc

    @app.get("/v1/approvals/{identity}")
    async def inspect_approval(identity: UUID):
        state.permissions.prune()
        entry = state.permissions.pending.get(str(identity))
        if entry is None:
            raise HTTPException(404, "Approval expired or not found")
        return {
            "v": 1,
            "project": entry.project,
            "cwd": str(state.workspace.root(entry.project)),
            "command": [sys.executable, "-m", "pytest", "-q"],
            "approved": entry.approved,
        }

    @app.post("/v1/approvals/{identity}")
    async def approve(identity: UUID, payload: ApprovalDecision):
        if not state.permissions.decide(str(identity), payload.approved):
            raise HTTPException(404, "Approval expired or not found")
        return {"v": 1, "approved": payload.approved}

    @app.websocket("/v1/chat")
    async def chat(socket: WebSocket):
        if state.connections >= settings.max_connections:
            await socket.close(code=1013)
            return
        state.connections += 1
        generation: asyncio.Task | None = None
        send_lock = asyncio.Lock()

        async def send(kind: str, request_id: str = "", **data):
            async with send_lock:
                await socket.send_json({"v": 1, "type": kind, "request_id": request_id, **data})

        async def generate(request: ChatRequest):
            identity = str(request.request_id)
            started = time.perf_counter()
            first_token_ms = None
            try:
                await send("queued", identity)
                context = (
                    state.editors.get(request.project)
                    if request.use_editor and not state.paused
                    else None
                )
                await send(
                    "state",
                    identity,
                    state="thinking",
                    provider=request.provider if request.provider != "default" else settings.provider,
                    skills=state.tutor.selected_skill_ids(request),
                )
                async for token in state.tutor.stream(
                    request, context.model_dump() if context else None
                ):
                    if first_token_ms is None:
                        first_token_ms = round((time.perf_counter() - started) * 1000)
                    await send("token", identity, content=token)
                await send("done", identity)
                elapsed_ms = str(round((time.perf_counter() - started) * 1000))
                await asyncio.to_thread(state.memory.record_metric, request.project, "chat_completed", elapsed_ms)
                if first_token_ms is not None:
                    await asyncio.to_thread(state.memory.record_metric, request.project, "chat_first_token", str(first_token_ms))
            except asyncio.CancelledError:
                with suppress(WebSocketDisconnect, RuntimeError):
                    await send("cancelled", identity)
                raise
            except Exception as exc:
                await asyncio.to_thread(state.memory.record_metric, request.project, "chat_failed", type(exc).__name__)
                logging.getLogger("codepet").warning("Generation failed: %s", type(exc).__name__)
                with suppress(WebSocketDisconnect, RuntimeError):
                    await send(
                        "error",
                        identity,
                        message=(
                            "O Codex não respondeu. Confira a conexão e o login com codex login."
                            if request.provider == "codex" else
                            "O DeepHat local não respondeu. Confira o Ollama e o modelo instalado."
                            if request.provider == "ollama" else
                            "O modelo configurado não respondeu. Confira o provider e os logs do backend."
                        ),
                    )

        try:
            await socket.accept()
            raw = await asyncio.wait_for(socket.receive_text(), timeout=5)
            auth = json.loads(raw) if len(raw) <= 2048 else {}
            if (
                not isinstance(auth, dict)
                or auth.get("v") != 1
                or auth.get("type") != "auth"
                or not isinstance(auth.get("token"), str)
                or not secrets.compare_digest(
                    auth["token"].encode(), settings.token.get_secret_value().encode()
                )
            ):
                await socket.close(code=1008)
                return
            await send("ready")
            last_request = 0.0
            while True:
                raw = await socket.receive_text()
                if len(raw) > 16384:
                    await socket.close(code=1009)
                    break
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict) and data == {"v": 1, "type": "cancel"}:
                        if generation and not generation.done():
                            generation.cancel()
                            await asyncio.gather(generation, return_exceptions=True)
                        continue
                    request = ChatRequest.model_validate(data)
                    state.workspace.root(request.project)
                    if request.skill and request.skill != "auto":
                        state.skills.get(request.skill)
                    if generation and not generation.done():
                        await send(
                            "error",
                            str(request.request_id),
                            message="One request per connection at a time",
                        )
                        continue
                    now = asyncio.get_running_loop().time()
                    if now - last_request < 1:
                        await send(
                            "error", str(request.request_id), message="Please wait before retrying"
                        )
                        continue
                    last_request = now
                    state.modes[request.project] = request.mode
                    generation = asyncio.create_task(generate(request))
                    state.tasks.add(generation)
                    generation.add_done_callback(state.tasks.discard)
                except (ValidationError, ValueError, TypeError):
                    await send("error", message="Invalid v1 request or unauthorized project")
        except (WebSocketDisconnect, TimeoutError, json.JSONDecodeError, RuntimeError):
            pass
        finally:
            if generation:
                generation.cancel()
                await asyncio.gather(generation, return_exceptions=True)
            state.connections -= 1

    return app


def run() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "backend.app.main:create_app",
        factory=True,
        host="127.0.0.1",
        port=8765,
        ws_max_size=16384,
        ws_max_queue=8,
        access_log=False,
    )


if __name__ == "__main__":
    run()
