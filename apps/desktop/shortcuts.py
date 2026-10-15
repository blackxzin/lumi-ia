"""Register desktop-wide shortcuts through the XDG portal on Wayland."""

import re
import shutil

from PySide6.QtCore import QObject, QProcess


class GlobalShortcutPortal(QObject):
    def __init__(self, activate, parent=None):
        super().__init__(parent)
        self.activate = activate
        self.gdbus = shutil.which("gdbus")
        self.monitor = QProcess(self)
        self.monitor.readyReadStandardOutput.connect(self._read_signals)
        self.monitor.finished.connect(self._monitor_finished)
        self.call: QProcess | None = None
        self.output = ""
        self.pending_path = ""
        self.operation = ""
        self.session = ""
        self.buffer = ""
        self.responses = {}

    def start(self):
        if not self.gdbus:
            return False
        self.monitor.setProgram(self.gdbus)
        self.monitor.setArguments([
            "monitor", "--session", "--dest", "org.freedesktop.portal.Desktop",
            "--object-path", "/org/freedesktop/portal/desktop",
        ])
        self.monitor.start()
        self._call("create", "org.freedesktop.portal.GlobalShortcuts.CreateSession",
                   "{'handle_token': <'lume_shortcuts'>, 'session_handle_token': <'lume_session'>}")
        return True

    def stop(self):
        """Stop both the long-running portal monitor and any pending call."""
        for process in (self.call, self.monitor):
            if process is None or process.state() == QProcess.ProcessState.NotRunning:
                continue
            process.terminate()
            if not process.waitForFinished(500):
                process.kill()
                process.waitForFinished(500)

    def _call(self, operation: str, method: str, *args: str):
        if self.call is not None:
            self.call.deleteLater()
        self.call = QProcess(self)
        self.operation = operation
        self.output = ""
        self.call.readyReadStandardOutput.connect(
            lambda: self._collect_call_output(self.call)
        )
        self.call.finished.connect(self._call_finished)
        self.call.setProgram(self.gdbus)
        self.call.setArguments([
            "call", "--session", "--dest", "org.freedesktop.portal.Desktop",
            "--object-path", "/org/freedesktop/portal/desktop",
            "--method", method, *args,
        ])
        self.call.start()

    def _collect_call_output(self, process):
        self.output += bytes(process.readAllStandardOutput()).decode(errors="replace")

    def _call_finished(self, _code, _status):
        process = self.call
        if process is None:
            return
        self._collect_call_output(process)
        if process.exitCode() != 0:
            self.pending_path = ""
            self.activate("unavailable")
            return
        match = re.search(r"(/org/freedesktop/portal/desktop/request/[^\s'(),]+)", self.output)
        if match:
            self.pending_path = match.group(1)
            if self.pending_path in self.responses:
                self._handle_signal(self.responses.pop(self.pending_path))
            else:
                self._read_signals()

    def _read_signals(self):
        self.buffer += bytes(self.monitor.readAllStandardOutput()).decode(errors="replace")
        lines = self.buffer.splitlines(keepends=True)
        self.buffer = ""
        for line in lines:
            if not line.endswith("\n"):
                self.buffer = line
                continue
            self._handle_signal(line)

    def _handle_signal(self, line: str):
        if "org.freedesktop.portal.Request.Response" in line and not self.pending_path:
            request = re.match(r"([^:]+):", line)
            if request:
                self.responses[request.group(1)] = line
            return
        if "org.freedesktop.portal.Request.Response" in line and self.pending_path \
                and not line.startswith(self.pending_path + ":"):
            request = re.match(r"([^:]+):", line)
            if request:
                self.responses[request.group(1)] = line
            return
        if self.pending_path and line.startswith(self.pending_path + ":"):
            success = "uint32 0" in line
            if not success:
                self.pending_path = ""
                self.activate("unavailable")
                return
            if self.operation == "create":
                match = re.search(r"'session_handle': <(?:objectpath )?'([^']+)'", line)
                if match:
                    self.session = match.group(1)
                    shortcuts = (
                        "[('toggle-chat', {'description': <'Mostrar ou ocultar o Lume'>, "
                        "'preferred_trigger': <'CTRL+SHIFT+SPACE'>}), "
                        "('toggle-relay', {'description': <'Ativar ou parar conversa por voz'>, "
                        "'preferred_trigger': <'CTRL+SHIFT+V'>})]"
                    )
                    self._call("bind", "org.freedesktop.portal.GlobalShortcuts.BindShortcuts",
                               self.session, shortcuts, "''", "{}")
            elif self.operation == "bind":
                self.activate("registered")
            self.pending_path = ""
            return
        match = re.search(r"org\.freedesktop\.portal\.GlobalShortcuts\.Activated \(objectpath '([^']+)', '([^']+)'", line)
        if match and match.group(1) == self.session:
            self.activate(match.group(2))

    def _monitor_finished(self, *_args):
        self.pending_path = ""
