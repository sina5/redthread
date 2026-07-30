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
