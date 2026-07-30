"""Exercises the server through the real MCP client-session protocol (not
just the plain tools.py functions), proving the FastMCP wiring itself works.
"""

import asyncio
import json
import subprocess
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from redthread import hostconfig
from redthread.mcp import tools
from redthread.mcp.server import build_server
from redthread.store import LocalStore, gitio


def _call(store_path: Path, tool: str, host_repo: Path | None = None, **kwargs):
    async def _run():
        # Never let host_repo fall back to Path.cwd(): a developer checkout
        # has its own untracked .redthread.yaml, which would otherwise make
        # these tests attach to that real store instead of the tmp_path one.
        server = build_server(store_path, host_repo=host_repo or store_path.parent)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await session.call_tool(tool, kwargs)

    return asyncio.run(_run())


def _host_repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    gitio.configure_identity(path, "Test", "test@example.com")
    (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def test_all_tools_are_registered(tmp_path):
    async def _run():
        server = build_server(tmp_path / "store", host_repo=tmp_path)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await session.list_tools()

    result = asyncio.run(_run())
    names = {t.name for t in result.tools}
    assert names == {
        "context_bootstrap",
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
        "memory_search",
        "agents_md_bootstrap",
    }


def test_static_resources_are_registered(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])

    async def _run():
        server = build_server(store_path, host_repo=tmp_path)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await session.list_resources(), await session.list_resource_templates()

    resources, templates = asyncio.run(_run())
    assert {str(r.uri) for r in resources.resources} == {
        "redthread://project",
        "redthread://memory",
        "redthread://bootstrap",
    }
    assert {t.uriTemplate for t in templates.resourceTemplates} == {
        "redthread://memory/{namespace}/{key}",
        "redthread://handoff/{run_id}/{phase}",
        "redthread://summary/{run_id}/{phase}",
    }


def _read_resource(store_path: Path, uri: str, host_repo: Path):
    async def _run():
        server = build_server(store_path, host_repo=host_repo)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await session.read_resource(uri)

    return asyncio.run(_run())


def test_project_and_memory_resources_return_store_content(tmp_path):
    store_path = tmp_path / "store"
    store = LocalStore.init(store_path, project_id="demo", phases=["build"])
    store.memory_write("notes", "uv.md", "Use uv.\n", description="Toolchain choice")

    project = _read_resource(store_path, "redthread://project", tmp_path)
    assert json.loads(project.contents[0].text)["project_id"] == "demo"

    index = _read_resource(store_path, "redthread://memory", tmp_path)
    entries = json.loads(index.contents[0].text)
    assert entries[0]["key"] == "uv.md"
    assert entries[0]["description"] == "Toolchain choice"

    entry = _read_resource(store_path, "redthread://memory/notes/uv.md", tmp_path)
    assert "Use uv." in entry.contents[0].text


def test_handoff_and_summary_resources_return_phase_content(tmp_path):
    store_path = tmp_path / "store"
    store = LocalStore.init(store_path, project_id="demo", phases=["build"])
    run_id = store.start_run().run_id
    store.set_summary(run_id, "build", "# built\n")
    tools.handoff_publish(store, "build", headline="build ok", run_id=run_id)

    handoff = _read_resource(store_path, f"redthread://handoff/{run_id}/build", tmp_path)
    assert json.loads(handoff.contents[0].text)["headline"] == "build ok"

    summary = _read_resource(store_path, f"redthread://summary/{run_id}/build", tmp_path)
    assert summary.contents[0].text == "# built\n"


def test_bootstrap_resource_matches_the_tool_payload(tmp_path):
    store_path = tmp_path / "store"
    store = LocalStore.init(store_path, project_id="demo", phases=["build"])
    store.start_run()

    resource = _read_resource(store_path, "redthread://bootstrap", tmp_path)
    payload = json.loads(resource.contents[0].text)
    assert payload["current_run"] == tools.context_bootstrap(store)["current_run"]
    assert payload["project"]["phases"] == ["build"]


def test_store_init_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    result = _call(store_path, "store_init", project_id="demo", phases=["build", "test"])
    assert not result.isError
    assert LocalStore(store_path).manifest.project_id == "demo"


def test_run_and_context_roundtrip_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])

    async def _run():
        server = build_server(store_path, host_repo=tmp_path)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            run_result = await session.call_tool("run_start", {})
            run_id = run_result.structuredContent["run_id"]

            log_result = await session.call_tool(
                "context_log",
                {"run_id": run_id, "phase": "build", "type": "note", "payload": {"msg": "hi"}},
            )
            entry_id = log_result.structuredContent["entry_id"]

            read_result = await session.call_tool(
                "context_read", {"run_id": run_id, "phase": "build"}
            )
            return entry_id, read_result

    entry_id, read_result = asyncio.run(_run())
    entries = read_result.structuredContent["entries"]
    assert entries[0]["entry_id"] == entry_id
    assert entries[0]["payload"] == {"msg": "hi"}


def test_run_id_can_be_omitted_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])

    async def _run():
        server = build_server(store_path, host_repo=tmp_path)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            run_id = (await session.call_tool("run_start", {})).structuredContent["run_id"]
            logged = await session.call_tool("context_log", {"phase": "build", "type": "note"})
            return run_id, logged

    run_id, logged = asyncio.run(_run())
    assert not logged.isError
    assert logged.structuredContent["run_id"] == run_id


def test_context_bootstrap_through_call_tool(tmp_path):
    store_path = tmp_path / "store"
    LocalStore.init(store_path, project_id="demo", phases=["build"])

    result = _call(store_path, "context_bootstrap")
    assert not result.isError
    assert result.structuredContent["project"]["phases"] == ["build"]
    assert result.structuredContent["_next"]


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


def test_tool_call_auto_attaches_worktree_store_from_marker(tmp_path):
    host = _host_repo(tmp_path / "host")
    hostconfig.write_host_config(
        host,
        hostconfig.HostConfig(
            store=hostconfig.StoreRef(mode="worktree", path="store-wt", branch="redthread-store")
        ),
    )
    store_path = tmp_path / "store-wt"
    assert not store_path.exists()

    result = _call(
        store_path,
        "store_init",
        host_repo=host,
        project_id="demo",
        phases=["build"],
    )
    assert not result.isError
    assert gitio.current_branch(store_path) == "redthread-store"
    assert LocalStore(store_path).manifest.project_id == "demo"


def test_tool_call_without_marker_gives_normal_missing_store_error(tmp_path):
    host = _host_repo(tmp_path / "host")
    store_path = tmp_path / "store"

    result = _call(store_path, "run_list", host_repo=host)
    assert result.isError
