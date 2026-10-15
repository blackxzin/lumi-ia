"""Opt-in Qt-to-real-Ollama acceptance test; requires running CodePet backend."""

import os

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from apps.desktop.chat.transport import BackendClient
from apps.desktop.main import ChatWindow
from backend.app.core.config import Settings


@pytest.mark.live
@pytest.mark.desktop
@pytest.mark.skipif(os.environ.get("CODEPET_DESKTOP_LIVE") != "1", reason="Opt-in GUI network test")
@pytest.mark.parametrize("selected", ["ollama", "codex"])
def test_qt_chat_streams_real_model(selected):
    app = QApplication.instance() or QApplication([])
    settings = Settings()
    assert settings.projects
    client = BackendClient(settings.token.get_secret_value())
    window = ChatWindow(client, settings)
    window.voice.setChecked(False)
    window.mode.setCurrentIndex(window.mode.findData("assistant"))
    result = {"done": False, "error": None, "tokens": []}

    def on_ready():
        window.prompt.setText("Lume, mude para o " + ("Codex" if selected == "codex" else "DeepHat"))
        window.ask()
        assert window.provider_choice.currentData() == selected
        window.prompt.setText("Responda apenas: Olá.")
        window.ask()

    def on_event(event):
        if event.get("type") == "token":
            result["tokens"].append(event["content"])
        elif event.get("type") == "done":
            result["done"] = True
            app.quit()
        elif event.get("type") == "error":
            result["error"] = event.get("message")
            app.quit()

    client.ready.connect(on_ready)
    client.event.connect(on_event)
    client.failure.connect(lambda error: (result.__setitem__("error", error), app.quit()))
    QTimer.singleShot(120000, app.quit)
    window.show()
    client.connect_backend()
    app.exec()
    window.shutdown()
    window.close()
    assert result["done"], result["error"] or "Timed out"
    assert "".join(result["tokens"]).strip()
