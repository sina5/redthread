from typer.testing import CliRunner

from redthread.cli import app

runner = CliRunner()


def test_present_cli_rejects_phase_outside_pipeline(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build,test", "--store", store])
    result = runner.invoke(app, ["run", "start", "--store", store])
    run_id = result.output.strip()

    result = runner.invoke(
        app, ["present", run_id, str(tmp_path / "out"), "--phase", "deploy", "--store", store]
    )
    assert result.exit_code != 0
    assert "not in this project's pipeline" in result.output


def test_present_cli_renders_outputs(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build,present", "--store", store])
    result = runner.invoke(app, ["run", "start", "--store", store])
    run_id = result.output.strip()

    out = tmp_path / "out"
    result = runner.invoke(app, ["present", run_id, str(out), "--store", store])
    assert result.exit_code == 0, result.output
    assert (out / "report.md").exists()
    assert (out / "deck.pptx").exists()
    assert (out / "docs" / "index.md").exists()
