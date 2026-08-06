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
    LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"], host_repo=host)

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

    # init_worktree already committed the marker on host-a's branch; all a
    # human/agent has left to do is push the branch they were already on.
    assert store_a.marker_status["committed"]
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


def _tracked(repo) -> set[str]:
    out = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split())


def test_init_worktree_bootstraps_a_project_that_is_not_a_git_repo_yet(tmp_path):
    """The day-one flow: a project directory with some files and no git at
    all becomes a Redthread host in one command."""
    project = tmp_path / "brand-new"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")

    LocalStore.init_worktree(
        project,
        project / "redthread-store",
        "redthread-store",
        project_id="demo",
        phases=["build"],
    )

    assert gitio.is_repo(project)
    assert gitio.current_branch(project) == "main"
    assert (project / "redthread-store" / "project.yaml").exists()
    assert gitio.current_branch(project / "redthread-store") == "redthread-store"


def test_init_worktree_commits_only_the_marker_and_gitignore(tmp_path):
    host = _host_repo(tmp_path / "host")
    # Something the user had staged but not committed: it must survive
    # untouched, not get swept into Redthread's commit.
    (host / "wip.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "wip.py"], cwd=host, check=True)

    store = LocalStore.init_worktree(
        host, host / "redthread-store", "redthread-store", project_id="demo", phases=["build"]
    )

    assert store.marker_status == {"ignored": True, "committed": True, "detail": None}
    assert _tracked(host) == {"app.py", ".gitignore", hostconfig.MARKER_FILENAME}
    assert (host / ".gitignore").read_text(encoding="utf-8").splitlines() == ["redthread-store/"]
    # wip.py is still staged and still uncommitted — exactly as it was.
    assert (
        "A  wip.py"
        in subprocess.run(
            ["git", "status", "--porcelain"], cwd=host, capture_output=True, text=True, check=True
        ).stdout
    )


def test_init_worktree_can_skip_committing_the_marker(tmp_path):
    host = _host_repo(tmp_path / "host")

    store = LocalStore.init_worktree(
        host,
        host / "redthread-store",
        "redthread-store",
        project_id="demo",
        phases=["build"],
        publish_marker=False,
    )

    assert store.marker_status is None
    assert hostconfig.marker_path(host).exists()  # written, just not committed
    assert _tracked(host) == {"app.py"}
    assert not (host / ".gitignore").exists()


def test_publish_marker_reports_a_failed_commit_without_raising(tmp_path):
    # A repo with no user identity configured: `git commit` refuses.
    host = tmp_path / "host"
    host.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(host)], check=True)
    for key in ("user.name", "user.email"):
        subprocess.run(["git", "-C", str(host), "config", key, ""], check=True)
    hostconfig.write_host_config(
        host,
        hostconfig.HostConfig(store=hostconfig.StoreRef(mode="worktree", path="s", branch="b")),
    )

    status = hostconfig.publish_marker(host, host / "s")

    assert status["committed"] is False
    assert status["detail"]


def test_ensure_ignored_is_idempotent_and_skips_stores_outside_the_repo(tmp_path):
    host = _host_repo(tmp_path / "host")

    assert hostconfig.ensure_ignored(host, host / "redthread-store") is True
    assert hostconfig.ensure_ignored(host, host / "redthread-store") is False
    assert hostconfig.ensure_ignored(host, tmp_path / "elsewhere") is False
    assert (host / ".gitignore").read_text(encoding="utf-8").splitlines() == ["redthread-store/"]


def test_ensure_repo_leaves_an_existing_repo_and_its_subdirs_alone(tmp_path):
    host = _host_repo(tmp_path / "host")
    nested = host / "packages" / "api"
    nested.mkdir(parents=True)

    assert gitio.ensure_repo(host) is False
    # A directory inside a repo already has version control; giving it a
    # second, nested repo would be worse than doing nothing.
    assert gitio.ensure_repo(nested) is False
    assert not (nested / ".git").exists()


# ---- check_binding -------------------------------------------------------
# An MCP server registered once and reused across workspaces serves the same
# store to every project. These pin the signal that catches it.


def test_check_binding_ok_when_marker_names_this_store(tmp_path):
    host = _host_repo(tmp_path / "host")
    store = tmp_path / "store-wt"
    LocalStore.init_worktree(host, store, "redthread-store", project_id="demo", phases=["build"])

    result = hostconfig.check_binding(host, store)
    assert result["status"] == "ok"


def test_check_binding_mismatch_when_marker_names_another_store(tmp_path):
    host = _host_repo(tmp_path / "host")
    own = tmp_path / "store-wt"
    LocalStore.init_worktree(host, own, "redthread-store", project_id="mine", phases=["build"])
    other = LocalStore.init(tmp_path / "other-store", project_id="theirs", phases=["build"])

    result = hostconfig.check_binding(host, other.layout.root)
    assert result["status"] == "mismatch"
    assert result["expected_store"] == str(own.resolve())
    assert result["store"] == str(other.layout.root.resolve())


def test_check_binding_ok_when_store_lives_inside_workspace(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    store = workspace / "redthread-store"
    LocalStore.init(store, project_id="demo", phases=["build"])

    assert hostconfig.check_binding(workspace, store)["status"] == "ok"


def test_check_binding_unverified_when_nothing_ties_store_to_workspace(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    store = LocalStore.init(tmp_path / "elsewhere", project_id="other", phases=["build"])

    result = hostconfig.check_binding(workspace, store.layout.root)
    assert result["status"] == "unverified"
    assert result["expected_store"] is None
