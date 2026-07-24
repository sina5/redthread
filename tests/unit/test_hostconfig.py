import subprocess

import pytest

from redthread import hostconfig
from redthread.store import LocalStore, StoreError, gitio


def _host_repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    gitio.configure_identity(path, "Test", "test@example.com")
    (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def test_init_worktree_writes_marker(tmp_path):
    host = _host_repo(tmp_path / "host")
    LocalStore.init_worktree(
        host, tmp_path / "store-wt", "redthread-store", project_id="demo", phases=["build"]
    )

    config = hostconfig.read_host_config(host)
    assert config is not None
    assert config.store.mode == "worktree"
    assert config.store.branch == "redthread-store"
    assert config.store.path == str((tmp_path / "store-wt").resolve())


def test_init_repo_mode_writes_marker_only_when_host_repo_given(tmp_path):
    host = _host_repo(tmp_path / "host")
    LocalStore.init(
        tmp_path / "store", project_id="demo", phases=["build"], host_repo=host
    )

    config = hostconfig.read_host_config(host)
    assert config is not None
    assert config.store.mode == "repo"
    assert config.store.url is None


def test_init_repo_mode_writes_no_marker_by_default(tmp_path):
    host = _host_repo(tmp_path / "host")
    LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])

    assert hostconfig.read_host_config(host) is None


def test_attach_worktree_mode_creates_fresh_orphan_when_nothing_exists_yet(tmp_path):
    host = _host_repo(tmp_path / "host")
    hostconfig.write_host_config(
        host,
        hostconfig.HostConfig(
            store=hostconfig.StoreRef(mode="worktree", path="store-wt", branch="redthread-store")
        ),
    )

    config = hostconfig.attach(host, tmp_path / "store-wt")
    assert config.store.mode == "worktree"
    # attach() only checks out the branch — the caller (LocalStore.init_worktree
    # or a subsequent LocalStore(...) open) is what puts project.yaml there
    assert not (tmp_path / "store-wt" / "project.yaml").exists()
    assert gitio.current_branch(host) == "main"
    assert gitio.current_branch(tmp_path / "store-wt") == "redthread-store"


def test_attach_worktree_mode_on_a_fresh_clone_finds_the_branch_via_origin(tmp_path):
    """The real scenario this feature targets: a second machine clones the
    HOST repo (never told --worktree-repo/--branch), and attach() finds the
    store branch by fetching origin — no separate store remote to know."""
    remote = tmp_path / "code-remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)

    host_a = _host_repo(tmp_path / "host-a")
    subprocess.run(["git", "-C", str(host_a), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(host_a), "push", "-q", "origin", "main"], check=True)

    store_a = LocalStore.init_worktree(
        host_a, tmp_path / "store-a", "redthread-store", project_id="demo", phases=["build"]
    )
    gitio.configure_identity(tmp_path / "store-a", "Test", "test@example.com")
    gitio.set_remote(tmp_path / "store-a", str(remote))
    run = store_a.start_run()
    gitio.sync(tmp_path / "store-a", "seed")

    # host-a also commits+pushes the marker, exactly as a human/agent would
    subprocess.run(["git", "-C", str(host_a), "add", hostconfig.MARKER_FILENAME], check=True)
    subprocess.run(
        ["git", "-C", str(host_a), "commit", "-q", "-m", "add marker"], check=True
    )
    subprocess.run(["git", "-C", str(host_a), "push", "-q", "origin", "main"], check=True)

    host_b = tmp_path / "host-b"
    gitio.clone(str(remote), host_b)
    assert hostconfig.marker_path(host_b).exists()

    config = hostconfig.attach(host_b, tmp_path / "store-b")
    assert config.store.mode == "worktree"
    store_b = LocalStore(tmp_path / "store-b")
    assert store_b.manifest.project_id == "demo"
    assert store_b.get_run(run.run_id) is not None
    assert gitio.current_branch(host_b) == "main"


def test_attach_repo_mode_requires_allow_clone(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    host = _host_repo(tmp_path / "host")
    # seed the remote from a throwaway clone, then point the marker at it directly
    LocalStore.init(tmp_path / "seed", project_id="demo", phases=["build"])
    gitio.configure_identity(tmp_path / "seed", "Test", "test@example.com")
    gitio.set_remote(tmp_path / "seed", str(remote))
    gitio.sync(tmp_path / "seed", "seed")
    hostconfig.write_host_config(
        host,
        hostconfig.HostConfig(
            store=hostconfig.StoreRef(mode="repo", path="store", url=str(remote))
        ),
    )

    with pytest.raises(StoreError):
        hostconfig.attach(host, tmp_path / "store", allow_clone=False)

    config = hostconfig.attach(host, tmp_path / "store", allow_clone=True)
    assert config.store.mode == "repo"
    assert (tmp_path / "store" / "project.yaml").exists()


def test_attach_repo_mode_syncs_url_from_existing_store_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    host = _host_repo(tmp_path / "host")
    LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"], host_repo=host)
    assert hostconfig.read_host_config(host).store.url is None

    gitio.configure_identity(tmp_path / "store", "Test", "test@example.com")
    gitio.set_remote(tmp_path / "store", str(remote))

    config = hostconfig.attach(host, tmp_path / "store")
    assert config.store.url == str(remote)
    assert hostconfig.read_host_config(host).store.url == str(remote)


def test_attach_raises_when_no_marker(tmp_path):
    host = _host_repo(tmp_path / "host")
    with pytest.raises(StoreError):
        hostconfig.attach(host, tmp_path / "store")
