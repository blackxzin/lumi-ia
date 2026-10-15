"""Create local configuration without overwriting an existing .env."""

import json
import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
content = (
    f"CODEPET_TOKEN={secrets.token_urlsafe(48)}\n"
    f"CODEPET_PROJECTS='{json.dumps({'default': str(root)})}'\n"
    "CODEPET_MODEL=\nCODEPET_RETENTION=true\nCODEPET_PROACTIVE=false\n"
)
try:
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print("Existing .env preserved.")
else:
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    print("Created .env with private token. Do not commit or share it.")
