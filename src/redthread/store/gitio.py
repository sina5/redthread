"""Git subprocess wrapper: clone/pull-rebase/commit/push with retry.

This is the sync transport described in the architecture: the git remote is
the hub, nodes are interchangeable clients. `sync()` is the one function
adapters and the daemon actually call — it commits local changes, rebases
onto whatever the remote has, and pushes, retrying the rebase+push if
another node pushed in the meantime.
"""

import contextlib
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from redthread import constants
from redthread.store.errors import StoreError


class GitError(StoreError):
    pass


class GitTimeout(GitError):
    """A git invocation ran past its timeout and was killed."""


class PushBudgetExceeded(GitError):
    """A sync ran out of its total time budget before the push landed.

    Not a failure of the write: the commit already happened, so the memory
    is durable here and the next sync publishes it. It exists so a slow
    remote costs the caller a bounded wait instead of minutes of retries.
    """


# Re-exported so call sites read naturally; defined in `constants`.
DEFAULT_TIMEOUT_SECONDS = constants.GIT_TIMEOUT_SECONDS
CLONE_PROGRESS_INTERVAL_SECONDS = constants.CLONE_PROGRESS_INTERVAL_SECONDS
CLONE_STALL_LIMIT_BYTES_PER_SECOND = constants.CLONE_STALL_LIMIT_BYTES_PER_SECOND
CLONE_STALL_LIMIT_SECONDS = constants.CLONE_STALL_LIMIT_SECONDS


def _noninteractive_env() -> dict[str, str]:
    """Environment that makes git fail rather than wait for a human.

    Every call here captures stdout and stderr, and usually runs inside an MCP
    server with no terminal attached. A credential prompt in that setting is
    not a question anyone can answer — it is an invisible, unbounded hang, and
    with a GUI credential helper it may not even appear on screen. These
    variables turn that case into an ordinary non-zero exit, which
    `sync_report` can report as a failed push while the commit stays safely on
    disk.

    The trade-off is that first-time authentication no longer prompts: a
    machine with no stored credentials has to `git push` once by hand to
    establish them.
    """
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"  # don't prompt on the terminal
    env["GCM_INTERACTIVE"] = "never"  # don't let Git Credential Manager open a dialog
    return env


# On POSIX, put git in its own process group so the whole group can be
# signalled at once. Windows has no equivalent knob here; `_terminate_tree`
# uses taskkill's /T instead.
_OWN_PROCESS_GROUP: dict[str, bool] = {} if sys.platform == "win32" else {"start_new_session": True}


def _terminate_tree(proc: "subprocess.Popen") -> None:
    """Kill git *and* whatever transport helper it spawned.

    Killing the `git` process alone is not enough: a network operation runs
    through a helper (`git-remote-https`, and under a credential manager
    possibly a GUI process too), and those are children, not the process we
    hold a handle to. Left alive, a helper keeps the connection — and any
    file handles into the repo — open after we have already given up on it,
    which on Windows is enough to make a subsequent cleanup of the directory
    fail. Best-effort throughout: a process that already exited is the
    outcome we wanted anyway.
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
            check=False,
        )
    else:
        with contextlib.suppress(OSError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    with contextlib.suppress(OSError):
        proc.kill()


def _run(
    args: list[str],
    cwd: Path,
    check: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        ["git", *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=_noninteractive_env(),
        **_OWN_PROCESS_GROUP,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_tree(proc)
        with contextlib.suppress(subprocess.TimeoutExpired, OSError):
            proc.communicate(timeout=constants.GIT_REAP_TIMEOUT_SECONDS)
        # Raised whatever `check` says: a timeout leaves no return code to
        # inspect, and no caller wants it silently treated as a plain failure.
        raise GitTimeout(f"git {' '.join(args)} timed out after {timeout:g}s in {cwd}") from exc
    result = subprocess.CompletedProcess(args, proc.returncode, stdout=stdout, stderr=stderr)
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed in {cwd}:\n{result.stderr.strip()}")
    return result


def init(dest: Path, branch: str = "main") -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    _run(["init", "-q", "-b", branch], cwd=dest)


def is_repo(path: Path) -> bool:
    """True if `path` is a git work tree, or sits inside one. The "inside one"
    part is deliberate: a project nested in a larger repo should attach to
    that repo, not quietly get a second one of its own."""
    result = _run(["rev-parse", "--is-inside-work-tree"], cwd=path, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_repo(path: Path, branch: str = "main") -> bool:
    """Make `path` a git repo if it isn't one already; returns True if this
    call created it. Lets a brand-new project become a Redthread host without
    a separate `git init` step — worktree mode needs a repo to hang the
    orphan branch off, and requiring one is a pointless stumble on day one.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if is_repo(path):
        return False
    # Pin the branch name rather than inheriting init.defaultBranch, for the
    # same reason store repos do: two machines shouldn't disagree on it.
    _run(["init", "-q", "-b", branch], cwd=path)
    return True


def _identity_args(repo: Path) -> list[str]:
    """`-c user.*` overrides, and only when git has no identity of its own.

    A machine that has never run `git config user.email` — a fresh box, a
    container, CI — makes every `git commit` fail outright. For a memory
    store that means the first commit never happens, so the branch stays
    unborn and everything in it untracked: precisely the silent data loss
    this module is meant to prevent, on the machines least likely to notice.

    Passed per invocation, so nothing is written to the user's config (a
    worktree store shares the host repo's config, where writing an identity
    would be an unwelcome surprise), and a real identity always wins.
    """
    for key in ("user.name", "user.email"):
        if not _run(["config", "--get", key], cwd=repo, check=False).stdout.strip():
            return [
                "-c",
                f"user.name={constants.FALLBACK_GIT_NAME}",
                "-c",
                f"user.email={constants.FALLBACK_GIT_EMAIL}",
            ]
    return []


def commit_paths(repo: Path, message: str, paths: list[str]) -> bool:
    """Stage and commit only `paths`, leaving the rest of the index and work
    tree untouched. Returns False if none of them exist or none had changes.

    A pathspec commit, not `add -A` + `commit`: this runs inside the user's
    own code repo, where sweeping up whatever else they had staged would be
    an unforgivable thing for a memory tool to do.
    """
    repo = Path(repo)
    existing = [p for p in paths if (repo / p).exists()]
    if not existing:
        return False
    _run(["add", "--", *existing], cwd=repo)
    if (
        _run(["diff", "--cached", "--quiet", "--", *existing], cwd=repo, check=False).returncode
        == 0
    ):
        return False  # already committed, nothing to do
    # No fallback identity here, unlike `commit_if_dirty`: this commit lands
    # in the user's own code repo, and authoring it as somebody they never
    # configured is worse than reporting that it didn't happen.
    _run(["commit", "-q", "-m", message, "--", *existing], cwd=repo)
    return True


def _stream_progress(
    args: list[str],
    cwd: Path,
    on_progress: Callable[[str], None] | None,
    interval: float = CLONE_PROGRESS_INTERVAL_SECONDS,
) -> subprocess.CompletedProcess:
    """Run git with no wall-clock cap, reporting that it is still alive.

    Used only by `clone`. Everything else in this module is bounded by
    `DEFAULT_TIMEOUT_SECONDS`, but a clone can be legitimately long, and
    killing an honest transfer at an arbitrary deadline is worse than waiting.
    The cost of dropping the deadline is that silence becomes ambiguous — so
    this reports at a fixed interval instead, either the newest line of git's
    own progress or a bare "still running" if git has gone quiet.

    Git writes progress to stderr as carriage-return-terminated chunks.
    Reading the pipe in text mode translates those to newlines
    (universal newlines), so iterating
    it yields one progress update at a time rather than blocking to end of
    stream. That read happens on a thread so a silent git cannot stop the
    interval from firing.
    """
    proc = subprocess.Popen(
        ["git", *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_noninteractive_env(),
        **_OWN_PROCESS_GROUP,
    )

    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        try:
            for line in proc.stderr:  # type: ignore[union-attr]
                lines.put(line)
        finally:
            lines.put(None)  # EOF

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()

    started = time.monotonic()
    latest = ""
    tail: list[str] = []
    next_report = started + interval
    while True:
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            line = ""
        if line is None:
            break
        if line.strip():
            latest = line.strip()
            tail.append(latest)
            del tail[:-20]  # only the end of it is useful in an error
        now = time.monotonic()
        if on_progress and now >= next_report:
            elapsed = int(now - started)
            on_progress(f"{latest or 'still running'} ({elapsed}s elapsed)")
            next_report = now + interval

    returncode = proc.wait()
    if returncode != 0:
        # git itself is gone, but a transport helper can outlive it and keep
        # writing into the destination we are about to delete.
        _terminate_tree(proc)
    reader.join(timeout=constants.GIT_REAP_TIMEOUT_SECONDS)
    stdout = proc.stdout.read() if proc.stdout else ""
    return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="\n".join(tail))


def clone(
    remote: str,
    dest: Path,
    branch: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Clone `remote` into `dest`, reporting progress while it runs.

    Deliberately has no timeout: see `_stream_progress` and
    `CLONE_STALL_LIMIT_SECONDS` for what bounds it instead.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    preexisting = dest.exists()
    args = [
        # Git aborts itself if the transfer flatlines, which is what makes
        # dropping the wall-clock timeout safe.
        "-c",
        f"http.lowSpeedLimit={CLONE_STALL_LIMIT_BYTES_PER_SECOND}",
        "-c",
        f"http.lowSpeedTime={CLONE_STALL_LIMIT_SECONDS}",
        "clone",
        "--progress",
    ]
    if branch:
        args += ["-b", branch]
    args += [str(remote), str(dest)]

    try:
        result = _stream_progress(args, cwd=dest.parent, on_progress=on_progress)
    except OSError as exc:
        _discard_partial_clone(dest, preexisting)
        raise GitError(_clone_failure_message(remote, dest, str(exc))) from exc
    if result.returncode != 0:
        _discard_partial_clone(dest, preexisting)
        raise GitError(_clone_failure_message(remote, dest, result.stderr.strip()))


def _discard_partial_clone(dest: Path, preexisting: bool) -> None:
    """Remove the half-written directory a failed clone leaves behind.

    Git creates the destination and starts filling it immediately, so a clone
    that dies partway leaves a directory that is neither absent nor usable.
    That is worse than either: a retry hits "destination path already exists
    and is not an empty directory", and callers that probe for the path (as
    `hostconfig` does) mistake the wreckage for a real store. Only clean up
    what this call created — never a directory that was already there.
    """
    if preexisting or not dest.exists():
        return
    shutil.rmtree(dest, ignore_errors=True)


def _clone_failure_message(remote: str, dest: Path, detail: str) -> str:
    """Say what broke *and* what to do about it.

    A failed clone is one of the few errors here with an obvious manual
    recovery, and it is usually a credential problem — which this module
    deliberately refuses to prompt for. Naming the command is the whole
    remedy, so it belongs in the message rather than in documentation the
    reader is not currently looking at.
    """
    lines = [f"could not clone {remote} into {dest}"]
    if detail:
        lines.append(detail)
    lines.append(
        f"clone it yourself to sort out credentials or a slow network, "
        f"then re-run this command: git clone {remote} {dest}"
    )
    return "\n".join(lines)


def branch_exists(repo: Path, branch: str) -> bool:
    ref = f"refs/heads/{branch}"
    result = _run(["show-ref", "--verify", "--quiet", ref], cwd=repo, check=False)
    return result.returncode == 0


def remote_ref_exists(repo: Path, branch: str, remote: str = "origin") -> bool:
    ref = f"refs/remotes/{remote}/{branch}"
    result = _run(["show-ref", "--verify", "--quiet", ref], cwd=repo, check=False)
    return result.returncode == 0


def _refuse_code_branch(host_repo: Path, ref: str, branch: str) -> None:
    """Raise if `ref` shares history with the host's checked-out commit.

    A store branch must be an orphan. One that descends from the code — a
    name collision like `--branch dev`, or a legacy `memories` branch once
    cut from `main` — would put memory commits on top of the project's code
    and push them wherever that code goes. An unborn host HEAD has no
    history to share, so there is nothing to check.
    """
    if not has_commits(host_repo):
        return
    result = _run(["merge-base", ref, "HEAD"], cwd=host_repo, check=False)
    if result.returncode == 0:
        raise GitError(
            f"branch '{branch}' ({ref}) shares history with this repo's checked-out code "
            f"(common commit {result.stdout.strip()[:7]}), so it is not an orphan branch and "
            f"cannot hold a Redthread store. Pick a branch name that doesn't exist yet "
            f"(e.g. --branch memories) and one is created as an orphan."
        )


def ensure_worktree(
    host_repo: Path, worktree_path: Path, branch: str, remote: str = "origin"
) -> bool:
    """Attach a worktree at `worktree_path` checked out to `branch`, without
    ever touching the host repo's currently checked-out branch. Creates
    `branch` as an orphan (no shared history) if it doesn't exist locally or
    on `remote`; otherwise checks out the existing branch, after refusing
    one that shares history with the host's code. Returns True if the
    branch was newly created as an orphan.
    """
    host_repo = Path(host_repo)
    worktree_path = Path(worktree_path)

    if branch_exists(host_repo, branch):
        _refuse_code_branch(host_repo, branch, branch)
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        _run(["worktree", "add", str(worktree_path), branch], cwd=host_repo)
        return False
    if has_remote(host_repo, remote):
        _run(["fetch", "-q", remote, branch], cwd=host_repo, check=False)
    if remote_ref_exists(host_repo, branch, remote):
        _refuse_code_branch(host_repo, f"{remote}/{branch}", branch)
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        _run(
            ["worktree", "add", "-b", branch, str(worktree_path), f"{remote}/{branch}"],
            cwd=host_repo,
        )
        return False
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    _run(["worktree", "add", "--orphan", "-b", branch, str(worktree_path)], cwd=host_repo)
    return True


def remove_worktree(host_repo: Path, worktree_path: Path) -> None:
    _run(["worktree", "remove", str(worktree_path)], cwd=host_repo, check=False)


def configure_identity(repo: Path, name: str, email: str) -> None:
    _run(["config", "user.name", name], cwd=repo)
    _run(["config", "user.email", email], cwd=repo)


def set_remote(repo: Path, url: str, name: str = "origin") -> None:
    existing = _run(["remote"], cwd=repo).stdout.split()
    if name in existing:
        _run(["remote", "set-url", name, str(url)], cwd=repo)
    else:
        _run(["remote", "add", name, str(url)], cwd=repo)


def has_remote(repo: Path, name: str = "origin") -> bool:
    return name in _run(["remote"], cwd=repo).stdout.split()


def is_worktree(repo: Path) -> bool:
    """True when `repo` is a linked worktree of another repository.

    A linked worktree has a `.git` *file* pointing at the host repo's
    gitdir, never a directory. It matters because a worktree shares the host
    repo's remotes: an `origin` here is the project's own origin, not a
    remote anybody chose for memory.
    """
    return (Path(repo) / ".git").is_file()


def has_commits(repo: Path) -> bool:
    """False on an unborn branch — one that exists only as a HEAD pointer
    with no commit behind it, and therefore no ref, no `git log`, and
    nothing that a `git clean` would spare."""
    return _run(["rev-parse", "--verify", "-q", "HEAD"], cwd=repo, check=False).returncode == 0


def get_remote_url(repo: Path, name: str = "origin") -> str | None:
    result = _run(["remote", "get-url", name], cwd=repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def current_branch(repo: Path) -> str:
    # `branch --show-current` resolves correctly even on an unborn HEAD
    # (a freshly created branch with zero commits); `rev-parse --abbrev-ref
    # HEAD` does not, which matters for a brand-new orphan worktree branch.
    return _run(["branch", "--show-current"], cwd=repo).stdout.strip()


def add_all(repo: Path) -> None:
    _run(["add", "-A"], cwd=repo)


def is_dirty(repo: Path) -> bool:
    return bool(_run(["status", "--porcelain"], cwd=repo).stdout.strip())


def commit_if_dirty(repo: Path, message: str) -> bool:
    add_all(repo)
    if not is_dirty(repo):
        return False
    _run([*_identity_args(repo), "commit", "-q", "-m", message], cwd=repo)
    return True


def uncommitted_paths(repo: Path) -> set[str]:
    """Repo-relative POSIX paths whose content is not committed — untracked
    or modified. Used to tell "written" apart from "written and durable"
    when listing memory; an untracked file is one `git clean` from gone.

    `--untracked-files=all` matters: the default collapses an untracked
    directory to `memory/`, which says nothing about which entries are at
    risk.
    """
    result = _run(["status", "--porcelain", "--untracked-files=all"], cwd=repo, check=False)
    if result.returncode != 0:
        return set()
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:  # rename: the destination is what exists now
            path = path.split(" -> ", 1)[1]
        paths.add(path.strip('"'))
    return paths


def commit_report(repo: Path, message: str) -> dict[str, str]:
    """Commit whatever is dirty, touching no network, as a status a caller
    can report instead of an exception.

    The local half of `sync_report`, for callers that deliberately do not
    publish. Committing is about durability and pushing is about
    distribution: declining the second is never a reason to skip the first.
    """
    try:
        changed = commit_if_dirty(Path(repo), message)
    except (GitError, OSError) as e:
        return {"status": "failed", "detail": str(e)}
    return {"status": "committed" if changed else "no_changes"}


def ahead_count(repo: Path, remote: str = "origin") -> int | None:
    """Commits on HEAD that the remote branch doesn't have, or None when
    there is nothing to compare against (no remote, or a branch the remote
    has never seen). Local-only — it compares against the last-fetched ref,
    which is exactly what "not yet published by us" means here."""
    branch = current_branch(repo)
    if not branch or not has_remote(repo, remote):
        return None
    result = _run(["rev-list", "--count", f"{remote}/{branch}..HEAD"], cwd=repo, check=False)
    if result.returncode != 0:
        return None
    return int(result.stdout.strip())


def pull_rebase(
    repo: Path, remote: str = "origin", timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> None:
    branch = current_branch(repo)
    result = _run(
        ["pull", "--rebase", "-q", remote, branch], cwd=repo, check=False, timeout=timeout
    )
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "couldn't find remote ref" in stderr or "unknown revision" in stderr:
            return  # nothing to pull yet — this is the first push
        raise GitError(f"git pull --rebase failed in {repo}:\n{result.stderr.strip()}")


def push(
    repo: Path, remote: str = "origin", timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess:
    branch = current_branch(repo)
    return _run(["push", "-q", "-u", remote, branch], cwd=repo, check=False, timeout=timeout)


LAST_PUSH_FILENAME = "redthread-last-push.json"


def _last_push_path(repo: Path) -> Path | None:
    result = _run(["rev-parse", "--absolute-git-dir"], cwd=repo, check=False)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()) / LAST_PUSH_FILENAME


def record_push_outcome(repo: Path, report: dict[str, object]) -> None:
    """Remember how the last push of this store ended, on this machine.

    Kept in the git dir rather than the store: it describes this clone's
    relationship with the remote, not memory, so it must never be committed.
    Without it a failed push is known only to the process that attempted it,
    and when that was the last write of a session nobody ever hears about it.
    """
    path = _last_push_path(repo)
    if path is None:
        return
    with contextlib.suppress(OSError):
        path.write_text(json.dumps({**report, "at": time.time()}), encoding="utf-8")


def last_push_outcome(repo: Path) -> dict[str, object] | None:
    """The outcome `record_push_outcome` saved, from any earlier process."""
    path = _last_push_path(repo)
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sync_report(
    repo: Path, message: str, remote: str = "origin", budget: float | None = None
) -> dict[str, str]:
    """`sync`, but as a status a caller can hand back to an agent instead of
    an exception. Used where the write itself already succeeded and a failed
    push must be reported, not raised — losing the write to a git error
    (no identity configured, no network, a remote that rejects) would be a
    much worse outcome than an unpushed one.

    `budget` caps the whole sync in seconds (see `sync`). Running out of it
    reports `committed`, not `failed`: the write is durable, the network was
    merely slow, and the next sync publishes it. Every outcome that involved
    a remote is recorded with `record_push_outcome`, so a later process can
    see a failure this one had no chance to report.
    """
    repo = Path(repo)
    try:
        changed = sync(repo, message, remote=remote, budget=budget)
    except PushBudgetExceeded as e:
        report = {
            "status": "committed",
            "detail": f"{e} — the commit is safe on this machine and the next sync publishes it",
        }
        record_push_outcome(repo, report)
        return report
    except (GitError, OSError) as e:
        report = {"status": "failed", "detail": str(e)}
        with contextlib.suppress(GitError, OSError):
            if has_remote(repo, remote):
                record_push_outcome(repo, report)
        return report
    if not has_remote(repo, remote):
        return {
            "status": "committed" if changed else "no_changes",
            "detail": f"no {remote!r} remote on the store repo, so nothing left this "
            "machine — add one with `git -C <store> remote add origin <url>` to make "
            "memory portable",
        }
    # Naming the remote is the only way a caller can see *where* memory went,
    # which matters most when the store never chose that remote itself (a
    # worktree store inherits the host repo's).
    report = {"status": "pushed" if changed else "no_changes"}
    url = get_remote_url(repo, remote)
    if url:
        report["remote"] = url
    record_push_outcome(repo, report)
    return report


def store_status(repo: Path) -> dict[str, object]:
    """Everything needed to answer "is this store's content actually safe?":
    the branch, whether it has any commits at all, what is uncommitted, and
    how far ahead of the remote it is."""
    repo = Path(repo)
    return {
        "path": str(repo.resolve()),
        "branch": current_branch(repo),
        "worktree": is_worktree(repo),
        "has_commits": has_commits(repo),
        "dirty": is_dirty(repo),
        "uncommitted": sorted(uncommitted_paths(repo)),
        "remote": get_remote_url(repo) if has_remote(repo) else None,
        "unpushed_commits": ahead_count(repo),
    }


def sync(
    repo: Path,
    message: str,
    remote: str = "origin",
    max_retries: int = constants.SYNC_MAX_RETRIES,
    budget: float | None = None,
) -> bool:
    """Commit local changes if any, then rebase onto and push to `remote`,
    retrying if another node pushed first. Returns True if anything was
    committed or pushed.

    `budget`, in seconds, bounds the network half as a whole — every pull,
    push, and backoff together — rather than each git call separately; a
    slow remote otherwise costs up to a minute per call across every retry.
    The commit comes first and never counts against it. Running out raises
    `PushBudgetExceeded` with the commit already made. None means no cap
    beyond each call's own timeout.
    """
    repo = Path(repo)
    committed = commit_if_dirty(repo, message)
    if not has_remote(repo, remote):
        return committed

    deadline = None if budget is None else time.monotonic() + budget

    def _timeout() -> float:
        if deadline is None:
            return DEFAULT_TIMEOUT_SECONDS
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PushBudgetExceeded(f"push did not finish within {budget:g}s")
        return min(DEFAULT_TIMEOUT_SECONDS, remaining)

    for attempt in range(max_retries):
        try:
            pull_rebase(repo, remote, timeout=_timeout())
            result = push(repo, remote, timeout=_timeout())
        except GitTimeout as e:
            if deadline is not None and time.monotonic() >= deadline:
                raise PushBudgetExceeded(f"push did not finish within {budget:g}s") from e
            raise
        if result.returncode == 0:
            return True
        stderr = result.stderr.lower()
        if "rejected" not in stderr and "fetch first" not in stderr:
            raise GitError(f"git push failed in {repo}:\n{result.stderr.strip()}")
        backoff = min(
            constants.SYNC_RETRY_BACKOFF_SECONDS * (2**attempt),
            constants.SYNC_RETRY_BACKOFF_CAP_SECONDS,
        )
        if deadline is not None:
            backoff = min(backoff, max(0.0, deadline - time.monotonic()))
        time.sleep(backoff)

    raise GitError(f"git push kept getting rejected after {max_retries} retries in {repo}")
