import subprocess

from typer.testing import CliRunner

from redthread.cli import app

runner = CliRunner()


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def test_backend_set_and_list(tmp_path):
    target = tmp_path / "objects"

    result = runner.invoke(app, ["backend", "set", "objects", str(target)])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["backend", "list"])
    assert result.exit_code == 0, result.output
    assert "objects" in result.output


def test_sync_and_resume_cli_roundtrip(tmp_path):
    remote = _bare_remote(tmp_path)
    store = str(tmp_path / "clone-a")

    runner.invoke(app, ["init", "demo", "--phases", "build,test", "--store", store])
    subprocess.run(["git", "config", "user.name", "Test"], cwd=store, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=store, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=store, check=True)

    result = runner.invoke(app, ["run", "start", "--store", store])
    run_id = result.output.strip()

    result = runner.invoke(app, ["sync", "--store", store])
    assert result.exit_code == 0, result.output

    clone_b = str(tmp_path / "clone-b")
    result = runner.invoke(app, ["resume", run_id, "--store", clone_b, "--remote", str(remote)])
    assert result.exit_code == 0, result.output
    assert "resumed" in result.output
