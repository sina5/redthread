"""redthread resume: pick up a run on a new node after the previous one died.

Swapping the machine running a phase is `clone + resume`: nothing is
stranded because nothing was ever owned by a node. This function only
touches node lineage and git; fetching whichever artifact a domain adapter
considers "resumable" (a checkpoint, a build output) is a separate call to
`LocalStore.resolve_artifact` — that choice is domain-specific, so it stays
out of the domain-neutral core.
"""

import socket
from datetime import UTC, datetime
from pathlib import Path

from redthread.ids import get_node_id
from redthread.models import NodeStint, RunRecord
from redthread.store import LocalStore, StoreError, gitio


def resume(
    store_root: Path, run_id: str, remote: str | None = None, host: str | None = None
) -> RunRecord:
    store_root = Path(store_root)
    if not (store_root / "project.yaml").exists():
        if not remote:
            raise StoreError(f"no store at {store_root} and no --remote given to clone from")
        gitio.clone(remote, store_root)
    else:
        if remote and not gitio.has_remote(store_root):
            gitio.set_remote(store_root, remote)
        if gitio.has_remote(store_root):
            gitio.pull_rebase(store_root)

    return _record_resume(LocalStore(store_root), run_id, host)


def resume_worktree(
    host_repo: Path, worktree_path: Path, branch: str, run_id: str, host: str | None = None
) -> RunRecord:
    """Same as `resume`, for a store that lives as an orphan-branch worktree
    of `host_repo` instead of its own repo. No `remote` argument is needed:
    the store's remote is whatever `host_repo`'s own "origin" already is,
    since the orphan branch lives in that same repo.
    """
    host_repo = Path(host_repo)
    worktree_path = Path(worktree_path)
    if not (worktree_path / "project.yaml").exists():
        gitio.ensure_worktree(host_repo, worktree_path, branch)
    elif gitio.has_remote(worktree_path):
        gitio.pull_rebase(worktree_path)

    return _record_resume(LocalStore(worktree_path), run_id, host)


def _record_resume(store: LocalStore, run_id: str, host: str | None) -> RunRecord:
    record = store.get_run(run_id)

    now = datetime.now(UTC)
    for stint in record.nodes:
        if stint.left is None:
            stint.left = now
    record.nodes.append(
        NodeStint(node_id=get_node_id(), host=host or socket.gethostname(), joined=now)
    )
    store.save_run(record)

    active_phase = next((p for p, status in record.phases.items() if status == "active"), None)
    phase = active_phase or next(iter(record.phases), None)
    if phase:
        store.log(
            run_id,
            phase,
            "milestone",
            payload={"event": "resumed", "node_id": get_node_id()},
        )
    return record
