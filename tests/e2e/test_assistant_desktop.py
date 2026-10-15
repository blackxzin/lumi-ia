import os

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
pytest.importorskip("PySide6")
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from apps.desktop.main import ChatWindow


@pytest.fixture
def assistant(settings, tmp_path, monkeypatch):
    from apps.desktop.chat.transport import BackendClient
    from apps.desktop.shortcuts import GlobalShortcutPortal
    from apps.desktop.voice.input import PushToTalk
    from apps.desktop.voice.tts import LocalSpeaker

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("apps.desktop.main.QSettings", lambda *_: QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat))
    monkeypatch.setattr(PushToTalk, "input_devices", staticmethod(lambda: [("test", "Test")]))
    monkeypatch.setattr(PushToTalk, "available", property(lambda _: True))
    monkeypatch.setattr(PushToTalk, "start", lambda _: True)
    monkeypatch.setattr(LocalSpeaker, "output_devices", staticmethod(lambda: []))
    monkeypatch.setattr(LocalSpeaker, "available", property(lambda _: True))
    monkeypatch.setattr(GlobalShortcutPortal, "start", lambda _: False)
    client = BackendClient(settings.token.get_secret_value())
    client.authenticated = True
    window = ChatWindow(client, settings)
    window.mode.setCurrentIndex(window.mode.findData("assistant"))
    window.sent = []
    window.spoken = []
    monkeypatch.setattr(client, "send", window.sent.append)
    monkeypatch.setattr(window.speaker, "say", window.spoken.append)
    yield window
    window.shutdown()
    window.close()
    app.processEvents()


def test_wake_mode_ignores_background_and_dispatches_only_user_commands(assistant, monkeypatch):
    opened = []
    monkeypatch.setattr("apps.desktop.main.launch_application", lambda *args: opened.append(args) or True)
    assistant.prompt.setText("rascunho")
    assistant.wake_mode.setChecked(True)
    assistant.on_voice_transcript("abra o terminal")
    assert assistant.prompt.text() == "rascunho"
    assert not opened
    assistant.on_voice_transcript("Lume, abra o terminal")
    assert opened[0][0] == "terminal"
    assert not assistant.sent
    assistant.handle_backend_event({"type": "token", "content": "Lume, abra o navegador"})
    assistant.handle_backend_event({"type": "done"})
    assert len(opened) == 1


def test_chat_mode_and_microphone_stop(assistant):
    assistant.wake_mode.setChecked(True)
    assistant.on_voice_transcript("Lume, me ajude a organizar meu dia")
    assert assistant.sent[0]["mode"] == "assistant"
    assert assistant.sent[0]["prompt"] == "me ajude a organizar meu dia"
    assistant.handle_backend_event({"type": "done"})
    assistant.on_voice_transcript("Lume, pare de ouvir")
    assert not assistant.wake_mode.isChecked()
    assert not assistant.voice_relay.isChecked()
    assert not assistant.voice_input.active


def test_spoken_model_switch_is_local_and_affects_next_request(assistant):
    assistant.wake_mode.setChecked(True)
    assistant.on_voice_transcript("Lume, mude para o Codex")
    assert not assistant.sent
    assert assistant.provider_choice.currentData() == "codex"
    assistant.on_voice_transcript("Lume, explique uma variável")
    assert assistant.sent[-1]["provider"] == "codex"
    session = assistant.sent[-1]["session"]
    assistant.handle_backend_event({"type": "done"})
    assistant.on_voice_transcript("Lume, quero modelo local DeepHat")
    assistant.on_voice_transcript("Lume, e uma função?")
    assert assistant.sent[-1]["provider"] == "ollama"
    assert assistant.sent[-1]["session"] == session
    assert assistant.preferences.value("chat_provider") == "ollama"


def test_focus_memory_and_search_use_real_api(assistant, client, monkeypatch):
    def rest(method, path, payload, callback):
        response = client.request(method, path, json=payload)
        if response.status_code >= 400:
            assistant.failure(str(response.json().get("detail")))
        else:
            callback(response.json())

    monkeypatch.setattr(assistant.client, "rest", rest)
    for command in ("iniciar foco de 15 minutos para Estudar Python", "pausar foco", "retomar foco", "concluir foco"):
        assistant.prompt.setText(command)
        assistant.ask()
        assert not assistant.busy
    assert assistant.focus_state["status"] == "completed"
    assistant.prompt.setText("anote que Prefiro exemplos curtos")
    assistant.ask()
    assert any(item["content"] == "Prefiro exemplos curtos" for item in client.get("/v1/memory/demo").json()["items"])
    assistant.prompt.setText("pesquise no projeto hello")
    assistant.ask()
    assert "main.py:1" in assistant.history.toPlainText()
    assistant.prompt.setText("pausar foco")
    assistant.ask()
    assert "Nenhuma sessão" in assistant.status.text()
    assert not assistant.busy


def test_offline_launch_failure_and_invalid_focus(assistant, monkeypatch):
    monkeypatch.setattr("apps.desktop.main.launch_application", lambda *_: False)
    assistant.client.authenticated = False
    assistant.prompt.setText("abra o terminal")
    assistant.ask()
    assert "Não consegui" in assistant.spoken[-1]
    assistant.prompt.setText("anote que teste")
    assistant.ask()
    assert "backend conectado" in assistant.spoken[-1]
    assistant.client.authenticated = True
    assistant.prompt.setText("iniciar foco de 999 minutos para estudar")
    assistant.ask()
    assert "1 a 120" in assistant.spoken[-1]


def test_generic_app_launch(assistant, monkeypatch):
    generic_calls = []
    monkeypatch.setattr(
        "apps.desktop.main.launch_generic",
        lambda name: (generic_calls.append(name) or True, name),
    )
    assistant.prompt.setText("abra o discord")
    assistant.ask()
    assert generic_calls == ["discord"]
    assert "Pedi ao sistema para abrir discord." in assistant.spoken[-1]

    monkeypatch.setattr(
        "apps.desktop.main.launch_generic",
        lambda name: (False, name),
    )
    assistant.prompt.setText("abra o aplicativoinexistente")
    assistant.ask()
    assert "Não encontrei" in assistant.spoken[-1]


def test_listening_waits_for_speech_and_reminders_respect_activity(assistant, monkeypatch):
    from apps.desktop.voice.tts import LocalSpeaker

    starts = []
    assistant.wake_mode.setChecked(True)
    monkeypatch.setattr(assistant.voice_input, "start", lambda: starts.append(True) or True)
    monkeypatch.setattr(LocalSpeaker, "speaking", property(lambda _: True))
    assistant.resume_voice_relay()
    assert not starts
    assistant.focus_state = {"status": "running", "goal": "Estudar Python"}
    assistant.focus_reminder()
    assert not assistant.spoken
    monkeypatch.setattr(LocalSpeaker, "speaking", property(lambda _: False))
    assistant.focus_reminder()
    assert "Estudar Python" in assistant.spoken[-1]
    count = len(assistant.spoken)
    assistant.mode.setCurrentText("silent")
    assistant.focus_reminder()
    assert len(assistant.spoken) == count
