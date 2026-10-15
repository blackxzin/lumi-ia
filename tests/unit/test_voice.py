import json
import subprocess

from apps.desktop.voice import input as voice_input
from apps.desktop.voice.input import PushToTalk
from apps.desktop.voice.tts import LocalSpeaker, spoken_text


def test_spoken_text_skips_code_and_urls():
    answer = "Veja [o guia](https://example.com). ```python\nprint('segredo')\n``` Resolvido."
    assert spoken_text(answer) == "Veja o guia. Resolvido."
    assert len(spoken_text("palavra " * 200)) <= 701
    assert spoken_text("[DeepHat local]\nOlá.\n[Segunda opinião: Codex]\nTudo bem?") == "Olá. Tudo bem?"


def test_transcript_releases_state_before_dispatch(tmp_path):
    import os

    from PySide6.QtCore import QProcess
    from PySide6.QtWidgets import QApplication

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    listener = PushToTalk()
    listener.temp_path = tmp_path / "audio.wav"
    listener.temp_path.touch()
    listener.temp_path.with_suffix(".txt").write_text("Lume, abra o terminal")
    observations = []

    def received(text):
        observations.append((text, listener.temp_path, listener.active))
        listener.shutdown()

    listener.text_ready.connect(received)
    listener.transcription_finished(0, QProcess.ExitStatus.NormalExit)
    assert observations == [("Lume, abra o terminal", None, False)]
    assert not list(tmp_path.iterdir())
    app.processEvents()


def test_input_devices_prioritizes_default_audiorelay_monitor(monkeypatch):
    sources = [
        {"name": "real-microphone", "description": "Microfone físico"},
        {"name": "audiorelay-virtual-mic-sink.monitor", "description": "AudioRelay"},
    ]
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        output = json.dumps(sources) if "list" in command else "audiorelay-virtual-mic-sink.monitor\n"
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr(voice_input.shutil, "which", lambda name: "/usr/bin/pactl" if name == "pactl" else None)
    monkeypatch.setattr(voice_input.subprocess, "run", fake_run)

    devices = PushToTalk.input_devices()

    assert devices[0] == ("audiorelay-virtual-mic-sink.monitor", "AudioRelay · monitor")
    assert devices[1] == ("real-microphone", "Microfone físico")
    assert len(calls) == 2


def test_whisper_model_can_be_configured(monkeypatch, tmp_path):
    model = tmp_path / "model.bin"
    model.touch()
    monkeypatch.setenv("CODEPET_WHISPER_MODEL", str(model))

    assert PushToTalk._find_whisper_model() == str(model)


def test_output_devices_recommend_physical_output_when_audiorelay_is_default(monkeypatch):
    sinks = [
        {"name": "audiorelay-virtual-mic-sink", "description": "AudioRelayVirtualMic"},
        {
            "name": "alsa_output.pci-0000_09_00.6.analog-stereo",
            "description": "(null)",
            "properties": {"device.description": "Fones de ouvido"},
        },
    ]

    def fake_run(command, **_kwargs):
        output = json.dumps(sinks) if "list" in command else "audiorelay-virtual-mic-sink\n"
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr("apps.desktop.voice.tts.shutil.which", lambda name: "/usr/bin/pactl")
    monkeypatch.setattr("apps.desktop.voice.tts.subprocess.run", fake_run)

    assert LocalSpeaker.output_devices() == [
        ("audiorelay-virtual-mic-sink", "AudioRelayVirtualMic"),
        ("alsa_output.pci-0000_09_00.6.analog-stereo", "Fones de ouvido"),
    ]
    assert LocalSpeaker.recommended_output_device() == "alsa_output.pci-0000_09_00.6.analog-stereo"
