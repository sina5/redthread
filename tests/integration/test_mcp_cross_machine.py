"""Agent memory written through the MCP tool layer on one node is visible,
byte-for-byte, on a completely fresh clone — the same claim the
architecture doc makes in section 7: "the same memory is visible on the
remote trainer, the local evaluator, and the next server you spin up," now
proven for the MCP-facing surface, not just LocalStore directly.
"""

import subprocess

from redthread.mcp import tools
from redthread.store import LocalStore, gitio


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def _push_fresh_store(store: LocalStore, remote_url: str) -> None:
    root = store.layout.root
    gitio.configure_identity(root, "Test", "test@example.com")
    gitio.set_remote(root, remote_url)
    gitio.sync(root, "init store")


def _clone(remote, tmp_path, name: str) -> LocalStore:
    gitio.clone(str(remote), tmp_path / name)
    store = LocalStore(tmp_path / name)
    gitio.configure_identity(store.layout.root, "Test", "test@example.com")
    gitio.set_remote(store.layout.root, str(remote))
    return store


def test_agent_memory_and_context_visible_on_fresh_clone(tmp_path):
    remote = _bare_remote(tmp_path)
    store_a = LocalStore.init(tmp_path / "clone-a", project_id="demo", phases=["build", "test"])
    _push_fresh_store(store_a, str(remote))

    # Node A: an agent writes long-term memory and logs context via the
    # exact functions the MCP tools delegate to.
    tools.memory_write(store_a, "agent", "preferences.md", "Use uv, never conda.")
    run_id = tools.run_start(store_a)["run_id"]
    tools.context_log(store_a, run_id, "build", "decision", payload={"note": "chose approach X"})
    gitio.sync(store_a.layout.root, "agent memory + context from node A")

    # A completely fresh clone on a "new server" — nothing shared but git.
    store_b = _clone(remote, tmp_path, "clone-b")

    assert tools.memory_read(store_b, "agent", "preferences.md") == "Use uv, never conda."
    assert tools.memory_list(store_b, "agent") == ["preferences.md"]

    entries = tools.context_read(store_b, run_id, phase="build")
    assert entries[0]["payload"] == {"note": "chose approach X"}


def test_memory_namespaces_are_independent_and_survive_sync_both_ways(tmp_path):
    remote = _bare_remote(tmp_path)
    store_a = LocalStore.init(tmp_path / "clone-a", project_id="demo", phases=["build"])
    _push_fresh_store(store_a, str(remote))
    store_b = _clone(remote, tmp_path, "clone-b")

    tools.memory_write(store_a, "node-a-notes", "a.md", "from A")
    gitio.sync(store_a.layout.root, "a writes")

    tools.memory_write(store_b, "node-b-notes", "b.md", "from B")
    gitio.sync(store_b.layout.root, "b writes")  # rebases past a, no conflict

    # store_b's own sync() already pulled A's prior commit before pushing.
    assert tools.memory_read(store_b, "node-a-notes", "a.md") == "from A"

    gitio.pull_rebase(store_a.layout.root)
    assert tools.memory_read(store_a, "node-b-notes", "b.md") == "from B"
    assert tools.memory_list(store_a, "node-a-notes") == ["a.md"]
