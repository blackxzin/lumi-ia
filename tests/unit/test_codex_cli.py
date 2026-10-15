from pathlib import Path

import pytest

from backend.app.llm.codex_cli import CodexCliProvider
from backend.app.llm.ollama import ProviderError


def fake_cli(path: Path, *, tool: bool = False) -> Path:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "if sys.argv[1:3] == ['login', 'status']:\n"
        "    sys.exit(0)\n"
        "prompt = sys.stdin.read()\n"
        "assert '--sandbox' in sys.argv and 'read-only' in sys.argv\n"
        "assert '--ephemeral' in sys.argv and '--ignore-user-config' in sys.argv\n"
        "assert 'CODEPET_TOKEN' not in os.environ\n"
        "assert 'Pergunta de teste' in prompt\n"
        + (
            "print(json.dumps({'type':'item.started','item':{'type':'command_execution'}}))\n"
            if tool
            else "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Resposta do Codex'}}))\n"
        )
        + "print(json.dumps({'type':'turn.completed'}))\n"
    )
    path.chmod(0o700)
    return path


async def test_codex_cli_provider_uses_read_only_ephemeral_process(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("CODEPET_TOKEN", "never-pass-this")
    provider = CodexCliProvider(settings, str(fake_cli(tmp_path / "codex-fake")))
    assert await provider.discover() == "Codex CLI"
    assert [part async for part in provider.stream([{"role": "user", "content": "Pergunta de teste"}])] == [
        "Resposta do Codex"
    ]


async def test_codex_cli_provider_rejects_tool_events(settings, tmp_path):
    provider = CodexCliProvider(settings, str(fake_cli(tmp_path / "codex-fake", tool=True)))
    with pytest.raises(ProviderError, match="tool call"):
        _ = [part async for part in provider.stream([{"role": "user", "content": "Pergunta de teste"}])]
