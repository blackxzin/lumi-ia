import os
import stat
from pathlib import Path


class Workspace:
    def __init__(self, projects: dict[str, Path]):
        self.projects = projects

    def root(self, project: str) -> Path:
        if project not in self.projects:
            raise ValueError("Project not authorized")
        return self.projects[project]

    def path(self, project: str, relative: str) -> Path:
        root = self.root(project)
        supplied = Path(relative)
        if supplied.is_absolute() or ".." in supplied.parts or not supplied.parts:
            raise ValueError("Expected a relative project file")
        for part in supplied.parts:
            lower = part.lower()
            if (
                lower.startswith(".")
                or lower in {"node_modules", "credentials", "secrets", "id_rsa", "id_ed25519"}
                or lower.endswith((".pem", ".key", ".p12", ".pfx", ".db", ".sqlite"))
                or "credential" in lower
                or "secret" in lower
            ):
                raise ValueError("Sensitive or excluded path")
        candidate = root / supplied
        current = root
        for part in supplied.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symlinks are not permitted")
        if not candidate.resolve().is_relative_to(root):
            raise ValueError("Path outside authorized project")
        return candidate

    def read(self, project: str, relative: str) -> str:
        # Open each component relative to a directory descriptor to avoid symlink races.
        self.path(project, relative)
        fd = os.open(self.root(project), os.O_RDONLY | os.O_DIRECTORY)
        try:
            parts = Path(relative).parts
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            with os.fdopen(file_fd, "rb") as stream:
                meta = os.fstat(stream.fileno())
                if not stat.S_ISREG(meta.st_mode) or meta.st_size > 65536:
                    raise ValueError("Only regular UTF-8 files up to 64 KiB are permitted")
                data = stream.read(65537)
                if len(data) > 65536 or b"\0" in data:
                    raise ValueError("File too large or binary")
                return data.decode("utf-8")
        finally:
            os.close(fd)
