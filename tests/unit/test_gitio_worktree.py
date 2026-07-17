import subprocess

from redthread.store import gitio


def _host_repo(tmp_path):
    host = tmp_path / "host"
    subprocess.run(["git", "init", "-q", "-b", "main", str(host)], check=True)
    gitio.configure_identity(host, "Test", "test@example.com")
    (host / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=host, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=host, check=True)
    return host


def test_ensure_worktree_creates_orphan_branch_without_moving_host(tmp_path):
    host = _host_repo(tmp_path)
    wt = tmp_path / "store-wt"

    created = gitio.ensure_worktree(host, wt, "redthread-store")

    assert created is True
    assert gitio.current_branch(host) == "main"
    assert gitio.current_branch(wt) == "redthread-store"
    assert not (wt / "README.md").exists()  # orphan: no shared history with main


def test_ensure_worktree_attaches_to_existing_local_branch(tmp_path):
    host = _host_repo(tmp_path)
    wt1 = tmp_path / "store-wt-1"
    gitio.ensure_worktree(host, wt1, "redthread-store")
    gitio.configure_identity(wt1, "Test", "test@example.com")
    (wt1 / "f.txt").write_text("x", encoding="utf-8")
    gitio.commit_if_dirty(wt1, "add f.txt")
    gitio.remove_worktree(host, wt1)

    wt2 = tmp_path / "store-wt-2"
    created = gitio.ensure_worktree(host, wt2, "redthread-store")

    assert created is False
    assert (wt2 / "f.txt").read_text(encoding="utf-8") == "x"
    assert gitio.current_branch(host) == "main"


def test_ensure_worktree_attaches_to_remote_branch_on_fresh_host_clone(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)

    host_a = _host_repo(tmp_path)
    subprocess.run(["git", "-C", str(host_a), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(host_a), "push", "-q", "origin", "main"], check=True)

    wt_a = tmp_path / "store-wt-a"
    gitio.ensure_worktree(host_a, wt_a, "redthread-store")
    gitio.configure_identity(wt_a, "Test", "test@example.com")
    gitio.set_remote(wt_a, str(remote))
    (wt_a / "f.txt").write_text("from a", encoding="utf-8")
    gitio.sync(wt_a, "a writes")

    # A second, independent clone of the SAME host repo — simulating a new machine.
    host_b = tmp_path / "host-b"
    gitio.clone(str(remote), host_b)
    gitio.configure_identity(host_b, "Test", "test@example.com")

    wt_b = tmp_path / "store-wt-b"
    created = gitio.ensure_worktree(host_b, wt_b, "redthread-store")

    assert created is False  # attached to the remote branch, not re-orphaned
    assert (wt_b / "f.txt").read_text(encoding="utf-8") == "from a"
    assert gitio.current_branch(host_b) == "main"  # host clone's checkout untouched
