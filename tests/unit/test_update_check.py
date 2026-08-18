"""The update notice must be helpful when it fires and silent otherwise.

Nothing here touches the network: every test stubs `latest_version`. The
autouse conftest fixture disables the check outright, so each test that wants
it re-enables it explicitly — which also documents the opt-out.
"""

import json

import pytest

from redthread import constants, update_check


@pytest.fixture(autouse=True)
def _enable_check(monkeypatch):
    monkeypatch.delenv(update_check.DISABLE_ENV_VAR, raising=False)


def _pypi_says(monkeypatch, version):
    monkeypatch.setattr(update_check, "latest_version", lambda *a, **k: version)


def test_a_newer_release_is_announced_with_the_upgrade_command(monkeypatch):
    _pypi_says(monkeypatch, "0.11.0")
    message = update_check.update_message("0.10.0")
    assert message is not None
    assert "0.11.0" in message
    assert "uv pip install --upgrade redthread" in message
    assert "pip install --upgrade redthread" in message


def test_the_current_version_says_nothing(monkeypatch):
    _pypi_says(monkeypatch, "0.10.0")
    assert update_check.update_message("0.10.0") is None


def test_a_local_build_ahead_of_pypi_says_nothing(monkeypatch):
    """Working in the repo on an unreleased version is not a reason to nag."""
    _pypi_says(monkeypatch, "0.10.0")
    assert update_check.update_message("0.11.0") is None


def test_versions_compare_numerically_not_as_strings(monkeypatch):
    """The bug this pins: "0.9.0" > "0.10.0" is true for strings."""
    _pypi_says(monkeypatch, "0.10.0")
    assert update_check.update_message("0.9.0") is not None
    _pypi_says(monkeypatch, "0.9.0")
    assert update_check.update_message("0.10.0", force=True) is None


def test_an_unreachable_pypi_is_not_an_error(monkeypatch):
    _pypi_says(monkeypatch, None)
    assert update_check.update_message("0.10.0") is None


def test_a_prerelease_is_not_offered_as_an_upgrade(monkeypatch):
    _pypi_says(monkeypatch, "0.11.0rc1")
    assert update_check.update_message("0.10.0") is None


def test_the_check_is_throttled_to_once_a_day(monkeypatch):
    calls = []

    def counting(*a, **k):
        calls.append(1)
        return "0.11.0"

    monkeypatch.setattr(update_check, "latest_version", counting)
    assert update_check.update_message("0.10.0") is not None
    assert update_check.update_message("0.10.0") is None  # throttled
    assert len(calls) == 1
    assert update_check.update_message("0.10.0", force=True) is not None
    assert len(calls) == 2


def test_a_stale_stamp_lets_the_check_run_again(monkeypatch):
    _pypi_says(monkeypatch, "0.11.0")
    cache = update_check._cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    stale = -(constants.UPDATE_CHECK_INTERVAL_SECONDS + 1)
    cache.write_text(json.dumps({"checked_at": stale}), encoding="utf-8")
    assert update_check.update_message("0.10.0") is not None


def test_a_corrupt_cache_does_not_break_the_check(monkeypatch):
    _pypi_says(monkeypatch, "0.11.0")
    cache = update_check._cache_path()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text("not json", encoding="utf-8")
    assert update_check.update_message("0.10.0") is not None


def test_the_opt_out_silences_it(monkeypatch):
    _pypi_says(monkeypatch, "0.11.0")
    monkeypatch.setenv(update_check.DISABLE_ENV_VAR, "1")
    assert update_check.update_message("0.10.0") is None
