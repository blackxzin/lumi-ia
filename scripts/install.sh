#!/usr/bin/env bash
# Local editable installation only; no sudo, compositor changes or service enablement.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v uv >/dev/null || { echo 'Install uv first; see docs/installation-arch.md'; exit 1; }
uv sync --locked --python 3.12 --extra desktop --extra mcp --extra dev
.venv/bin/python scripts/bootstrap.py
.venv/bin/alembic upgrade head
.venv/bin/python scripts/install_desktop_entry.py
.venv/bin/python scripts/doctor.py
printf '%s\n' 'Installed. Start backend and desktop in separate terminals; see README.md.'
