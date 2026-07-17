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
