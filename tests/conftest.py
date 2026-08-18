"""Isolate every test's Redthread config dir (node_id, paths.json) from the
real machine — otherwise tests would read/write the developer's actual
per-user AppData/XDG config directory."""

import pytest

from redthread import update_check


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("REDTHREAD_CONFIG_DIR", str(tmp_path / "_redthread_config"))
    # No test may reach pypi.org. The update check is best-effort and would
    # merely be slow rather than failing, which is exactly the kind of
    # network dependency that makes a suite flaky for no diagnostic value.
    monkeypatch.setenv(update_check.DISABLE_ENV_VAR, "1")
