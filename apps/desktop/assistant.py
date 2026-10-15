"""Explicit desktop commands; model output never enters this dispatcher."""

import glob
import os
import re
import shutil
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path


def normalize(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", text.casefold())
        if not unicodedata.combining(char)
    )


def addressed_text(text: str) -> str | None:
    match = re.match(r"^(?:(?:oi|ei|olá|ola|hey)[,\s]+)?lum[ei]\b[\s,:.!?–—-]*", text.strip(), re.I)
    return text.strip()[match.end():].strip() if match else None


class WakeGate:
    """A bare name arms one follow-up, only for the next eight seconds."""

    def __init__(self):
        self.until = 0.0

    def reset(self):
        self.until = 0.0

    def accept(self, text: str) -> str | None:
        command = addressed_text(text)
        if command is not None:
            self.until = time.monotonic() + 8 if not command else 0.0
            return command
        if time.monotonic() < self.until:
            self.reset()
            return text.strip()
        self.reset()
        return None


@dataclass(frozen=True)
class DesktopCommand:
    action: str
    value: str = ""
    minutes: int = 25


APP_NAMES = {
    "navegador": "browser", "browser": "browser",
    "terminal": "terminal", "vs code": "editor", "vscode": "editor",
    "visual studio code": "editor", "editor": "editor",
    "arquivos": "files", "pasta do projeto": "files", "projeto": "files",
}

# Only single clean names: letters, digits, hyphens, spaces, dots. No shell
# metacharacters, no slashes, no semicolons, no chaining operators, no flags.
# At most three words (e.g. "obs studio", "libre office writer").
_SAFE_APP_NAME = re.compile(
    r"^[a-záàâãéèêíïóôõúüçñ]"           # starts with a letter
    r"[a-záàâãéèêíïóôõúüçñ0-9.+-]*"     # rest of first word
    r"(?:\s[a-záàâãéèêíïóôõúüçñ][a-záàâãéèêíïóôõúüçñ0-9.+-]*){0,2}$"  # up to 2 more words, each starting with a letter
)


def _is_safe_app_name(name: str) -> bool:
    """Reject anything that looks like it carries arguments or shell tricks."""
    return bool(_SAFE_APP_NAME.match(name))


def find_desktop_executable(query: str) -> str | None:
    """Search XDG .desktop files for *query* and return the Exec binary path.

    Only the executable name (argv[0]) is extracted; field codes and arguments
    from the .desktop entry are stripped.  Returns ``None`` when nothing matches.
    """
    dirs = os.environ.get("XDG_DATA_DIRS", "/usr/share:/usr/local/share").split(":")
    dirs.append(os.path.expanduser("~/.local/share"))
    query_lower = query.lower()
    for d in dirs:
        for path in glob.glob(os.path.join(d, "applications", "*.desktop")):
            try:
                name_match = False
                exec_line = ""
                with open(path, encoding="utf-8", errors="replace") as fh:
                    in_entry = False
                    for line in fh:
                        stripped = line.strip()
                        if stripped == "[Desktop Entry]":
                            in_entry = True
                            continue
                        if stripped.startswith("[") and in_entry:
                            break
                        if not in_entry:
                            continue
                        if stripped.startswith("Name=") or stripped.startswith("GenericName="):
                            value = stripped.split("=", 1)[1].strip().lower()
                            if query_lower == value or query_lower in value:
                                name_match = True
                        elif stripped.startswith("Exec="):
                            exec_line = stripped.split("=", 1)[1].strip()
                if name_match and exec_line:
                    # Strip field codes like %U %f etc. and take only argv[0].
                    binary = re.split(r"\s+", exec_line)[0]
                    binary = re.sub(r"%[a-zA-Z]", "", binary).strip()
                    resolved = shutil.which(os.path.basename(binary)) or shutil.which(binary)
                    if resolved:
                        return resolved
            except OSError:
                continue
    return None

HELP = (
    'Diga “Lume” antes do pedido. Exemplos:\n'
    '• Lume, abra o navegador / terminal / VS Code / pasta do projeto.\n'
    '• Lume, iniciar foco de 25 minutos para terminar o relatório.\n'
    '• Lume, pausar foco / retomar foco / concluir foco / como está meu foco?\n'
    '• Lume, anote que preciso revisar os testes.\n'
    '• Lume, pesquise no projeto minha_funcao.\n'
    '• Lume, me distraí.\n'
    '• Lume, mude para o Codex / quero o modelo local DeepHat.\n'
    '• Lume, pare de ouvir.\n'
    'Você também pode digitar esses comandos no modo assistente.'
)


def parse_command(text: str) -> DesktopCommand | None:
    text = text.strip().rstrip(".!?").strip()
    plain = normalize(text)
    switch = re.fullmatch(
        r"(?:mude|muda|mudar|troque|troca|trocar)(?: o modelo)? (?:para|pro|pra) (?:o )?(.+)|"
        r"(?:use|usar|quero)(?: usar)? (?:o )?(.+)", plain,
    )
    if switch:
        target = switch[1] or switch[2]
        if target in {"codex", "modelo codex"}:
            return DesktopCommand("provider", "codex")
        if target in {"deephat", "deep hat", "deep het", "modelo local", "local", "modelo local deephat", "modelo local deep hat", "modelo local deep het", "deephat local", "deep hat local"}:
            return DesktopCommand("provider", "ollama")
    fixed = {
        "ajuda": "help", "o que voce pode fazer": "help", "comandos": "help",
        "pausar foco": "focus_pause", "pause o foco": "focus_pause",
        "retomar foco": "focus_resume", "retome o foco": "focus_resume",
        "concluir foco": "focus_complete", "conclua o foco": "focus_complete",
        "como esta meu foco": "focus_status", "status do foco": "focus_status",
        "me distrai": "recover", "pare de ouvir": "stop_listening",
        "parar de ouvir": "stop_listening", "que horas sao": "time",
    }
    if plain in fixed:
        return DesktopCommand(fixed[plain])
    opened = re.fullmatch(r"(?:abra|abrir|abre) (?:o |a )?(.+)", plain)
    if opened:
        app = APP_NAMES.get(opened[1])
        if app:
            return DesktopCommand("open", app)
        raw_name = opened[1]
        if _is_safe_app_name(raw_name):
            return DesktopCommand("open_generic", raw_name)
        return DesktopCommand("unsupported")
    note = re.fullmatch(r"(?:anote(?: que)?|guarde (?:a )?nota)\s+(.+)", text, re.I)
    if note:
        return DesktopCommand("remember", note[1])
    search = re.fullmatch(r"(?:pesquise|busque|procure) no projeto\s+(.+)", text, re.I)
    if search:
        return DesktopCommand("search", search[1])
    focus = re.fullmatch(
        r"(?:iniciar|inicie|comecar|comece) (?:o )?foco"
        r"(?: (?:de |por )?(\d{1,3}|quinze|vinte e cinco|cinquenta) minutos)?"
        r"(?: para (.+))?", plain,
    )
    if focus:
        amount = focus[1] or "25"
        minutes = {"quinze": 15, "vinte e cinco": 25, "cinquenta": 50}.get(amount)
        minutes = minutes if minutes is not None else int(amount)
        # Preserve the original spelling of the goal.
        goal = re.split(r" para ", text, maxsplit=1, flags=re.I)[-1] if focus[2] else ""
        return DesktopCommand("focus_start", goal, minutes)
    return None


def launch_application(target: str, project: Path) -> bool:
    """Fixed launch targets and argv, with no shell or user-provided arguments."""
    from PySide6.QtCore import QProcess, QUrl
    from PySide6.QtGui import QDesktopServices

    if target == "browser":
        return QDesktopServices.openUrl(QUrl("https://www.google.com"))
    if target == "files":
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(project)))
    programs = {
        "editor": ("code", "codium"),
        "terminal": ("kitty", "foot", "alacritty", "konsole", "gnome-terminal", "xterm"),
    }
    for name in programs.get(target, ()):
        executable = shutil.which(name)
        if executable:
            args = ["--new-window", str(project)] if target == "editor" else []
            started, _pid = QProcess.startDetached(executable, args, str(project))
            return started
    return False


def launch_generic(app_name: str) -> tuple[bool, str]:
    """Try to open any installed application by name.

    Resolution order:
    1. Direct executable lookup via ``shutil.which``.
    2. XDG ``.desktop`` file search matching Name/GenericName fields.

    Returns ``(started, display_name)`` where *display_name* is the
    identifier shown to the user.
    """
    from PySide6.QtCore import QProcess

    if not _is_safe_app_name(app_name):
        return False, app_name

    # 1. Try direct executable lookup (handles "discord", "spotify", etc.)
    executable = shutil.which(app_name)
    if not executable:
        # Try common casing variants for Electron apps (/usr/bin/Discord)
        executable = shutil.which(app_name.title())
    if not executable:
        executable = shutil.which(app_name.lower().replace(" ", "-"))

    # 2. Search .desktop files by friendly name
    if not executable:
        executable = find_desktop_executable(app_name)

    if executable:
        started, _pid = QProcess.startDetached(executable, [], "")
        return started, app_name
    return False, app_name
