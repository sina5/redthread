import io
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


# ----- never block waiting for a human --------------------------------------
#
# Every git call is made with output captured, typically from an MCP server
# with no terminal. A credential prompt there is invisible and unbounded, so
# these tests pin the three things that keep it from happening.


class _FakeProc:
    """Stand-in for a git process, for tests that must not really run git."""

    def __init__(self, stderr_lines=(), returncode=0, hang=False):
        self.pid = -1
        self.stderr = iter(list(stderr_lines))
        self.stdout = io.StringIO("")
        self.returncode = returncode
        self.killed = False
        self._hang = hang

    def communicate(self, timeout=None):
        if self._hang:
            self._hang = False  # the post-kill reap must succeed
            raise subprocess.TimeoutExpired("git", timeout or 0)
        return "", "\n".join(self.stderr)

    def wait(self):
        return self.returncode

    def kill(self):
        self.killed = True


def _capture_popen_kwargs(monkeypatch, **proc_kwargs):
    """Record the kwargs gitio passes to subprocess.Popen, and stub the call."""
    recorded = {}

    def fake_popen(args, **kwargs):
        recorded.update(kwargs)
        recorded["args"] = args
        proc = _FakeProc(**proc_kwargs)
        recorded["proc"] = proc
        return proc

    monkeypatch.setattr(gitio.subprocess, "Popen", fake_popen)
    return recorded


def _capture_communicate_timeout(monkeypatch):
    """Record the timeout gitio allows one git call, without running git."""
    recorded = _capture_popen_kwargs(monkeypatch)
    original = _FakeProc.communicate

    def spy(self, timeout=None):
        recorded["timeout"] = timeout
        return original(self, timeout)

    monkeypatch.setattr(_FakeProc, "communicate", spy)
    return recorded


def test_git_never_inherits_stdin(tmp_path, monkeypatch):
    recorded = _capture_popen_kwargs(monkeypatch)
    gitio.is_dirty(tmp_path)
    assert recorded["stdin"] is subprocess.DEVNULL


def test_git_is_told_not_to_prompt_for_credentials(tmp_path, monkeypatch):
    recorded = _capture_popen_kwargs(monkeypatch)
    gitio.is_dirty(tmp_path)
    assert recorded["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert recorded["env"]["GCM_INTERACTIVE"] == "never"


def test_the_rest_of_the_environment_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("REDTHREAD_CANARY", "kept")
    recorded = _capture_popen_kwargs(monkeypatch)
    gitio.is_dirty(tmp_path)
    assert recorded["env"]["REDTHREAD_CANARY"] == "kept"


def test_every_git_call_carries_a_timeout(tmp_path, monkeypatch):
    recorded = _capture_communicate_timeout(monkeypatch)
    gitio.is_dirty(tmp_path)
    assert recorded["timeout"] == gitio.DEFAULT_TIMEOUT_SECONDS


def test_clone_has_no_wall_clock_timeout(tmp_path, monkeypatch):
    """A big store is legitimately slow to clone; a deadline would kill it."""
    recorded = _capture_popen_kwargs(monkeypatch)
    gitio.clone("https://example.invalid/x.git", tmp_path / "dest")
    assert "timeout" not in recorded


def test_clone_still_aborts_on_a_dead_connection(tmp_path, monkeypatch):
    """What replaces the deadline: git's own throughput floor.

    Dropping the wall-clock cap is only safe because a transfer that has
    stopped moving still fails instead of hanging forever.
    """
    recorded = _capture_popen_kwargs(monkeypatch)
    gitio.clone("https://example.invalid/x.git", tmp_path / "dest")
    args = recorded["args"]
    assert f"http.lowSpeedLimit={gitio.CLONE_STALL_LIMIT_BYTES_PER_SECOND}" in args
    assert f"http.lowSpeedTime={gitio.CLONE_STALL_LIMIT_SECONDS}" in args


def _time_out_on(monkeypatch, subcommand):
    """Make one git subcommand hang until its timeout; the rest succeed.

    Returns the list of processes gitio tore down, so callers can assert on
    the cleanup. Stubbing `_terminate_tree` is also what keeps its real
    implementation from re-entering the patched Popen to run `taskkill`.
    """
    killed = []
    monkeypatch.setattr(gitio, "_terminate_tree", killed.append)

    def fake_popen(args, **kwargs):
        return _FakeProc(hang=args[1] == subcommand)

    monkeypatch.setattr(gitio.subprocess, "Popen", fake_popen)
    return killed


def test_a_hanging_git_call_becomes_a_giterror(tmp_path, monkeypatch):
    _time_out_on(monkeypatch, "status")
    with pytest.raises(gitio.GitError, match="timed out"):
        gitio.is_dirty(tmp_path)


def test_a_timeout_raises_even_when_the_caller_ignores_return_codes(tmp_path, monkeypatch):
    # push() and pull_rebase() both pass check=False, so a timeout that
    # respected it would be swallowed and the hang would go unreported.
    _time_out_on(monkeypatch, "push")
    with pytest.raises(gitio.GitError, match="timed out"):
        gitio._run(["push", "-q", "origin", "main"], cwd=tmp_path, check=False)


def test_a_timed_out_git_call_kills_the_transport_helper_too(tmp_path, monkeypatch):
    """Killing `git` alone leaves `git-remote-https` holding the connection."""
    killed = _time_out_on(monkeypatch, "push")

    with pytest.raises(gitio.GitError):
        gitio._run(["push", "-q", "origin", "main"], cwd=tmp_path, check=False)

    assert killed, "a timed-out git call must tear down its whole process tree"


# ----- a long clone says so, and a failed one cleans up ----------------------


def test_a_long_clone_reports_that_it_is_still_running(tmp_path, monkeypatch):
    """With no deadline, silence is the only thing left to worry a caller."""
    monkeypatch.setattr(
        gitio.subprocess,
        "Popen",
        lambda args, **kw: _FakeProc(stderr_lines=["Receiving objects:  40%\n"]),
    )
    seen = []
    gitio._stream_progress(["clone"], cwd=tmp_path, on_progress=seen.append, interval=0)

    assert seen, "a clone that produces output must report it"
    assert "Receiving objects" in seen[-1]
    assert "elapsed" in seen[-1]


def test_a_silent_clone_still_reports_that_it_is_alive(tmp_path, monkeypatch):
    monkeypatch.setattr(
        gitio.subprocess, "Popen", lambda args, **kw: _FakeProc(stderr_lines=["\n"])
    )
    seen = []
    gitio._stream_progress(["clone"], cwd=tmp_path, on_progress=seen.append, interval=0)

    assert seen and "still running" in seen[0]


def test_a_failed_clone_removes_the_directory_it_created(tmp_path):
    """Otherwise the retry hits "already exists and is not an empty directory"."""
    dest = tmp_path / "store"
    with pytest.raises(gitio.GitError):
        gitio.clone(str(tmp_path / "nope.git"), dest)

    assert not dest.exists()


def test_a_failed_clone_leaves_a_preexisting_directory_alone(tmp_path):
    """Only clean up wreckage this call made — never the user's own files."""
    dest = tmp_path / "store"
    dest.mkdir()
    (dest / "precious.txt").write_text("mine", encoding="utf-8")

    with pytest.raises(gitio.GitError):
        gitio.clone(str(tmp_path / "nope.git"), dest)

    assert (dest / "precious.txt").read_text(encoding="utf-8") == "mine"


def test_a_failed_clone_says_how_to_do_it_by_hand(tmp_path):
    """The usual cause is credentials, which this module refuses to prompt for."""
    remote = str(tmp_path / "nope.git")
    with pytest.raises(gitio.GitError, match="git clone") as exc:
        gitio.clone(remote, tmp_path / "store")

    assert remote in str(exc.value)


def test_sync_report_reports_a_hung_push_instead_of_hanging(tmp_path):
    """The payoff: the entry is committed, the push fails, the caller is told.

    sync_report already promised never to lose a write to a git error. A hang
    was the one failure mode that broke that promise, because it never
    returned at all.
    """
    repo = _fresh_repo(tmp_path / "store")
    gitio.set_remote(repo, "https://example.invalid/unreachable.git")
    (repo / "memory.md").write_text("something worth keeping", encoding="utf-8")

    result = gitio.sync_report(repo, "add memory")

    assert result["status"] == "failed"
    assert "detail" in result
    # The write itself survived, which is the whole point.
    assert not gitio.is_dirty(repo)
    assert (repo / "memory.md").exists()
