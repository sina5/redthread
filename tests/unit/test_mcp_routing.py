"""Discovery mode: one MCP registration serving each project its own store."""

import asyncio
from pathlib import Path

import pytest

from redthread import constants
from redthread.mcp.routing import ClientRootsProbe, StoreRouter, WorkspaceLocator
from redthread.store import LocalStore, StoreError


def _project(root: Path, project_id: str) -> Path:
    """A workspace with its own store beside it, declared by a marker."""
    root.mkdir(parents=True)
    store = root.parent / f"{project_id}-store"
    LocalStore.init(store, project_id=project_id, phases=["build"], host_repo=root)
    return root


class _FakeRoot:
    def __init__(self, uri: str) -> None:
        self.uri = uri


class _FakeSession:
    """Stands in for the MCP client session's roots request."""

    def __init__(self, roots: list[_FakeRoot] | None = None, error: Exception | None = None):
        self._roots = roots or []
        self._error = error

    async def list_roots(self):
        if self._error:
            raise self._error
        return type("Result", (), {"roots": self._roots})()


# ---- WorkspaceLocator ------------------------------------------------------


def test_locate_finds_marker_in_the_starting_directory(tmp_path):
    (tmp_path / constants.MARKER_FILENAME).write_text("x", encoding="utf-8")
    assert WorkspaceLocator().locate(tmp_path) == tmp_path.resolve()


def test_locate_walks_up_from_a_subdirectory(tmp_path):
    (tmp_path / constants.MARKER_FILENAME).write_text("x", encoding="utf-8")
    nested = tmp_path / "src" / "pkg"
    nested.mkdir(parents=True)
    assert WorkspaceLocator().locate(nested) == tmp_path.resolve()


def test_locate_returns_none_when_no_ancestor_has_a_marker(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert WorkspaceLocator().locate(nested) is None


# ---- StoreRouter: discovery mode -------------------------------------------


def test_two_workspaces_resolve_to_their_own_stores(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    beta = _project(tmp_path / "beta", "beta")
    router = StoreRouter(default_workspace=tmp_path, environ={})

    assert router.resolve(alpha).store.manifest.project_id == "alpha"
    assert router.resolve(beta).store.manifest.project_id == "beta"


def test_resolve_from_a_subdirectory_of_the_workspace(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    nested = alpha / "src"
    nested.mkdir()
    router = StoreRouter(default_workspace=tmp_path, environ={})

    resolved = router.resolve(nested)
    assert resolved.workspace == alpha.resolve()
    assert resolved.store.manifest.project_id == "alpha"


def test_unmarked_workspace_refuses_rather_than_guessing(tmp_path):
    _project(tmp_path / "alpha", "alpha")
    plain = tmp_path / "plain"
    plain.mkdir()
    router = StoreRouter(default_workspace=tmp_path / "alpha", environ={})

    with pytest.raises(StoreError) as excinfo:
        router.resolve(plain)
    message = str(excinfo.value)
    assert constants.MARKER_FILENAME in message
    assert "redthread init" in message
    assert "redthread attach" in message


def test_bound_workspace_sticks_for_later_calls(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    _project(tmp_path / "beta", "beta")
    router = StoreRouter(default_workspace=tmp_path / "beta", environ={})

    router.resolve(alpha, bind=True)
    assert router.resolve().store.manifest.project_id == "alpha"


def test_environment_variable_supplies_the_workspace(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    router = StoreRouter(
        default_workspace=tmp_path,
        environ={constants.WORKSPACE_ENV_VAR: str(alpha)},
    )

    assert router.resolve().store.manifest.project_id == "alpha"


def test_explicit_workspace_beats_the_environment(tmp_path):
    _project(tmp_path / "alpha", "alpha")
    beta = _project(tmp_path / "beta", "beta")
    router = StoreRouter(
        default_workspace=tmp_path,
        environ={constants.WORKSPACE_ENV_VAR: str(tmp_path / "alpha")},
    )

    assert router.resolve(beta).store.manifest.project_id == "beta"


def test_launch_directory_is_the_last_resort(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    router = StoreRouter(default_workspace=alpha, environ={})

    assert router.resolve().store.manifest.project_id == "alpha"


def test_discovering_flag_reports_the_mode(tmp_path):
    assert StoreRouter(environ={}).discovering is True
    assert StoreRouter(fixed_store=tmp_path, environ={}).discovering is False


def test_store_path_for_names_a_store_that_does_not_exist_yet(tmp_path):
    workspace = tmp_path / "fresh"
    workspace.mkdir()
    (workspace / constants.MARKER_FILENAME).write_text(
        "schema_version: 1\nstore:\n  mode: repo\n  path: ../fresh-store\n",
        encoding="utf-8",
    )
    router = StoreRouter(default_workspace=tmp_path, environ={})

    assert router.store_path_for(workspace) == (tmp_path / "fresh-store").resolve()
    with pytest.raises(StoreError):
        router.resolve(workspace)  # located, but nothing to open yet


def test_forget_drops_the_cached_store(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    router = StoreRouter(default_workspace=tmp_path, environ={})
    first = router.resolve(alpha).store

    router.forget(first.layout.root)
    assert router.resolve(alpha).store is not first


# ---- StoreRouter: pinned mode ----------------------------------------------


def test_pinned_store_ignores_the_workspace(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    pinned = tmp_path / "pinned-store"
    LocalStore.init(pinned, project_id="pinned", phases=["build"])
    router = StoreRouter(fixed_store=pinned, default_workspace=tmp_path, environ={})

    resolved = router.resolve(alpha)
    assert resolved.store.manifest.project_id == "pinned"
    assert resolved.workspace == alpha.resolve()


# ---- ClientRootsProbe ------------------------------------------------------


def test_probe_prefers_a_root_that_declares_a_store(tmp_path):
    alpha = _project(tmp_path / "alpha", "alpha")
    plain = tmp_path / "plain"
    plain.mkdir()
    roots = [_FakeRoot(plain.as_uri()), _FakeRoot(alpha.as_uri())]

    probe = ClientRootsProbe()
    assert probe.choose(probe._to_paths(roots)) == alpha.resolve()


def test_probe_falls_back_to_the_first_root(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    roots = [_FakeRoot(first.as_uri()), _FakeRoot(second.as_uri())]

    probe = ClientRootsProbe()
    assert probe.choose(probe._to_paths(roots)) == first


def test_probe_returns_none_when_the_client_has_no_roots():
    assert asyncio.run(ClientRootsProbe().probe(_FakeSession([]))) is None


def test_probe_returns_none_when_the_client_refuses():
    session = _FakeSession(error=RuntimeError("roots not supported"))
    assert asyncio.run(ClientRootsProbe().probe(session)) is None


def test_probe_ignores_non_file_roots():
    roots = [_FakeRoot("https://example.com/repo")]
    assert ClientRootsProbe()._to_paths(roots) == []
