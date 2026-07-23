"""Exercises the server through the real MCP client-session protocol (not
just the plain tools.py functions), proving the FastMCP wiring itself works.
"""

import asyncio
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from redthread.mcp.server import build_server
from redthread.store import LocalStore


def _call(store_path: Path, tool: str, **kwargs):
    async def _run():
        server = build_server(store_path)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await session.call_tool(tool, kwargs)

    return asyncio.run(_run())


def test_all_tools_are_registered(tmp_path):
    async def _run():
        server = build_server(tmp_path / "store")
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await session.list_tools()

    result = asyncio.run(_run())
    names = {t.name for t in result.tools}
    assert names == {
        "store_init",
        "run_start",
        "run_list",
        "context_log",
        "context_read",
        "artifact_put",
        "artifact_get",
        "summary_update",
        "summary_get",
        "handoff_publish",
        "handoff_get",
        "memory_write",
        "memory_read",
        "memory_list",
        "agents_md_bootstrap",
    }


def test_store_init_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    result = _call(store_path, "store_init", project_id="demo", phases=["build", "test"])
    assert not result.isError
    assert LocalStore(store_path).manifest.project_id == "demo"


def test_run_and_context_roundtrip_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])

    async def _run():
        server = build_server(store_path)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            run_result = await session.call_tool("run_start", {})
            run_id = run_result.structuredContent["run_id"]

            log_result = await session.call_tool(
                "context_log",
                {"run_id": run_id, "phase": "build", "type": "note", "payload": {"msg": "hi"}},
            )
            entry_id = log_result.structuredContent["result"]

            read_result = await session.call_tool(
                "context_read", {"run_id": run_id, "phase": "build"}
            )
            return entry_id, read_result

    entry_id, read_result = asyncio.run(_run())
    entries = read_result.structuredContent["result"]
    assert entries[0]["entry_id"] == entry_id
    assert entries[0]["payload"] == {"msg": "hi"}


def test_memory_roundtrip_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])

    write_result = _call(
        store_path, "memory_write", namespace="agent", key="notes.md", content="remember this"
    )
    assert not write_result.isError

    read_result = _call(store_path, "memory_read", namespace="agent", key="notes.md")
    assert read_result.structuredContent["result"] == "remember this"


def test_error_propagates_as_tool_error(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])

    result = _call(store_path, "context_log", run_id="no-such-run", phase="build", type="note")
    assert result.isError


def test_agents_md_bootstrap_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    result = _call(store_path, "agents_md_bootstrap", project_dir=str(project_dir))
    assert not result.isError
    assert result.structuredContent["status"] == "created"
    assert (project_dir / "AGENTS.md").exists()
