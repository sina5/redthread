"""Isolate every test's Redthread config dir (node_id, paths.json) from the
real machine — otherwise tests would read/write the developer's actual
per-user AppData/XDG config directory."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("REDTHREAD_CONFIG_DIR", str(tmp_path / "_redthread_config"))
