from pathlib import Path

from alembic import command
from alembic.config import Config

from backend.app.memory.store import MemoryStore


def test_metrics_and_focus_review(tmp_path: Path, monkeypatch):
    database = tmp_path / "metrics.db"
    monkeypatch.setenv("CODEPET_DATABASE", str(database))
    command.upgrade(Config(str(Path(__file__).parents[2] / "alembic.ini")), "head")
    store = MemoryStore(database, True)
    store.record_metric("demo", "chat_completed")
    assert store.metric_summary("demo")["events"] == {"chat_completed": 1}
    store.record_focus("demo", {"goal": "Estudar", "focus_minutes": 15, "break_minutes": 5})
    assert store.review_focus("demo", "Estudar", "Terminei a leitura", "Fazer exercícios")
    assert store.focus_history("demo")[0]["outcome"] == "Terminei a leitura"
    store.close()
