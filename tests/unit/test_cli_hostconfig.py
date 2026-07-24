import subprocess

from typer.testing import CliRunner

from redthread import hostconfig
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


def test_init_worktree_repo_writes_marker_via_cli(tmp_path):
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
        ],
    )
    assert result.exit_code == 0, result.output
    config = hostconfig.read_host_config(host)
    assert config is not None
    assert config.store.mode == "worktree"
    assert config.store.branch == "redthread-store"


def test_init_repo_mode_host_repo_flag_writes_marker_via_cli(tmp_path):
    host = _host_repo(tmp_path / "host")
    store = tmp_path / "store"

    result = runner.invoke(
        app,
        [
            "init",
            "demo",
            "--phases",
            "build",
            "--store",
            str(store),
            "--host-repo",
            str(host),
        ],
    )
    assert result.exit_code == 0, result.output
    config = hostconfig.read_host_config(host)
    assert config is not None
    assert config.store.mode == "repo"


def test_attach_cli_creates_worktree_from_marker(tmp_path):
    host = _host_repo(tmp_path / "host")
    hostconfig.write_host_config(
        host,
        hostconfig.HostConfig(
            store=hostconfig.StoreRef(mode="worktree", path="store-wt", branch="redthread-store")
        ),
    )

    result = runner.invoke(
        app, ["attach", "--store", str(tmp_path / "store-wt"), "--host-repo", str(host)]
    )
    assert result.exit_code == 0, result.output
    assert "worktree" in result.output
    assert gitio.current_branch(tmp_path / "store-wt") == "redthread-store"


def test_attach_cli_fails_without_marker(tmp_path):
    host = _host_repo(tmp_path / "host")
    result = runner.invoke(
        app, ["attach", "--store", str(tmp_path / "store"), "--host-repo", str(host)]
    )
    assert result.exit_code != 0
