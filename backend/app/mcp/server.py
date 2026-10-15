"""Official MCP SDK v1 stdio adapter. No approval-granting tool is exposed."""

import asyncio
from uuid import UUID

import httpx
from mcp.server.fastmcp import FastMCP

from backend.app.core.config import Settings
from backend.app.schemas.messages import ToolInput


def create_server(settings: Settings | None = None, transport=None) -> FastMCP:
    settings = settings or Settings()
    server = FastMCP("CodePet AI")

    async def invoke(name: str, project: str, **arguments) -> dict:
        request = ToolInput(name=name, project=project, **arguments)
        async with asyncio.timeout(50):
            async with httpx.AsyncClient(
                base_url="http://127.0.0.1:8765",
                transport=transport,
                headers={"Authorization": "Bearer " + settings.token.get_secret_value()},
                timeout=45,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                result = await client.post("/v1/tools", json=request.model_dump(mode="json"))
                result.raise_for_status()
                return result.json()

    @server.tool()
    async def get_active_editor(project: str) -> dict:
        """Read authorized editor context, unavailable while observation is paused."""
        return await invoke("get_active_editor", project)

    @server.tool()
    async def get_diagnostics(project: str) -> dict:
        """Get editor diagnostics with one-based line numbers."""
        return await invoke("get_diagnostics", project)

    @server.tool()
    async def read_project_file(project: str, path: str) -> dict:
        """Read bounded UTF-8 source inside an authorized project, excluding secrets and symlinks."""
        return await invoke("read_project_file", project, path=path)

    @server.tool()
    async def search_project(project: str, query: str) -> dict:
        """Bounded literal search. Returns file, line and excerpt, never shell output execution."""
        return await invoke("search_project", project, query=query)

    @server.tool()
    async def get_git_status(project: str) -> dict:
        """Get tracked Git status without modifying the working tree."""
        return await invoke("get_git_status", project)

    @server.tool()
    async def get_git_diff(project: str, path: str) -> dict:
        """Get diff for one authorized file, with external diff drivers disabled."""
        return await invoke("get_git_diff", project, path=path)

    @server.tool()
    async def get_terminal_output(project: str) -> dict:
        """Read the most recent explicitly submitted terminal output for a project."""
        return await invoke("get_terminal_output", project)

    @server.tool()
    async def run_project_tests(project: str, approval_id: UUID | None = None) -> dict:
        """Request pytest execution. Requires a human approval through the desktop or CLI; a model cannot approve."""
        return await invoke("run_project_tests", project, approval_id=approval_id)

    @server.tool()
    async def propose_code_patch(project: str, path: str, patch: str) -> dict:
        """Return an inert patch proposal for human review. Does not apply or execute it."""
        return await invoke("propose_code_patch", project, path=path, patch=patch)

    @server.tool()
    async def get_screen_context(project: str) -> dict:
        """Capture the screen only when CODEPET_SCREEN_CAPTURE=true is enabled."""
        return await invoke("get_screen_context", project)

    @server.tool()
    async def get_learning_progress(project: str) -> dict:
        """Read user-managed topics, preferences and difficulties from this project only."""
        return await invoke("get_learning_progress", project)

    return server


def run() -> None:
    create_server().run(transport="stdio")


if __name__ == "__main__":
    run()
