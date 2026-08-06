"""`.redthread.yaml`: a small, git-committed marker in the HOST (code) repo
recording where and how a project's Redthread store attaches — so a fresh
clone of the host repo (or an MCP server launched from it) can find the
store without a human remembering `--worktree-repo`/`--branch`/`--remote`
flags. Written automatically by `LocalStore.init`/`init_worktree` when a
`host_repo` is given; nothing reads or writes it otherwise.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from redthread.store import gitio
from redthread.store.errors import StoreError

MARKER_FILENAME = ".redthread.yaml"


class StoreRef(BaseModel):
    mode: Literal["worktree", "repo"]
    path: str  # relative to the host repo
    branch: str | None = None  # worktree mode
    url: str | None = None  # repo mode, once a remote is known


class HostConfig(BaseModel):
    schema_version: int = 1
    store: StoreRef


def marker_path(host_repo: Path) -> Path:
    return Path(host_repo) / MARKER_FILENAME


def check_binding(host_repo: Path, store_path: Path) -> dict[str, object]:
    """Does the store being served actually belong to the workspace being
    edited? Returns a status plus both resolved paths.

    An MCP server registered once, globally, in a client that reuses that
    one registration for every workspace (Cursor, Windsurf, VS Code) serves
    the SAME store no matter which project the agent has open. Nothing in
    the store's own contents reveals that: the agent calls
    ``context_bootstrap``, sees a real pipeline and a populated memory
    index, and writes project B's session notes into project A's store.
    Comparing the served store against the workspace is the only signal
    that catches it, so it is computed here and surfaced by bootstrap.

    - ``ok`` — the workspace's marker names this store, or the store lives
      inside the workspace (worktree mode's normal shape).
    - ``mismatch`` — the workspace's marker names a DIFFERENT store. The
      server is pointed at the wrong project; writes here are misfiled.
    - ``unverified`` — the workspace has no marker and the store is outside
      it, so nothing connects the two. Legitimate for a deliberately shared
      store, but indistinguishable from a stale global registration.
    """
    workspace = Path(host_repo).resolve()
    store = Path(store_path).resolve()
    config = read_host_config(workspace)

    if config is not None:
        expected = (workspace / config.store.path).resolve()
        if expected == store:
            return {
                "status": "ok",
                "workspace": str(workspace),
                "store": str(store),
                "expected_store": str(expected),
                "detail": f"{MARKER_FILENAME} in {workspace} names this store.",
            }
        return {
            "status": "mismatch",
            "workspace": str(workspace),
            "store": str(store),
            "expected_store": str(expected),
            "detail": (
                f"{MARKER_FILENAME} in {workspace} names the store at {expected}, but this "
                f"server is serving {store}. The MCP server is pointed at another project's "
                f"store — most likely a single global registration reused across workspaces."
            ),
        }

    if store == workspace or workspace in store.parents:
        return {
            "status": "ok",
            "workspace": str(workspace),
            "store": str(store),
            "expected_store": None,
            "detail": f"The store lives inside the workspace at {workspace}.",
        }

    return {
        "status": "unverified",
        "workspace": str(workspace),
        "store": str(store),
        "expected_store": None,
        "detail": (
            f"The workspace at {workspace} has no {MARKER_FILENAME} and the store at {store} "
            f"is outside it, so nothing ties this store to this project. It may be a store "
            f"shared on purpose, or a global MCP registration left pointing at another project."
        ),
    }


def read_host_config(host_repo: Path) -> HostConfig | None:
    path = marker_path(host_repo)
    if not path.exists():
        return None
    return HostConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8-sig")))


def write_host_config(host_repo: Path, config: HostConfig) -> None:
    path = marker_path(host_repo)
    path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )


def ensure_ignored(host_repo: Path, store_path: Path) -> bool:
    """Add the store directory to the host repo's `.gitignore` if it lives
    inside the host repo's working tree. Returns True if a line was added.

    Without this, a worktree-mode store shows up as a mountain of untracked
    files in `git status` for the repo it's meant to sit quietly beside.
    """
    host_repo = Path(host_repo).resolve()
    try:
        rel = Path(store_path).resolve().relative_to(host_repo)
    except ValueError:
        return False  # store lives outside the host repo; nothing to ignore
    entry = rel.as_posix().rstrip("/") + "/"
    gitignore = host_repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8-sig") if gitignore.exists() else ""
    if entry in {line.strip() for line in existing.splitlines()}:
        return False
    prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
    gitignore.write_text(prefix + entry + "\n", encoding="utf-8", newline="\n")
    return True


def publish_marker(host_repo: Path, store_path: Path) -> dict[str, object]:
    """Ignore the store directory and commit `.redthread.yaml` (plus that
    `.gitignore` change) to the host repo's current branch — and nothing
    else, so the user's own staged work is never swept into it.

    This is what makes the marker do its job: a marker that only exists in
    someone's working tree can't tell the *next* clone where the store is.
    Committing is best-effort — the store already exists by this point, so a
    repo with no configured git identity should produce a warning to act on,
    not a failed init.
    """
    host_repo = Path(host_repo)
    ignored = ensure_ignored(host_repo, store_path)
    paths = [MARKER_FILENAME] + ([".gitignore"] if ignored else [])
    try:
        committed = gitio.commit_paths(host_repo, "Set up Redthread memory store", paths)
    except (gitio.GitError, OSError) as e:
        return {"ignored": ignored, "committed": False, "detail": str(e)}
    return {"ignored": ignored, "committed": committed, "detail": None}


def attach(host_repo: Path, store_path: Path, *, allow_clone: bool = False) -> HostConfig:
    """Make `store_path` exist, per the marker in `host_repo`. Worktree mode
    always attaches freely (it's just the repo you already cloned). Repo
    mode requires `allow_clone=True` to clone a missing store, since that
    means running `git clone` against a URL read from a committed file — a
    real trust boundary, not a default to cross silently.

    If the store already exists in repo mode, this instead syncs the
    marker's `url` from the store's actual `origin` remote — so running
    `redthread attach` again after `git remote add origin ...` is how a
    repo-mode marker created before a remote existed gets its url filled
    in, with no separate "update" command needed.
    """
    host_repo = Path(host_repo)
    store_path = Path(store_path)
    config = read_host_config(host_repo)
    if config is None:
        raise StoreError(f"no {MARKER_FILENAME} found in {host_repo}")

    ref = config.store
    if ref.mode == "worktree":
        if not ref.branch:
            raise StoreError(f"{MARKER_FILENAME} has mode 'worktree' but no branch recorded")
        gitio.ensure_worktree(host_repo, store_path, ref.branch)
        return config

    if not store_path.exists():
        if not ref.url:
            raise StoreError(
                f"{MARKER_FILENAME} has mode 'repo' but no url recorded; "
                "clone the store manually first"
            )
        if not allow_clone:
            raise StoreError(
                f"{MARKER_FILENAME} points at a store repo ({ref.url}) that isn't "
                f"cloned locally yet; pass --allow-clone to clone it automatically, "
                f"or clone it yourself first: git clone {ref.url} {store_path}"
            )
        gitio.clone(ref.url, store_path)
        return config

    current_url = gitio.get_remote_url(store_path) if gitio.has_remote(store_path) else None
    if current_url and current_url != ref.url:
        config = HostConfig(store=StoreRef(mode="repo", path=ref.path, url=current_url))
        write_host_config(host_repo, config)
    return config
