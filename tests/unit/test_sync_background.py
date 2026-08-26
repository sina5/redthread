"""BackgroundSyncer: the push must leave the caller's latency path without
losing the two promises sync_report made — nothing committed is ever lost,
and a failed push is reported, not swallowed."""

import subprocess
import threading

import pytest

from redthread.mcp import tools
from redthread.store import LocalStore, gitio
from redthread.sync import BackgroundSyncer
from redthread.sync import background as background_mod


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def _repo_with_remote(tmp_path, name="repo"):
    repo = tmp_path / name
    gitio.init(repo)
    gitio.configure_identity(repo, "Test", "test@example.com")
    gitio.set_remote(repo, str(_bare_remote(tmp_path)))
    return repo


def _store_with_remote(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    gitio.configure_identity(store.layout.root, "Test", "test@example.com")
    gitio.set_remote(store.layout.root, str(_bare_remote(tmp_path)))
    return store


@pytest.fixture
def syncer():
    s = BackgroundSyncer()
    yield s
    s.drain(timeout=30)


def test_schedule_returns_pushing_immediately_and_pushes(tmp_path, syncer):
    repo = _repo_with_remote(tmp_path)
    (repo / "f.txt").write_text("v1", encoding="utf-8")
    gitio.commit_if_dirty(repo, "v1")

    result = syncer.schedule(repo, "v1")
    assert result["status"] == "pushing"

    report = syncer.wait(repo, timeout=30)
    assert report["status"] == "pushed"
    assert gitio.ahead_count(repo) == 0


def test_commit_during_inflight_push_is_not_left_behind(tmp_path, syncer, monkeypatch):
    """A commit that lands while a push is in flight must trigger a rerun —
    otherwise it sits unpushed until some unrelated later sync."""
    repo = _repo_with_remote(tmp_path)
    first_push_started = threading.Event()
    release_first_push = threading.Event()
    real_sync_report = gitio.sync_report

    def gated_sync_report(root, message, remote="origin"):
        first_push_started.set()
        release_first_push.wait(timeout=30)
        return real_sync_report(root, message, remote=remote)

    monkeypatch.setattr(background_mod.gitio, "sync_report", gated_sync_report)

    (repo / "a.txt").write_text("a", encoding="utf-8")
    gitio.commit_if_dirty(repo, "a")
    syncer.schedule(repo, "a")
    assert first_push_started.wait(timeout=30)

    # Worker is mid-push: land a second commit and coalesce into it.
    (repo / "b.txt").write_text("b", encoding="utf-8")
    gitio.commit_if_dirty(repo, "b")
    assert syncer.schedule(repo, "b")["status"] == "pushing"

    release_first_push.set()
    report = syncer.wait(repo, timeout=30)
    assert report["status"] in ("pushed", "no_changes")
    assert gitio.ahead_count(repo) == 0


def test_previous_failure_is_surfaced_on_next_schedule(tmp_path, syncer, monkeypatch):
    repo = _repo_with_remote(tmp_path)

    def failing_sync_report(root, message, remote="origin"):
        return {"status": "failed", "detail": "remote unreachable"}

    monkeypatch.setattr(background_mod.gitio, "sync_report", failing_sync_report)
    (repo / "a.txt").write_text("a", encoding="utf-8")
    gitio.commit_if_dirty(repo, "a")
    syncer.schedule(repo, "a")
    syncer.wait(repo, timeout=30)

    monkeypatch.undo()
    result = syncer.schedule(repo, "b")
    assert result["status"] == "pushing"
    assert result["previous"]["status"] == "failed"
    assert "remote unreachable" in result["previous"]["detail"]
    syncer.wait(repo, timeout=30)


def test_memory_write_no_longer_blocks_on_the_network(tmp_path, monkeypatch):
    """The regression this feature exists for: memory_write must return
    without waiting on pull/push, reporting `pushing`, and the entry must
    still reach the remote."""
    store = _store_with_remote(tmp_path)

    result = tools.memory_write(store, "notes", "fast", "content", description="d")
    assert result["sync"]["status"] == "pushing"

    from redthread.sync import shared_syncer

    report = shared_syncer().wait(store.layout.root, timeout=30)
    assert report["status"] == "pushed"
    assert gitio.ahead_count(store.layout.root) == 0


def test_memory_write_without_remote_reports_committed_synchronously(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    gitio.configure_identity(store.layout.root, "Test", "test@example.com")

    result = tools.memory_write(store, "notes", "local", "content")
    assert result["sync"]["status"] == "committed"
    assert "remote" in result["sync"]["detail"]


def test_sync_status_reports_published_store(tmp_path):
    store = _store_with_remote(tmp_path)
    tools.memory_write(store, "notes", "k", "v")

    from redthread.sync import shared_syncer

    shared_syncer().wait(store.layout.root, timeout=30)
    status = tools.sync_status(store)
    assert status["has_remote"] is True
    assert status["in_flight"] is False
    assert status["last_push"]["status"] == "pushed"
    assert status["unpushed_commits"] == 0
    assert "Fully published" in status["_next"]
