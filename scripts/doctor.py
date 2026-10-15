"""Read-only checks. Does not download or load any model."""

import importlib.util
import json
import os
import platform
import shutil
import subprocess
import urllib.error
import urllib.request

from backend.app.core.config import Settings

settings = Settings()
print("Configured provider:", settings.provider)
if settings.provider == "codex":
    codex = shutil.which("codex")
    print("Codex CLI:", codex or "missing")
    if codex:
        try:
            result = subprocess.run(
                [codex, "login", "status"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
            print("Codex login:", "ready" if result.returncode == 0 else "required")
        except (OSError, subprocess.TimeoutExpired):
            print("Codex login: unavailable")

print("Python:", platform.python_version())
print("Session:", os.environ.get("XDG_SESSION_TYPE"), os.environ.get("XDG_CURRENT_DESKTOP"))
for name in ("PySide6", "fastapi", "sqlalchemy", "alembic", "mcp"):
    print(name, "available" if importlib.util.find_spec(name) else "missing")
for name in ("ollama", "rg", "git", "hyprctl", "gdbus", "grim", "bwrap"):
    print(name, shutil.which(name) or "missing")
try:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open("http://127.0.0.1:11434/api/tags", timeout=5) as response:
        data = json.load(response)
    models = [item["name"] for item in data.get("models", [])]
    print("Installed Ollama models:", models)
    print(
        "DeepHat candidates:",
        [name for name in models if "deephat" in name.lower().replace("-", "").replace("_", "")],
    )
except (urllib.error.URLError, OSError, ValueError) as exc:
    print("Ollama API unreachable:", type(exc).__name__)
print(
    "Wayland positioning and portal permissions require a real desktop session; not inferred from environment variables."
)
