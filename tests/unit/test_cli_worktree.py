import subprocess

from typer.testing import CliRunner

from redthread.cli import app
from redthread.store import gitio

runner = CliRunner()


def _host_repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    gitio.configure_identity(path, "Test", "test@example.com")
    (path / "app.py").write_text("print('hi')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


def test_init_worktree_via_cli_does_not_move_host_branch(tmp_path):
    host = _host_repo(tmp_path / "host")
    store = tmp_path / "store-wt"

    result = runner.invoke(
        app,
        [
            "init",
            "demo",
            "--phases",
            "build,test",
            "--store",
            str(store),
            "--worktree-repo",
            str(host),
            "--branch",
            "redthread-store",
        ],
    )
    assert result.exit_code == 0, result.output
    assert gitio.current_branch(host) == "main"
    assert gitio.current_branch(store) == "redthread-store"


def test_init_worktree_leaves_the_orphan_branch_born_and_tracked(tmp_path):
    """The bug this closes: the branch had no commits, so it wasn't a ref at
    all — invisible to `git branch -a`, `git log` refused to run, and every
    file in the store was one `git clean -fdx` from gone."""
    host = _host_repo(tmp_path / "host")
    store = tmp_path / "store-wt"

    result = runner.invoke(
        app,
        [
            "init",
            "demo",
            "--phases",
            "build",
            "--store",
            str(store),
            "--worktree-repo",
            str(host),
            "--branch",
            "memories",
        ],
    )

    assert result.exit_code == 0, result.output
    assert gitio.has_commits(store)
    assert gitio.branch_exists(host, "memories")
    assert not gitio.is_dirty(store)
    branches = subprocess.run(
        ["git", "branch", "-a"], cwd=host, capture_output=True, text=True, check=True
    ).stdout
    assert "memories" in branches


def test_init_worktree_does_not_publish_memory_to_the_host_repos_remote(tmp_path):
    """A worktree shares the host repo's remotes, which in the field was a
    public GitHub repo the user never chose as a memory destination."""
    host = _host_repo(tmp_path / "host")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    gitio.set_remote(host, str(remote))
    store = tmp_path / "store-wt"
    runner.invoke(
        app,
        [
            "init",
            "demo",
            "--phases",
            "build",
            "--store",
            str(store),
            "--worktree-repo",
            str(host),
            "--branch",
            "memories",
        ],
    )
    note = tmp_path / "note.md"
    note.write_text("internal network topology\n", encoding="utf-8")

    result = runner.invoke(
        app, ["memory", "write", "notes", "net.md", str(note), "--store", str(store)]
    )

    assert result.exit_code == 0, result.output
    assert "committed" in result.output
    assert not gitio.is_dirty(store)  # durable locally
    refs = subprocess.run(
        ["git", "ls-remote", str(remote)], capture_output=True, text=True, check=True
    ).stdout
    assert "memories" not in refs  # but never published

    enabled = runner.invoke(app, ["publish", "--enable", "--store", str(store)])
    assert enabled.exit_code == 0, enabled.output
    pushed = runner.invoke(app, ["sync", "--store", str(store)])
    assert pushed.exit_code == 0, pushed.output
    refs = subprocess.run(
        ["git", "ls-remote", str(remote)], capture_output=True, text=True, check=True
    ).stdout
    assert "memories" in refs


def test_init_commits_even_on_a_machine_with_no_git_identity(tmp_path, monkeypatch):
    """CI and fresh machines have no `user.email`, which is exactly where an
    unborn branch would go unnoticed longest."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "absent.gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "absent.system.gitconfig"))
    store = tmp_path / "store"

    result = runner.invoke(app, ["init", "demo", "--phases", "build", "--store", str(store)])

    assert result.exit_code == 0, result.output
    assert "committed the store's scaffolding" in result.output
    assert gitio.has_commits(store)
    assert not gitio.is_dirty(store)
