"""A slow or failing push must never hold the caller, and must never be
forgotten: a bounded push reports `committed` instead of blocking, every
outcome is recorded on disk, and the next session's bootstrap republishes
whatever an earlier one left behind."""

import subprocess
import time

from redthread.mcp import tools
from redthread.store import LocalStore, gitio
from redthread.sync import shared_syncer


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def _store_with_remote(tmp_path):
    store = LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])
    remote = _bare_remote(tmp_path)
    gitio.set_remote(store.layout.root, str(remote))
    return store, remote


def _remote_heads(remote):
    return subprocess.run(
        ["git", "ls-remote", "--heads", str(remote)], capture_output=True, text=True, check=True
    ).stdout


def test_exhausted_budget_reports_committed_not_failed(tmp_path):
    store, remote = _store_with_remote(tmp_path)
    root = store.layout.root
    (root / "memory" / "note").write_text("x\n", encoding="utf-8")

    report = gitio.sync_report(root, "write", budget=0)

    assert report["status"] == "committed"
    assert "0s" in report["detail"]
    assert not gitio.is_dirty(root)  # the commit happened before the budget ran out
    assert _remote_heads(remote) == ""


def test_a_slow_remote_is_cut_off_at_the_budget(tmp_path, monkeypatch):
    store, _ = _store_with_remote(tmp_path)
    root = store.layout.root
    seen = []

    def slow_pull(repo, remote="origin", timeout=gitio.DEFAULT_TIMEOUT_SECONDS):
        seen.append(timeout)
        time.sleep(timeout)
        raise gitio.GitTimeout("git pull timed out")

    monkeypatch.setattr(gitio, "pull_rebase", slow_pull)
    started = time.monotonic()

    report = gitio.sync_report(root, "write", budget=0.3)

    assert time.monotonic() - started < 5
    assert seen and seen[0] <= 0.3  # the git call got the remaining budget, not 60s
    assert report["status"] == "committed"


def test_push_outcome_survives_the_process_that_attempted_it(tmp_path, monkeypatch):
    store, _ = _store_with_remote(tmp_path)
    root = store.layout.root

    def refused(repo, remote="origin", timeout=gitio.DEFAULT_TIMEOUT_SECONDS):
        raise gitio.GitError("remote refused")

    monkeypatch.setattr(gitio, "pull_rebase", refused)
    gitio.sync_report(root, "write")

    recorded = gitio.last_push_outcome(root)
    assert recorded["status"] == "failed"
    assert "remote refused" in recorded["detail"]
    assert not gitio.is_dirty(root)  # the record lives in the git dir, never in the store


def test_bootstrap_republishes_commits_an_earlier_session_left_behind(tmp_path):
    store, remote = _store_with_remote(tmp_path)
    root = store.layout.root
    (root / "memory" / "note").write_text("x\n", encoding="utf-8")
    gitio.commit_report(root, "written, never pushed")

    payload = tools.context_bootstrap(store)

    assert payload["sync"]["republishing"] == "pushing"
    assert "earlier session" in payload["sync"]["_next"]
    report = shared_syncer().wait(root, timeout=60)
    assert report["status"] == "pushed"
    assert _remote_heads(remote) != ""


def test_bootstrap_says_nothing_when_the_remote_is_up_to_date(tmp_path):
    store, _ = _store_with_remote(tmp_path)
    gitio.sync_report(store.layout.root, "publish")

    payload = tools.context_bootstrap(store)

    assert "sync" not in payload


def test_bootstrap_leaves_a_store_that_does_not_publish_alone(tmp_path):
    store, remote = _store_with_remote(tmp_path)
    store.set_publish(False)
    gitio.commit_report(store.layout.root, "local only")

    payload = tools.context_bootstrap(store)

    assert "sync" not in payload
    assert _remote_heads(remote) == ""
