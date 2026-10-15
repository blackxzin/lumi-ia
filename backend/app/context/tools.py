import asyncio
import base64
import json
import logging
import os
import shutil
import signal
import sys
import tempfile
from contextlib import suppress
from pathlib import Path

from backend.app.context.workspace import Workspace
from backend.app.core.config import Settings
from backend.app.memory.store import MemoryStore
from backend.app.permissions.actions import Permissions
from backend.app.schemas.messages import ToolInput

log = logging.getLogger("codepet.audit")


async def command(argv: list[str], cwd: Path, deadline_seconds: float = 30) -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT"}
    }
    env.update({"GIT_TERMINAL_PROMPT": "0", "PYTHONNOUSERSITE": "1"})
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    output = bytearray()
    reason = "completed"
    try:
        async with asyncio.timeout(deadline_seconds):
            while chunk := await process.stdout.read(4096):
                output.extend(chunk)
                if len(output) > 32768:
                    reason = "output_limit"
                    break
            if reason == "completed":
                await process.wait()
    except TimeoutError:
        reason = "timeout"
    finally:
        # Also terminate child processes left behind by the test runner.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await process.wait()
    return {
        "status": reason,
        "exit_code": process.returncode,
        "output": bytes(output[:32768]).decode("utf-8", errors="replace"),
    }


async def capture_screen(max_bytes: int) -> dict:
    executable = shutil.which("grim")
    if not executable:
        return {"status": "unavailable", "reason": "grim is not installed"}
    with tempfile.TemporaryDirectory(prefix="codepet-screen-") as directory:
        target = Path(directory) / "screen.png"
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                "--",
                str(target),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                async with asyncio.timeout(10):
                    await process.wait()
            except TimeoutError:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
                return {"status": "error", "reason": "screen capture timed out"}
            if process.returncode != 0 or not target.exists():
                return {"status": "unavailable", "reason": "Wayland capture was rejected"}
            data = target.read_bytes()
            if len(data) > max_bytes:
                return {"status": "error", "reason": "screenshot exceeded size limit"}
            return {
                "status": "ok",
                "mime": "image/png",
                "encoding": "base64",
                "data": base64.b64encode(data).decode("ascii"),
            }
        except OSError:
            return {"status": "unavailable", "reason": "screen capture could not start"}


def sandbox_command(argv: list[str], cwd: Path, settings: Settings) -> list[str] | None:
    if settings.test_sandbox == "none":
        return argv
    executable = shutil.which("bwrap")
    if not executable:
        return None
    return [
        executable,
        "--die-with-parent",
        "--unshare-net",
        "--ro-bind",
        "/",
        "/",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--bind",
        str(cwd),
        str(cwd),
        "--chdir",
        str(cwd),
        "--",
        *argv,
    ]


class Tools:
    def __init__(
        self,
        workspace: Workspace,
        memory: MemoryStore,
        permissions: Permissions,
        editors: dict,
        terminals: dict,
        paused,
        settings: Settings,
    ):
        self.workspace, self.memory, self.permissions = workspace, memory, permissions
        self.editors, self.terminals, self.paused, self.settings = (
            editors,
            terminals,
            paused,
            settings,
        )
        self.gate = asyncio.Semaphore(1)

    async def execute(self, request: ToolInput) -> dict:
        status = "error"
        try:
            async with asyncio.timeout(45):
                async with self.gate:
                    result = await self._execute(request)
            status = result.get("status", "ok")
            return {"v": 1, **result}
        finally:
            # No source, prompts, terminal output or credentials in audit records.
            log.info(
                json.dumps({"tool": request.name, "project": request.project, "status": status})
            )

    async def _execute(self, r: ToolInput) -> dict:
        root = self.workspace.root(r.project)
        if r.name in {"get_active_editor", "get_diagnostics"}:
            if self.paused():
                return {"status": "paused"}
            event = self.editors.get(r.project)
            data = event.model_dump() if event else None
            if r.name == "get_diagnostics":
                data = data["diagnostics"] if data else []
            return {"status": "ok", "data": data}
        if r.name == "get_terminal_output":
            if self.paused():
                return {"status": "paused"}
            event = self.terminals.get(r.project)
            return {"status": "ok", "data": event.model_dump() if event else None}
        if r.name == "read_project_file":
            text = await asyncio.to_thread(self.workspace.read, r.project, r.path)
            return {"status": "ok", "path": r.path, "content": text}
        if r.name == "search_project":
            if not r.query:
                raise ValueError("Search query required")
            listing = await command(
                ["rg", "--files", "--no-config", "--glob", "!node_modules/**"], root
            )
            hits = []
            # Bounded file count, output and duration; all content passes file policy.
            for relative in listing["output"].splitlines()[:200]:
                try:
                    content = await asyncio.to_thread(self.workspace.read, r.project, relative)
                except (ValueError, OSError, UnicodeError):
                    continue
                for line, text in enumerate(content.splitlines(), 1):
                    if r.query in text:
                        hits.append({"path": relative, "line": line, "text": text[:300]})
                        if len(hits) == 30:
                            return {"status": "ok", "hits": hits, "limited": True}
            return {"status": "ok", "hits": hits, "limited": True}
        if r.name == "get_git_status":
            return await command(
                ["git", "--no-optional-locks", "status", "--porcelain=v1", "--untracked-files=no"],
                root,
            )
        if r.name == "get_git_diff":
            if not r.path:
                raise ValueError("Specify one authorized file for diff")
            await asyncio.to_thread(self.workspace.read, r.project, r.path)
            return await command(
                ["git", "--no-pager", "diff", "--no-ext-diff", "--no-textconv", "--", r.path], root
            )
        if r.name == "run_project_tests":
            if not self.permissions.consume(r):
                identity = self.permissions.request(r)
                return {
                    "status": "approval_required",
                    "approval_id": identity,
                    "command": [sys.executable, "-m", "pytest", "-q"],
                    "cwd": str(root),
                    "warning": "Tests execute project code with your user permissions, including filesystem and network access.",
                }
            test_argv = sandbox_command([sys.executable, "-m", "pytest", "-q"], root, self.settings)
            if test_argv is None:
                return {
                    "status": "sandbox_unavailable",
                    "reason": "Install bubblewrap or set CODEPET_TEST_SANDBOX=none knowingly.",
                }
            return await command(test_argv, root)
        if r.name == "propose_code_patch":
            self.workspace.path(r.project, r.path)
            return {"status": "proposal_only", "path": r.path, "patch": r.patch, "applied": False}
        if r.name == "get_learning_progress":
            notes = await asyncio.to_thread(self.memory.notes, r.project)
            return {
                "status": "ok",
                "items": [
                    item for item in notes if item["kind"] in {"topic", "difficulty", "preference"}
                ],
            }
        if r.name == "get_screen_context":
            if not self.settings.screen_capture:
                return {
                    "status": "unavailable",
                    "reason": "Screen capture is disabled; set CODEPET_SCREEN_CAPTURE=true to opt in.",
                }
            return await capture_screen(self.settings.screen_capture_max_bytes)
        return {"status": "unavailable", "reason": "Tool is not enabled in this release."}
