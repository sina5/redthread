import subprocess

import pytest

from redthread.store import gitio


def _bare_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def _fresh_repo(path, branch="main"):
    gitio.init(path, branch=branch)
    gitio.configure_identity(path, "Test", "test@example.com")
    return path


def test_commit_if_dirty_detects_changes(tmp_path):
    repo = _fresh_repo(tmp_path / "repo")
    assert not gitio.is_dirty(repo)
    (repo / "a.txt").write_text("hi", encoding="utf-8")
    assert gitio.is_dirty(repo)
    assert gitio.commit_if_dirty(repo, "add a.txt") is True
    assert not gitio.is_dirty(repo)
    assert gitio.commit_if_dirty(repo, "noop") is False


def test_clone_and_push_pull_roundtrip(tmp_path):
    remote = _bare_remote(tmp_path)

    repo_a = _fresh_repo(tmp_path / "a")
    gitio.set_remote(repo_a, str(remote))
    (repo_a / "f.txt").write_text("from a", encoding="utf-8")
    gitio.commit_if_dirty(repo_a, "from a")
    gitio.push(repo_a)

    gitio.clone(str(remote), tmp_path / "b")
    repo_b = tmp_path / "b"
    gitio.configure_identity(repo_b, "Test", "test@example.com")
    assert (repo_b / "f.txt").read_text(encoding="utf-8") == "from a"


def test_sync_pushes_local_changes(tmp_path):
    remote = _bare_remote(tmp_path)
    repo = _fresh_repo(tmp_path / "a")
    gitio.set_remote(repo, str(remote))
    (repo / "f.txt").write_text("v1", encoding="utf-8")
    pushed = gitio.sync(repo, "v1")
    assert pushed is True

    gitio.clone(str(remote), tmp_path / "b")
    assert (tmp_path / "b" / "f.txt").read_text(encoding="utf-8") == "v1"


def test_sync_retries_after_concurrent_push(tmp_path):
    """Two nodes append-only writing at once must both land via sync()'s
    pull-rebase-retry loop — no data loss, no manual conflict resolution."""
    remote = _bare_remote(tmp_path)

    repo_a = _fresh_repo(tmp_path / "a")
    gitio.set_remote(repo_a, str(remote))
    (repo_a / "shared.txt").write_text("base", encoding="utf-8")
    gitio.sync(repo_a, "base")

    gitio.clone(str(remote), tmp_path / "b")
    repo_b = tmp_path / "b"
    gitio.configure_identity(repo_b, "Test", "test@example.com")

    # Both nodes add their own distinct file and race to push.
    (repo_a / "from-a.txt").write_text("a", encoding="utf-8")
    (repo_b / "from-b.txt").write_text("b", encoding="utf-8")

    assert gitio.sync(repo_a, "from a") is True
    assert gitio.sync(repo_b, "from b") is True  # must rebase+retry past a's push

    gitio.pull_rebase(repo_a)
    assert (repo_a / "from-b.txt").exists()
    assert (repo_b / "from-a.txt").exists()


def test_sync_without_remote_only_commits(tmp_path):
    repo = _fresh_repo(tmp_path / "solo")
    (repo / "f.txt").write_text("x", encoding="utf-8")
    assert gitio.sync(repo, "x") is True  # committed, no remote to push to
    assert not gitio.is_dirty(repo)


def test_run_git_failure_raises_giterror(tmp_path):
    repo = tmp_path / "not-a-repo"
    repo.mkdir()
    with pytest.raises(gitio.GitError):
        gitio.commit_if_dirty(repo, "should fail")
