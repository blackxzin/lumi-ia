"""Small, nonblocking, local text-to-speech adapter for the desktop pet."""

import json
import re
import shutil
import subprocess

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


def spoken_text(answer: str) -> str:
    """Keep prose short and avoid reading code blocks, links and Markdown syntax aloud."""
    prose = re.sub(r"```[\s\S]*?```", " ", answer)
    prose = re.sub(r"^\[(?:DeepHat|Segunda opinião|Provider online)[^\n]*\]\s*", "", prose, flags=re.M)
    prose = re.sub(r"!?\[([^]]+)\]\([^)]*\)", r"\1", prose)
    prose = re.sub(r"https?://\S+", " ", prose)
    prose = re.sub(r"[`*_#>|]", " ", prose)
    prose = re.sub(r"\s+", " ", prose).strip()
    if len(prose) <= 700:
        return prose
    short = prose[:700]
    sentences = list(re.finditer(r"[.!?](?:\s|$)", short))
    if sentences:
        return short[:sentences[-1].start() + 1]
    return short.rsplit(" ", 1)[0].rstrip(" ,;:") + "."


class LocalSpeaker(QObject):
    speech_started = Signal()
    speech_finished = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.command = shutil.which("espeak-ng")
        self.process: QProcess | None = None
        self._pending: str | None = None
        self.speed = 155
        self.volume = 100
        self.output_device = ""

    @staticmethod
    def output_devices() -> list[tuple[str, str]]:
        """Return available PulseAudio/PipeWire outputs, with the default first."""
        pactl = shutil.which("pactl")
        if not pactl:
            return []
        try:
            result = subprocess.run(
                [pactl, "-f", "json", "list", "sinks"], capture_output=True,
                text=True, timeout=2, check=True,
            )
            sinks = json.loads(result.stdout)
            default = subprocess.run(
                [pactl, "get-default-sink"], capture_output=True,
                text=True, timeout=2, check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError, ValueError):
            return []
        devices = []
        for sink in sinks:
            name = sink.get("name", "")
            if not name:
                continue
            description = sink.get("description") or name
            if description == "(null)":
                description = sink.get("properties", {}).get("device.description") or name
            devices.append((name, description))
        devices.sort(key=lambda item: item[0] != default)
        return devices

    @staticmethod
    def recommended_output_device() -> str:
        devices = LocalSpeaker.output_devices()
        if not devices:
            return ""
        current = devices[0][0]
        if "audiorelay" not in current.lower():
            return ""
        physical = next(
            (name for name, _ in devices if name.startswith("alsa_output.") and "monitor" not in name),
            "",
        )
        return physical

    @property
    def available(self) -> bool:
        return self.command is not None

    @property
    def speaking(self) -> bool:
        return self._pending is not None or (
            self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning
        )

    def say(self, answer: str) -> None:
        if not self.available:
            return
        text = spoken_text(answer)
        if not text:
            return
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self._pending = text
            self.process.kill()
        else:
            self._start(text)

    def stop(self) -> None:
        self._pending = None
        if self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def _start(self, text: str) -> None:
        # Model text goes to stdin, never to a shell or an option-parsing argument.
        if self.process is None:
            self.process = QProcess(self)
            self.process.started.connect(self.speech_started)
            self.process.finished.connect(self._finished)
            self.process.errorOccurred.connect(self._error)
        environment = QProcessEnvironment.systemEnvironment()
        if self.output_device:
            environment.insert("PULSE_SINK", self.output_device)
        else:
            environment.remove("PULSE_SINK")
        self.process.setProcessEnvironment(environment)
        self.process.start(self.command, ["-v", "pt-br", "-s", str(self.speed), "-a", str(self.volume), "--stdin"])
        self.process.write(text.encode("utf-8"))
        self.process.closeWriteChannel()

    def _finished(self, _code: int, _status: QProcess.ExitStatus) -> None:
        if self._pending is not None:
            text, self._pending = self._pending, None
            self._start(text)
        else:
            self.speech_finished.emit()

    def _error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._pending = None
            self.speech_finished.emit()
