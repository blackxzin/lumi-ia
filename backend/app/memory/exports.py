"""Write user-controlled memory exports with private filesystem permissions."""

import json
import os
import tempfile
from pathlib import Path


def write_private_export(path: Path, payload: dict, *, overwrite: bool = False) -> Path:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".codepet-export-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path, follow_symlinks=False)
            temporary.unlink()
        return path
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
