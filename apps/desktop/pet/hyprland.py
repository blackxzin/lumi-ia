"""Place the pet with Qt, using Hyprland IPC when that compositor is available."""

import json
import os
import shutil
from collections.abc import Callable

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication, QWidget


class HyprlandPlacement:
    def __init__(self, pet: QWidget):
        self.pet = pet
        self.desired_size = (pet.width(), pet.height())
        self.process: QProcess | None = None
        self.address: str | None = None
        self.monitor: dict | None = None

    def start(self) -> None:
        hyprland = (
            QApplication.platformName() == "wayland"
            and shutil.which("hyprctl")
            and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        )
        if not hyprland:
            self._place_with_qt()
            return
        # The window must have a compositor address before we can target it.
        QTimer.singleShot(400, self._find_window)

    def _place_with_qt(self) -> None:
        """Request a lower-right initial position where the window system permits it."""
        screen = self.pet.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.pet.move(
            area.right() - self.pet.width() - 23,
            area.bottom() - self.pet.height() - 23,
        )

    def _run(self, args: list[str], callback: Callable[[bytes], None]) -> None:
        process = QProcess(self.pet)
        self.process = process
        process.setProgram("hyprctl")
        process.setArguments(args)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        def finished(code: int, _status) -> None:
            data = bytes(process.readAllStandardOutput()) if code == 0 else b""
            process.deleteLater()
            if self.process is process:
                self.process = None
            callback(data)

        process.finished.connect(finished)
        process.start()

    def _find_window(self) -> None:
        def found(data: bytes) -> None:
            try:
                windows = json.loads(data)
                own = [
                    window
                    for window in windows
                    if window.get("pid") == os.getpid()
                    and window.get("title") == self.pet.windowTitle()
                ]
                if len(own) != 1:
                    return
                self.address = own[0]["address"]
                self._run(["monitors", "-j"], self._find_monitor)
            except (ValueError, TypeError, KeyError):
                return

        self._run(["clients", "-j"], found)

    def _find_monitor(self, data: bytes) -> None:
        try:
            monitors = json.loads(data)
            screen = self.pet.screen()
            chosen = next((item for item in monitors if item.get("name") == screen.name()), None)
            self.monitor = chosen or next((item for item in monitors if item.get("focused")), None)
        except (ValueError, TypeError):
            self.monitor = None
        self._float()

    def _dispatch(self, expression: str, next_step: Callable[[bytes], None]) -> None:
        self._run(["dispatch", expression], next_step)

    def _float(self) -> None:
        address = self.address
        if address is None:
            return
        # Hyprland 0.55+ Lua dispatcher; precise address prevents touching other windows.
        self._dispatch(
            f'hl.dsp.window.float({{ action = "set", window = "address:{address}" }})',
            self._resize,
        )

    def _resize(self, result: bytes) -> None:
        if not result or self.address is None:
            return
        width, height = self.desired_size
        self._dispatch(
            f"hl.dsp.window.resize({{ x = {width}, y = {height}, relative = false, "
            f'window = "address:{self.address}" }})',
            self._move,
        )

    def _move(self, result: bytes) -> None:
        if not result or self.address is None or self.monitor is None:
            return
        width, height = self.desired_size
        reserved = self.monitor.get("reserved", [0, 0, 0, 0])
        right, bottom = reserved[2], reserved[3]
        x = max(0, int(self.monitor["width"]) - width - right - 24)
        y = max(0, int(self.monitor["height"]) - height - bottom - 24)
        self._dispatch(
            f"hl.dsp.window.move({{ x = {x}, y = {y}, relative = false, "
            f'window = "address:{self.address}" }})',
            self._pin,
        )

    def _pin(self, result: bytes) -> None:
        if not result or self.address is None:
            return
        # Pin only this floating pet; Hyprland then shows it on the monitor's workspaces.
        self._dispatch(
            f'hl.dsp.window.pin({{ action = "on", window = "address:{self.address}" }})',
            lambda _: None,
        )
