import pytest

pytest.importorskip("mcp.server.fastmcp", exc_type=ImportError)

from backend.app.mcp.server import create_server


async def test_mcp_registers_schemas_without_approval_capability(settings):
    server = create_server(settings)
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert len(tools) == 11
    assert "read_project_file" in tools
    assert "approve" not in tools
    assert "grant_permission" not in tools
    assert set(tools["read_project_file"].inputSchema["required"]) == {"project", "path"}
    assert "approval_id" in tools["run_project_tests"].inputSchema["properties"]
