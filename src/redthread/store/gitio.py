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


def sync(
    repo: Path, message: str, remote: str = "origin", max_retries: int = 5
) -> bool:
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
