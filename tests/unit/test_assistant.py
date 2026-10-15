import pytest

from apps.desktop.assistant import (
    WakeGate,
    _is_safe_app_name,
    addressed_text,
    find_desktop_executable,
    parse_command,
)


@pytest.mark.parametrize("text", ["a lume está aqui", "Lumen abra o terminal", "volume alto", "abra o terminal"])
def test_wake_word_requires_addressing_lume(text):
    assert addressed_text(text) is None


def test_wake_word_and_one_short_followup(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("apps.desktop.assistant.time.monotonic", lambda: now[0])
    gate = WakeGate()
    assert gate.accept("Ei, Lume, abra o terminal!") == "abra o terminal!"
    assert gate.accept("abra o navegador") is None
    assert gate.accept("Lume") == ""
    assert gate.accept("que horas são?") == "que horas são?"
    assert gate.accept("abra o navegador") is None
    gate.accept("Lume")
    now[0] += 9
    assert gate.accept("abra o navegador") is None


@pytest.mark.parametrize("text", [
    "abra o terminal; rm -rf /", "abra o terminal && curl example.com", "abra o vscode --install-extension x",
    "abra o navegador e o terminal", "abra https://example.com", "abra $(comando)",
])
def test_open_does_not_accept_arguments_or_chained_commands(text):
    assert parse_command(text).action == "unsupported"


def test_focus_and_notes_preserve_user_text():
    command = parse_command("Começar foco de vinte e cinco minutos para Revisar a API.")
    assert (command.action, command.minutes, command.value) == ("focus_start", 25, "Revisar a API")
    assert parse_command("anote que Prefiro Python").value == "Prefiro Python"
    assert parse_command("como está meu foco?").action == "focus_status"
    assert parse_command("Por que iniciar foco ajuda?") is None


@pytest.mark.parametrize("text, expected", [
    ("mude para o Codex", "codex"), ("quero usar o Codex", "codex"),
    ("quero modelo local deep hat", "ollama"), ("use o DeepHat", "ollama"),
    ("mude para o deep het", "ollama"),
])
def test_explicit_model_commands(text, expected):
    assert parse_command(text).value == expected
    assert parse_command(text).action == "provider"


def test_launcher_uses_only_fixed_argv(monkeypatch, tmp_path):
    from PySide6.QtCore import QProcess

    from apps.desktop.assistant import launch_application

    calls = []
    monkeypatch.setattr("apps.desktop.assistant.shutil.which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(QProcess, "startDetached", lambda *args: (calls.append(args) or True, 10))
    assert launch_application("editor", tmp_path)
    assert calls == [("/usr/bin/code", ["--new-window", str(tmp_path)], str(tmp_path))]
    assert not launch_application("sh", tmp_path)
    assert len(calls) == 1


def test_open_generic_parses_clean_app_names():
    cmd = parse_command("abra o discord")
    assert cmd.action == "open_generic"
    assert cmd.value == "discord"
    cmd = parse_command("abra o spotify")
    assert cmd.action == "open_generic"
    assert cmd.value == "spotify"
    cmd = parse_command("abre a steam")
    assert cmd.action == "open_generic"
    assert cmd.value == "steam"
    cmd = parse_command("abra o obs")
    assert cmd.action == "open_generic"
    assert cmd.value == "obs"
    # Known apps still use the fixed action
    cmd = parse_command("abra o terminal")
    assert cmd.action == "open"
    assert cmd.value == "terminal"


def test_safe_app_name_rejects_dangerous_input():
    assert _is_safe_app_name("discord")
    assert _is_safe_app_name("obs studio")
    assert _is_safe_app_name("libre office")
    assert not _is_safe_app_name("rm -rf /")
    assert not _is_safe_app_name("/usr/bin/evil")
    assert not _is_safe_app_name("app; curl evil.com")
    assert not _is_safe_app_name("$(whoami)")
    assert not _is_safe_app_name("")


def test_find_desktop_executable_finds_by_name(tmp_path, monkeypatch):
    apps_dir = tmp_path / "share" / "applications"
    apps_dir.mkdir(parents=True)
    (apps_dir / "discord.desktop").write_text(
        "[Desktop Entry]\nName=Discord\nExec=/usr/bin/discord-app\nType=Application\n"
    )
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "share"))
    monkeypatch.setattr("apps.desktop.assistant.shutil.which",
                        lambda name: f"/usr/bin/{name}" if name == "discord-app" else None)
    result = find_desktop_executable("discord")
    assert result == "/usr/bin/discord-app"


def test_find_desktop_executable_returns_none_for_unknown(tmp_path, monkeypatch):
    apps_dir = tmp_path / "share" / "applications"
    apps_dir.mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "share"))
    assert find_desktop_executable("nonexistent-app-xyz") is None


def test_launch_generic_finds_executable(monkeypatch):
    from PySide6.QtCore import QProcess

    from apps.desktop.assistant import launch_generic

    calls = []
    monkeypatch.setattr("apps.desktop.assistant.shutil.which",
                        lambda name: f"/usr/bin/{name}" if name == "discord" else None)
    monkeypatch.setattr(QProcess, "startDetached", lambda *args: (calls.append(args) or True, 10))
    started, display = launch_generic("discord")
    assert started
    assert display == "discord"
    assert calls == [("/usr/bin/discord", [], "")]


def test_launch_generic_rejects_unsafe_names():
    from apps.desktop.assistant import launch_generic

    started, _ = launch_generic("rm -rf /")
    assert not started
