#!/usr/bin/env bash
# Launch the local MCP adapter from any working directory.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec .venv/bin/python -m backend.app.mcp.server
