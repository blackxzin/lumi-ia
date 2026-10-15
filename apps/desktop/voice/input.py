"""Optional local push-to-talk and relay input.

PulseAudio compatibility (including PipeWire monitor sources) is preferred; Qt
Multimedia remains the fallback. Transcription stays local to the machine.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QObject, QProcess, QTimer, Signal
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices

TRANSCRIPTION_HINT = (
    "Lume, abra o terminal. Lume, abra o navegador. Lume, iniciar foco de vinte e cinco minutos. "
    "Lume, pausar foco. Lume, anote que preciso estudar. Lume, que horas são?"
    " Lume, mude para o Codex. Lume, use o modelo local DeepHat."
)


class PushToTalk(QObject):
    text_ready = Signal(str)
    failure = Signal(str)
    level_changed = Signal(int)
    recording_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        venv_whisper = Path(sys.executable).with_name("whisper")
        self.transcriber = str(venv_whisper) if venv_whisper.is_file() else shutil.which("whisper")
        self.whisper_cli = shutil.which("whisper-cli") or shutil.which("whisper-cpp")
        self.whisper_model = self._find_whisper_model()
        self.use_whisper_cpp = bool(self.whisper_cli and self.whisper_model)
        self.audio = None
        self.buffer: QBuffer | None = None
        self.parec = shutil.which("parec")
        self.pulse_process: QProcess | None = None
        self.stopping_capture = False
        self.raw_audio = bytearray()
        self.process: QProcess | None = None
        self.temp_path: Path | None = None
        self.started_at = 0.0
        self.last_voice_at = 0.0
        self.device_name = ""
        self.silence_seconds = 1.1
        self.sensitivity = 420
        self.level_timer = QTimer(self)
        self.level_timer.setInterval(150)
        self.level_timer.timeout.connect(self.check_silence)
        self.transcription_timer = QTimer(self)
        self.transcription_timer.setSingleShot(True)
        self.transcription_timer.setInterval(60_000)
        self.transcription_timer.timeout.connect(self.transcription_timeout)

    @property
    def available(self) -> bool:
        return bool(self.use_whisper_cpp or self.transcriber) and bool(self.input_devices())

    @property
    def active(self) -> bool:
        return self.pulse_process is not None or self.audio is not None or self.process is not None

    @staticmethod
    def _find_whisper_model() -> str:
        configured = os.environ.get("CODEPET_WHISPER_MODEL", "").strip()
        candidates = [configured] if configured else []
        candidates.extend(
            str(path)
            for path in (
                Path.home() / ".local/share/whisper.cpp/ggml-base.bin",
                Path.home() / ".local/share/whisper.cpp/models/ggml-base.bin",
                Path.home() / ".cache/whisper.cpp/ggml-base.bin",
                Path("/usr/share/whisper.cpp/models/ggml-base.bin"),
                Path("/usr/share/whisper-cpp/models/ggml-base.bin"),
                Path("/usr/share/whisper.cpp/ggml-base.bin"),
                Path("/usr/share/whisper-cpp/ggml-base.bin"),
            )
        )
        return next((value for value in candidates if value and Path(value).is_file()), "")

    @staticmethod
    def input_devices() -> list[tuple[str, str]]:
        """Return PulseAudio/PipeWire sources, including virtual sink monitors."""
        pactl = shutil.which("pactl")
        if pactl:
            try:
                result = subprocess.run(
                    [pactl, "-f", "json", "list", "sources"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=True,
                )
                sources = json.loads(result.stdout)
                devices = []
                for source in sources:
                    name = source.get("name", "")
                    if not name:
                        continue
                    description = source.get("description") or name
                    if description == "(null)":
                        if "audiorelay" in name.lower():
                            description = "AudioRelay virtual mic"
                        elif name.endswith(".monitor"):
                            description = f"Monitor · {name.split('.', 1)[0]}"
                        else:
                            description = f"Microfone · {name.rsplit('.', 1)[-1]}"
                    if name.endswith(".monitor"):
                        description = f"{description} · monitor"
                    devices.append((name, description))
                if devices:
                    default = subprocess.run(
                        [pactl, "get-default-source"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        check=True,
                    ).stdout.strip()
                    devices.sort(key=lambda item: item[0] != default)
                    return devices
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
        return [
            (bytes(device.id()).decode(errors="replace"), device.description())
            for device in QMediaDevices.audioInputs()
        ]

    def start(self) -> bool:
        if self.process is not None:
            return False
        if self.pulse_process is not None or self.audio is not None:
            return True
        if not self.available:
            if self.whisper_cli and not self.whisper_model:
                message = "Modelo do whisper.cpp não encontrado (defina CODEPET_WHISPER_MODEL)."
            elif not self.transcriber and not self.whisper_cli:
                message = "Instale whisper ou whisper.cpp com modelo local para transcrever voz."
            else:
                message = "Nenhuma entrada de áudio PipeWire/PulseAudio foi encontrada."
            self.failure.emit(message)
            return False
        devices = dict(self.input_devices())
        source = self.device_name if self.device_name in devices else ""
        if self.parec and shutil.which("pactl"):
            self.raw_audio = bytearray()
            self.pulse_process = QProcess(self)
            self.pulse_process.readyReadStandardOutput.connect(self._read_pulse_audio)
            self.pulse_process.errorOccurred.connect(self._pulse_error)
            self.pulse_process.finished.connect(self._pulse_finished)
            args = ["--format=s16le", "--rate=16000", "--channels=1"]
            if source:
                args.insert(0, f"--device={source}")
            self.pulse_process.start(self.parec, args)
            if not self.pulse_process.waitForStarted(1500):
                error = self.pulse_process.errorString()
                self.pulse_process = None
                self.failure.emit(f"Não consegui abrir o microfone PipeWire: {error}")
                return False
            self.audio = None
            self.buffer = None
            self._begin_recording()
            return True

        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.buffer = QBuffer(self)
        self.buffer.open(QIODevice.OpenModeFlag.ReadWrite)
        devices = QMediaDevices.audioInputs()
        device = next(
            (
                item
                for item in devices
                if item.description() == self.device_name
                or bytes(item.id()).decode(errors="replace") == self.device_name
            ),
            None,
        )
        self.audio = QAudioSource(device or QMediaDevices.defaultAudioInput(), fmt, self)
        self.audio.start(self.buffer)
        if self.audio.error() != QAudioSource.Error.NoError:
            message = self.audio.errorString()
            self.audio.stop()
            self.audio.deleteLater()
            self.audio = None
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None
            self.failure.emit(f"Não consegui abrir o microfone: {message}")
            return False
        self._begin_recording()
        return True

    def _begin_recording(self) -> None:
        self.started_at = time.monotonic()
        self.last_voice_at = 0.0
        self.level_timer.start()
        self.recording_changed.emit(True)

    def _read_pulse_audio(self) -> None:
        if self.pulse_process is not None:
            self.raw_audio.extend(bytes(self.pulse_process.readAllStandardOutput()))

    def _pulse_error(self, _error) -> None:
        if (
            not self.stopping_capture
            and self.pulse_process is not None
            and self.pulse_process.state() == QProcess.ProcessState.NotRunning
        ):
            self._fail_pulse_capture(
                f"Falha ao acessar o microfone: {self.pulse_process.errorString()}"
            )

    def _pulse_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        if self.stopping_capture or self.pulse_process is None:
            return
        process = self.pulse_process
        self._read_pulse_audio()
        self.pulse_process = None
        process.deleteLater()
        self.level_timer.stop()
        self.recording_changed.emit(False)
        self.level_changed.emit(0)
        if exit_code:
            self.failure.emit("O PipeWire encerrou a captura do microfone.")
            return
        self._transcribe_audio(bytes(self.raw_audio))

    def _fail_pulse_capture(self, message: str) -> None:
        process, self.pulse_process = self.pulse_process, None
        self.level_timer.stop()
        self.recording_changed.emit(False)
        self.level_changed.emit(0)
        if process is not None:
            process.deleteLater()
        self.failure.emit(message)

    def check_silence(self) -> None:
        if self.pulse_process is None and (self.buffer is None or self.audio is None):
            self.level_timer.stop()
            return
        raw = bytes(self.raw_audio) if self.pulse_process is not None else bytes(self.buffer.data())
        # Int16 mono, 16 kHz: the tail is approximately 100 ms of microphone input.
        tail = raw[-3200:]
        if len(tail) >= 3200:
            samples = struct.unpack("<1600h", tail)
            rms = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
            level = min(100, int(rms / 120))
            self.level_changed.emit(level)
            if rms >= self.sensitivity:
                self.last_voice_at = time.monotonic()
        else:
            self.level_changed.emit(0)
        now = time.monotonic()
        if (self.last_voice_at and now - self.last_voice_at >= self.silence_seconds) or now - self.started_at >= 20:
            self.stop()

    def stop(self) -> None:
        if self.pulse_process is None and (self.audio is None or self.buffer is None):
            return
        self.level_timer.stop()
        self.recording_changed.emit(False)
        self.level_changed.emit(0)
        if self.pulse_process is not None:
            process = self.pulse_process
            self.stopping_capture = True
            self._read_pulse_audio()
            process.terminate()
            if not process.waitForFinished(1000):
                process.kill()
                process.waitForFinished(1000)
            self._read_pulse_audio()
            raw = bytes(self.raw_audio)
            self.pulse_process = None
            self.stopping_capture = False
            process.deleteLater()
        else:
            self.audio.stop()
            raw = bytes(self.buffer.data())
            self.audio.deleteLater()
            self.audio = None
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None
        # Do not run Whisper on silence: it can hallucinate commands from noise.
        if not self.last_voice_at:
            self.failure.emit("Nenhuma fala detectada.")
            return
        self._transcribe_audio(raw)

    def shutdown(self) -> None:
        """Release audio and transcription children without starting new work."""
        self.level_timer.stop()
        self.transcription_timer.stop()
        recording = self.pulse_process is not None or self.audio is not None
        if self.pulse_process is not None:
            process, self.pulse_process = self.pulse_process, None
            self.stopping_capture = True
            process.terminate()
            if not process.waitForFinished(500):
                process.kill()
                process.waitForFinished(500)
            process.deleteLater()
            self.stopping_capture = False
        if self.audio is not None:
            self.audio.stop()
            self.audio.deleteLater()
            self.audio = None
        if self.buffer is not None:
            self.buffer.close()
            self.buffer.deleteLater()
            self.buffer = None
        if recording:
            self.recording_changed.emit(False)
        if self.process is not None:
            process, self.process = self.process, None
            process.blockSignals(True)
            process.kill()
            process.waitForFinished(500)
            process.deleteLater()
        if self.temp_path is not None:
            self.temp_path.unlink(missing_ok=True)
            self.temp_path.with_suffix(".txt").unlink(missing_ok=True)
            self.temp_path = None

    def _transcribe_audio(self, raw: bytes) -> None:
        if not raw:
            self.failure.emit("Nenhum áudio capturado.")
            return
        handle = tempfile.NamedTemporaryFile(prefix="codepet-voice-", suffix=".wav", delete=False)
        handle.close()
        self.temp_path = Path(handle.name)
        with wave.open(str(self.temp_path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(raw)
        self.transcribe()

    def transcribe(self) -> None:
        if self.temp_path is None:
            return
        self.process = QProcess(self)
        self.process.finished.connect(self.transcription_finished)
        self.process.errorOccurred.connect(self.transcription_error)
        self.transcription_timer.start()
        if self.use_whisper_cpp:
            output_base = str(self.temp_path.with_suffix(""))
            self.process.start(self.whisper_cli, [
                "--no-gpu", "-m", self.whisper_model, "-f", str(self.temp_path),
                "-l", "pt", "-otxt", "-of", output_base,
                "--prompt", TRANSCRIPTION_HINT,
            ])
        else:
            self.process.start(self.transcriber, [
                str(self.temp_path),
                "--language",
                "pt",
                "--initial_prompt",
                TRANSCRIPTION_HINT,
                "--task",
                "transcribe",
                "--model",
                "base",
                "--device",
                "cpu",
                "--fp16",
                "False",
                "--output_format",
                "txt",
                "--output_dir",
                str(self.temp_path.parent),
            ])

    def transcription_finished(self, _code: int, _status: QProcess.ExitStatus) -> None:
        self.transcription_timer.stop()
        if self.temp_path is None:
            return
        transcript = self.temp_path.with_suffix(".txt")
        text = ""
        error = ""
        try:
            if self.process is not None and self.process.exitCode() != 0:
                error = "A transcrição falhou. Confira o modelo e o comando whisper instalado."
            elif transcript.exists():
                text = transcript.read_text(encoding="utf-8").strip()
                if not text:
                    error = "O áudio não trouxe texto reconhecível."
            else:
                error = "O whisper não produziu uma transcrição."
        finally:
            self.temp_path.unlink(missing_ok=True)
            transcript.unlink(missing_ok=True)
            self.temp_path = None
            if self.process is not None:
                self.process.deleteLater()
                self.process = None
        # Slots may cancel capture or start another turn; release the old job first.
        if text:
            self.text_ready.emit(text)
        else:
            self.failure.emit(error)

    def transcription_error(self, error) -> None:
        if error != QProcess.ProcessError.FailedToStart:
            return
        if self.process is None or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.transcription_timer.stop()
        if self.temp_path is not None:
            self.temp_path.unlink(missing_ok=True)
            self.temp_path.with_suffix(".txt").unlink(missing_ok=True)
        self.process.deleteLater()
        self.process = None
        self.temp_path = None
        self.failure.emit("Não consegui iniciar a transcrição local. Confira o whisper instalado.")

    def transcription_timeout(self) -> None:
        self.shutdown()
        self.failure.emit("A transcrição demorou demais. Tente uma frase mais curta.")
