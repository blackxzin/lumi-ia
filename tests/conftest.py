import asyncio
import os
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app


class FakeProvider:
    def __init__(self):
        self.messages = []

    async def discover(self):
        return "test/deephat:7b"

    async def stream(self, messages):
        self.messages = messages
        for token in ("Olá", ", mundo!"):
            yield token

    async def close(self):
        pass


@pytest.fixture
def settings(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("print('hello')\n")
    database = tmp_path / "memory.db"
    monkeypatch.setenv("CODEPET_DATABASE", str(database))
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    return Settings(
        _env_file=None,
        token="t" * 48,
        projects={"demo": tmp_path, "other": tmp_path},
        database=database,
        proactive=True,
    )


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def app(settings, provider):
    return create_app(settings, provider)


@pytest.fixture
def client(app):
    options = {}
    if os.environ.get("CODEPET_TEST_POLL_LOOP") == "1":
        # Some restricted runners cannot wake a selector across threads via sockets.
        # Poll the in-process test loop; production networking is never replaced.
        def loop_factory():
            loop = asyncio.new_event_loop()

            def tick():
                loop.call_later(0.01, tick)

            loop.call_soon(tick)
            return loop

        options["loop_factory"] = loop_factory
    with TestClient(
        app,
        base_url="http://127.0.0.1:8765",
        backend_options=options,
        headers={"Authorization": "Bearer " + "t" * 48},
    ) as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def restricted_runner_loop():
    if os.environ.get("CODEPET_TEST_POLL_LOOP") == "1":
        loop = asyncio.get_running_loop()

        def tick():
            loop.call_later(0.01, tick)

        loop.call_soon(tick)
        # Keep polling through executor shutdown; loop.close() discards timers.
    yield
