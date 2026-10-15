import os
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect


def payload():
    return {
        "v": 1,
        "type": "chat",
        "request_id": str(uuid4()),
        "session": str(uuid4()),
        "project": "demo",
        "prompt": "Explique o código",
        "use_editor": True,
    }


def test_auth_origin_host_and_size(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.get("/health", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get("/health", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 403
    assert client.post("/v1/editor", content=b"x" * 65537).status_code == 413
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(
            "ws://127.0.0.1:8765/v1/chat", headers={"Origin": "https://evil.example"}
        ),
    ):
        pass


def test_stream_and_persist(client, provider):
    event = {
        "project": "demo",
        "path": "main.py",
        "language": "python",
        "selection": "print('hello')",
    }
    assert client.post("/v1/editor", json=event).status_code == 200
    request = payload()
    with client.websocket_connect("ws://127.0.0.1:8765/v1/chat") as ws:
        ws.send_json({"v": 1, "type": "auth", "token": "t" * 48})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json(request)
        events = []
        while True:
            item = ws.receive_json()
            events.append(item)
            if item["type"] in {"done", "error"}:
                break
        assert events[-1]["type"] == "done"
        assert next(item for item in events if item["type"] == "state")["skills"] == [
            "ponytail",
            "caveman",
            "graphify",
        ]
        assert (
            "".join(item["content"] for item in events if item["type"] == "token") == "Olá, mundo!"
        )
    assert "main.py" in provider.messages[1]["content"]
    assert all(
        f"SKILL ATIVA: {name}" in provider.messages[0]["content"]
        for name in ("Ponytail", "Caveman", "Graphify (relatório)")
    )
    assert len(client.get("/v1/memory/demo").json()["items"]) == 2
    assert client.get("/v1/memory/other").json()["items"] == []


def test_skill_listing_and_selection(client, provider):
    skills = client.get("/v1/skills").json()["items"]
    assert {item["id"] for item in skills} >= {
        "explain-code",
        "debug-error",
        "ponytail",
        "caveman",
        "graphify",
    }
    request = payload()
    request["skill"] = "debug-error"
    with client.websocket_connect("ws://127.0.0.1:8765/v1/chat") as ws:
        ws.send_json({"v": 1, "type": "auth", "token": "t" * 48})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json(request)
        while ws.receive_json()["type"] != "done":
            pass
    assert "SKILL ATIVA" in provider.messages[0]["content"]
    assert "erro ou diagnóstico observado" in provider.messages[0]["content"]


def test_pause_discards_context_and_rejects_new_events(client, app):
    event = {"project": "demo", "path": "main.py", "language": "python"}
    client.post("/v1/editor", json=event)
    assert app.state.runtime.editors
    assert client.post("/v1/observation", json={"paused": True}).status_code == 200
    assert not app.state.runtime.editors
    assert client.post("/v1/editor", json=event).json()["status"] == "paused"
    assert not app.state.runtime.editors


def test_focus_mode_has_small_goal_and_lifecycle(client):
    missing = client.post("/v1/focus/demo", json={"action": "start"})
    assert missing.status_code == 422

    started = client.post(
        "/v1/focus/demo",
        json={"action": "start", "goal": "Escrever o primeiro teste", "focus_minutes": 15},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "running"
    assert started.json()["goal"] == "Escrever o primeiro teste"

    paused = client.post("/v1/focus/demo", json={"action": "pause"})
    assert paused.json()["status"] == "paused"
    resumed = client.post("/v1/focus/demo", json={"action": "resume"})
    assert resumed.json()["status"] == "running"
    completed = client.post("/v1/focus/demo", json={"action": "complete"})
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_sessions"] == 1
    progress = client.get("/v1/learning/demo").json()
    assert progress["focus"]["sessions"] == 1
    assert progress["focus"]["minutes"] == 15


def test_focus_mode_is_available_to_chat(client, provider):
    request = payload()
    request["mode"] = "focus"
    request["prompt"] = "Estou travado; qual é o próximo passo?"
    with client.websocket_connect("ws://127.0.0.1:8765/v1/chat") as ws:
        ws.send_json({"v": 1, "type": "auth", "token": "t" * 48})
        assert ws.receive_json()["type"] == "ready"
        ws.send_json(request)
        while ws.receive_json()["type"] != "done":
            pass
    assert "anti-procrastinação" in provider.messages[0]["content"]


def test_memory_crud_and_isolation(client):
    result = client.post("/v1/memory/demo", json={"kind": "difficulty", "content": "Recursão"})
    identity = result.json()["id"]
    assert (
        client.put(
            f"/v1/memory/other/{identity}", json={"kind": "topic", "content": "x"}
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/v1/memory/demo/{identity}", json={"kind": "topic", "content": "Recursão revisada"}
        ).status_code
        == 200
    )
    assert client.get("/v1/memory/demo/export").json()["items"][0]["content"] == "Recursão revisada"
    assert client.delete(f"/v1/memory/demo/{identity}").json()["deleted"] == 1


def test_memory_search_exercises_and_spaced_review(client):
    client.post(
        "/v1/memory/demo", json={"kind": "topic", "content": "Árvores binárias e recursão"}
    )
    search = client.get("/v1/memory/demo/search", params={"q": "recursão"})
    assert search.status_code == 200
    assert search.json()["items"][0]["kind"] == "topic"

    created = client.post(
        "/v1/exercises/demo",
        json={"prompt": "O que é recursão?", "answer": "Uma função que chama a si mesma", "topic": "funções"},
    )
    assert created.status_code == 200
    identity = created.json()["id"]
    due = client.get("/v1/exercises/demo", params={"due_only": True}).json()["items"]
    assert any(item["id"] == identity for item in due)
    assert client.post(f"/v1/exercises/demo/{identity}/review", json={"rating": 5}).status_code == 200
    current = client.get("/v1/exercises/demo").json()["items"]
    reviewed = next(item for item in current if item["id"] == identity)
    assert reviewed["repetitions"] == 1
    assert client.delete(f"/v1/exercises/demo/{identity}").json()["deleted"] is True


def test_terminal_observation_and_screen_opt_in(client):
    payload = {"project": "demo", "command": "pytest -q", "output": "1 passed"}
    assert client.post("/v1/terminal", json=payload).status_code == 200
    result = client.post("/v1/tools", json={"name": "get_terminal_output", "project": "demo"})
    assert result.json()["data"]["output"] == "1 passed"
    screen = client.post("/v1/tools", json={"name": "get_screen_context", "project": "demo"})
    assert screen.json()["status"] == "unavailable"


def test_test_execution_requires_approval(client, monkeypatch):
    calls = []

    async def command(argv, cwd, deadline_seconds=30):
        calls.append(argv)
        return {"status": "completed", "exit_code": 0, "output": "1 passed"}

    monkeypatch.setattr("backend.app.context.tools.command", command)
    request = {"name": "run_project_tests", "project": "demo"}
    result = client.post("/v1/tools", json=request).json()
    assert result["status"] == "approval_required" and not calls
    identity = result["approval_id"]
    assert client.post(f"/v1/approvals/{identity}", json={"approved": True}).status_code == 200
    request["approval_id"] = identity
    assert client.post("/v1/tools", json=request).json()["exit_code"] == 0
    assert len(calls) == 1
    assert client.post("/v1/tools", json=request).json()["status"] == "approval_required"
    assert len(calls) == 1


def test_bad_websocket_auth(client):
    with client.websocket_connect("ws://127.0.0.1:8765/v1/chat") as ws:
        ws.send_json({"v": 1, "type": "auth", "token": "bad"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_cancellation_releases_inference_and_does_not_retain_partial(client, app):
    import asyncio

    class BlockFirst:
        calls = 0
        active = 0
        maximum = 0

        async def stream(self, messages):
            self.calls += 1
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                yield "start"
                if self.calls == 1:
                    await asyncio.Event().wait()
            finally:
                self.active -= 1

    provider = BlockFirst()
    app.state.runtime.tutor.provider = provider
    with (
        client.websocket_connect("ws://127.0.0.1:8765/v1/chat") as first,
        client.websocket_connect("ws://127.0.0.1:8765/v1/chat") as second,
    ):
        for ws in (first, second):
            ws.send_json({"v": 1, "type": "auth", "token": "t" * 48})
            ws.receive_json()
        first.send_json(payload())
        while first.receive_json()["type"] != "token":
            pass
        second.send_json(payload())
        assert second.receive_json()["type"] == "queued"
        first.send_json({"v": 1, "type": "cancel"})
        assert first.receive_json()["type"] == "cancelled"
        while second.receive_json()["type"] != "done":
            pass
    assert provider.calls == 2 and provider.maximum == 1
    assert len(client.get("/v1/memory/demo").json()["items"]) == 2


def test_pause_cancels_running_generation(client, app):
    import asyncio

    class Blocking:
        async def stream(self, messages):
            yield "partial"
            await asyncio.Event().wait()

    app.state.runtime.tutor.provider = Blocking()
    with client.websocket_connect("ws://127.0.0.1:8765/v1/chat") as ws:
        ws.send_json({"v": 1, "type": "auth", "token": "t" * 48})
        ws.receive_json()
        ws.send_json(payload())
        while ws.receive_json()["type"] != "token":
            pass
        assert client.post("/v1/observation", json={"paused": True}).status_code == 200
        assert ws.receive_json()["type"] == "cancelled"
    assert client.get("/v1/memory/demo").json()["items"] == []


def test_memory_survives_new_store_instance(settings):
    from backend.app.memory.store import MemoryStore

    first = MemoryStore(settings.database, True)
    first.add("demo", "difficulty", "Recursão")
    first.close()
    second = MemoryStore(settings.database, True)
    assert second.list("demo")[0]["content"] == "Recursão"
    second.retention = False
    assert second.add("demo", "topic", "not retained") is None
    assert second.list("demo") == []
    # Turning retention off does not silently delete existing data.
    second.retention = True
    assert len(second.list("demo")) == 1
    second.close()


def test_real_approved_test_subprocess(client, settings):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        pytest.skip("GitHub-hosted runners deny bubblewrap network namespaces")
    root = settings.projects["demo"]
    (root / "test_sample.py").write_text("def test_example():\n    assert 2 + 2 == 4\n")
    request = {"name": "run_project_tests", "project": "demo"}
    proposal = client.post("/v1/tools", json=request).json()
    identity = proposal["approval_id"]
    client.post(f"/v1/approvals/{identity}", json={"approved": True})
    request["approval_id"] = identity
    result = client.post("/v1/tools", json=request).json()
    assert result["status"] == "completed"
    assert result["exit_code"] == 0, result["output"]
    assert "1 passed" in result["output"]


def test_approval_review_and_denial(client, settings):
    proposal = client.post(
        "/v1/tools", json={"name": "run_project_tests", "project": "demo"}
    ).json()
    identity = proposal["approval_id"]
    review = client.get(f"/v1/approvals/{identity}").json()
    assert review["project"] == "demo"
    assert review["cwd"] == str(settings.projects["demo"])
    assert review["approved"] is False
    assert client.post(f"/v1/approvals/{identity}", json={"approved": "true"}).status_code == 422
    assert client.post(f"/v1/approvals/{identity}", json={"approved": False}).status_code == 200
    assert client.get(f"/v1/approvals/{identity}").status_code == 404
