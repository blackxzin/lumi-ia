"""Install a per-user desktop ID so Wayland portals recognize CodePet."""

from pathlib import Path

root = Path(__file__).resolve().parents[1]
python = root / ".venv/bin/python"
if not python.is_file():
    raise SystemExit("Run scripts/install.sh first")
entry = Path.home() / ".local/share/applications/codepet-ai.desktop"
entry.parent.mkdir(parents=True, exist_ok=True)
content = "\n".join(
    (
        "[Desktop Entry]",
        "Type=Application",
        "Name=CodePet AI",
        "Comment=Tutor de programação local com pet virtual",
        f'Exec="{python}" -m apps.desktop.main',
        f"Path={root}",
        "Terminal=false",
        "Categories=Development;Education;",
        "StartupNotify=false",
        "",
    )
)
if entry.exists() and entry.read_text() == content:
    print(f"Desktop entry already installed: {entry}")
else:
    entry.write_text(content)
    print(f"Installed desktop entry: {entry}")
