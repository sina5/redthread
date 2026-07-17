import json

from typer.testing import CliRunner

from redthread.cli import app

runner = CliRunner()


def test_cli_init_log_read_roundtrip(tmp_path):
    store = str(tmp_path / "store")

    result = runner.invoke(
        app, ["init", "demo", "--phases", "build,test,present", "--store", store]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["run", "start", "--store", store])
    assert result.exit_code == 0, result.output
    run_id = result.output.strip()

    result = runner.invoke(
        app, ["log", run_id, "build", "note", '{"msg": "hi"}', "--store", store]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["read", run_id, "--store", store, "--type", "note"])
    assert result.exit_code == 0, result.output
    logged = json.loads(result.output.strip())
    assert logged["payload"] == {"msg": "hi"}
    assert logged["phase"] == "build"


def test_cli_rejects_phase_outside_pipeline(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build,test", "--store", store])
    result = runner.invoke(app, ["run", "start", "--store", store])
    run_id = result.output.strip()

    result = runner.invoke(app, ["log", run_id, "deploy", "note", "{}", "--store", store])
    assert result.exit_code != 0
