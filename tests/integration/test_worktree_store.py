"""The requested acceptance scenario: a store that lives as an orphan-branch
git worktree of a host repo (e.g. the user's code repo), so the host repo's
currently checked-out branch is never touched, and syncing/resuming reuses
all the same portable-sync machinery unchanged.
"""

import subprocess

import pytest

from redthread.resume import resume_worktree
from redthread.store import LocalStore, StoreError, gitio


def _host_repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    gitio.configure_identity(path, "Test", "test@example.com")
    (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def test_init_worktree_never_moves_host_branch(tmp_path):
    host = _host_repo(tmp_path / "host")
    wt = tmp_path / "store-wt"

    store = LocalStore.init_worktree(
        host, wt, "redthread-store", project_id="demo", phases=["build", "test"]
    )

    assert store.manifest.project_id == "demo"
    assert gitio.current_branch(host) == "main"
    assert gitio.current_branch(wt) == "redthread-store"
    # the code file from the host's checked-out branch never leaks into the store
    assert not (wt / "app.py").exists()


def test_init_worktree_rejects_existing_store(tmp_path):
    host = _host_repo(tmp_path / "host")
    wt = tmp_path / "store-wt"
    LocalStore.init_worktree(host, wt, "redthread-store", project_id="demo", phases=["build"])

    with pytest.raises(StoreError):
        LocalStore.init_worktree(host, wt, "redthread-store", project_id="demo", phases=["build"])


def test_full_worktree_lifecycle_across_two_host_clones(tmp_path):
    remote = tmp_path / "code-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)

    host_a = _host_repo(tmp_path / "host-a")
    subprocess.run(["git", "-C", str(host_a), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(host_a), "push", "-q", "origin", "main"], check=True)

    wt_a = tmp_path / "store-wt-a"
    store_a = LocalStore.init_worktree(
        host_a, wt_a, "redthread-store", project_id="demo", phases=["build", "test"]
    )
    gitio.configure_identity(wt_a, "Test", "test@example.com")
    gitio.set_remote(wt_a, str(remote))
    run = store_a.start_run()
    store_a.log(run.run_id, "build", "decision", payload={"note": "chose approach A"})
    gitio.sync(wt_a, "node A progress")

    # A second machine: clones the HOST (code) repo the normal way — no
    # separate remote for the store is ever configured by the user.
    host_b = tmp_path / "host-b"
    gitio.clone(str(remote), host_b)
    gitio.configure_identity(host_b, "Test", "test@example.com")

    wt_b = tmp_path / "store-wt-b"
    record = resume_worktree(host_b, wt_b, "redthread-store", run.run_id, host="node-b")

    assert len(record.nodes) == 2
    assert record.nodes[0].left is not None
    assert record.nodes[1].host == "node-b"

    store_b = LocalStore(wt_b)
    entries = store_b.read_entries(run.run_id, phase="build")
    assert any(e.payload.get("note") == "chose approach A" for e in entries)
    assert any(e.type == "milestone" and e.payload.get("event") == "resumed" for e in entries)

    # the host repo's own checked-out branch was never disturbed on either machine
    assert gitio.current_branch(host_a) == "main"
    assert gitio.current_branch(host_b) == "main"
