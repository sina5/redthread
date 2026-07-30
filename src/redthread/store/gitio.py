"""Git subprocess wrapper: clone/pull-rebase/commit/push with retry.

This is the sync transport described in the architecture: the git remote is
the hub, nodes are interchangeable clients. `sync()` is the one function
adapters and the daemon actually call — it commits local changes, rebases
onto whatever the remote has, and pushes, retrying the rebase+push if
another node pushed in the meantime.
"""

import subprocess
import time
from pathlib import Path

from redthread.store.errors import StoreError


class GitError(StoreError):
    pass


def _run(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )
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
    _run(["commit", "-q", "-m", message, "--", *existing], cwd=repo)
    return True


def clone(remote: str, dest: Path, branch: str | None = None) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "-q", str(remote), str(dest)]
    if branch:
        args = ["clone", "-q", "-b", branch, str(remote), str(dest)]
    _run(args, cwd=dest.parent)


def branch_exists(repo: Path, branch: str) -> bool:
    ref = f"refs/heads/{branch}"
    result = _run(["show-ref", "--verify", "--quiet", ref], cwd=repo, check=False)
    return result.returncode == 0


def remote_ref_exists(repo: Path, branch: str, remote: str = "origin") -> bool:
    ref = f"refs/remotes/{remote}/{branch}"
    result = _run(["show-ref", "--verify", "--quiet", ref], cwd=repo, check=False)
    return result.returncode == 0


def ensure_worktree(
    host_repo: Path, worktree_path: Path, branch: str, remote: str = "origin"
) -> bool:
    """Attach a worktree at `worktree_path` checked out to `branch`, without
    ever touching the host repo's currently checked-out branch. Creates
    `branch` as an orphan (no shared history) if it doesn't exist locally or
    on `remote`; otherwise checks out the existing branch. Returns True if
    the branch was newly created as an orphan.
    """
    host_repo = Path(host_repo)
    worktree_path = Path(worktree_path)
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    if branch_exists(host_repo, branch):
        _run(["worktree", "add", str(worktree_path), branch], cwd=host_repo)
        return False
    if has_remote(host_repo, remote):
        _run(["fetch", "-q", remote, branch], cwd=host_repo, check=False)
    if remote_ref_exists(host_repo, branch, remote):
        _run(
            ["worktree", "add", "-b", branch, str(worktree_path), f"{remote}/{branch}"],
            cwd=host_repo,
        )
        return False
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
    _run(["commit", "-q", "-m", message], cwd=repo)
    return True


def pull_rebase(repo: Path, remote: str = "origin") -> None:
    branch = current_branch(repo)
    result = _run(["pull", "--rebase", "-q", remote, branch], cwd=repo, check=False)
    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "couldn't find remote ref" in stderr or "unknown revision" in stderr:
            return  # nothing to pull yet — this is the first push
        raise GitError(f"git pull --rebase failed in {repo}:\n{result.stderr.strip()}")


def push(repo: Path, remote: str = "origin") -> subprocess.CompletedProcess:
    branch = current_branch(repo)
    return _run(["push", "-q", "-u", remote, branch], cwd=repo, check=False)


def sync_report(repo: Path, message: str, remote: str = "origin") -> dict[str, str]:
    """`sync`, but as a status a caller can hand back to an agent instead of
    an exception. Used where the write itself already succeeded and a failed
    push must be reported, not raised — losing the write to a git error
    (no identity configured, no network, a remote that rejects) would be a
    much worse outcome than an unpushed one.
    """
    repo = Path(repo)
    try:
        changed = sync(repo, message, remote=remote)
    except (GitError, OSError) as e:
        return {"status": "failed", "detail": str(e)}
    if not has_remote(repo, remote):
        return {
            "status": "committed" if changed else "no_changes",
            "detail": f"no {remote!r} remote on the store repo, so nothing left this "
            "machine — add one with `git -C <store> remote add origin <url>` to make "
            "memory portable",
        }
    return {"status": "pushed" if changed else "no_changes"}


def sync(repo: Path, message: str, remote: str = "origin", max_retries: int = 5) -> bool:
    """Commit local changes if any, then rebase onto and push to `remote`,
    retrying if another node pushed first. Returns True if anything was
    committed or pushed."""
    repo = Path(repo)
    committed = commit_if_dirty(repo, message)
    if not has_remote(repo, remote):
        return committed

    for attempt in range(max_retries):
        pull_rebase(repo, remote)
        result = push(repo, remote)
        if result.returncode == 0:
            return True
        stderr = result.stderr.lower()
        if "rejected" not in stderr and "fetch first" not in stderr:
            raise GitError(f"git push failed in {repo}:\n{result.stderr.strip()}")
        time.sleep(min(0.5 * (2**attempt), 5))

    raise GitError(f"git push kept getting rejected after {max_retries} retries in {repo}")
