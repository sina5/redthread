"""Background push: get the network out of the caller's latency path.

A memory write is durable the moment it is committed locally; the push adds
portability, nothing else. Callers that block on the push (an MCP tool call,
with an agent and a human waiting behind it) pay two network round trips —
pull --rebase, then push — for something that has no bearing on whether
their write succeeded. This module runs that network half on a worker
thread: `schedule()` returns immediately with status `pushing`, and the
outcome lands in `last_report()`, where the next call on the same store
picks it up. A failed push is therefore still surfaced — one call later
instead of never — and the entry itself was already safe on disk.

If the process exits mid-push, the commit survives locally and the next
sync from any path (another `schedule`, the auto-commit daemon, a manual
`redthread sync`) publishes it; an `atexit` drain gives an in-flight push a
bounded window to finish first.
"""

import atexit
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from redthread import constants
from redthread.store import gitio


@dataclass
class _RepoState:
    """Per-store worker bookkeeping. Guarded by `lock`."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    running: bool = False
    rerun: bool = False
    message: str = ""
    last: dict[str, Any] | None = None
    thread: threading.Thread | None = None


class BackgroundSyncer:
    """At most one in-flight push per store, coalescing bursts of writes.

    `schedule()` expects the caller to have already committed (the
    underlying `gitio.sync` re-commits anything it finds anyway, so a
    miss costs nothing). If a commit lands while a push is in flight, the
    `rerun` flag sends the same worker around again, so nothing committed
    after a push started is left behind.
    """

    def __init__(self) -> None:
        self._states: dict[Path, _RepoState] = {}
        self._states_lock = threading.Lock()

    def schedule(self, root: Path, message: str) -> dict[str, Any]:
        """Start (or coalesce into) a background push of `root`.

        Returns `{"status": "pushing"}` immediately; if the previous
        background push of this store failed, its report is attached under
        `previous` so the failure reaches the caller instead of dying with
        this process.
        """
        state = self._state(root)
        with state.lock:
            previous = state.last
            state.message = message
            if state.running:
                state.rerun = True
            else:
                state.running = True
                state.thread = threading.Thread(
                    target=self._work,
                    args=(Path(root), state),
                    name=f"redthread-sync:{Path(root).name}",
                    daemon=True,
                )
                state.thread.start()
        result: dict[str, Any] = {"status": "pushing"}
        if previous is not None and previous.get("status") == "failed":
            result["previous"] = previous
        return result

    def last_report(self, root: Path) -> dict[str, Any] | None:
        """Outcome of the most recently completed push of `root`, if any."""
        state = self._state(root)
        with state.lock:
            return dict(state.last) if state.last is not None else None

    def in_flight(self, root: Path) -> bool:
        state = self._state(root)
        with state.lock:
            return state.running

    def wait(self, root: Path, timeout: float | None = None) -> dict[str, Any] | None:
        """Block until the current push of `root` (if any) finishes; returns
        the last report. For callers that need a confirmed publish — tests,
        session teardown — not for the ordinary write path."""
        state = self._state(root)
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            with state.lock:
                thread = state.thread if state.running else None
            if thread is None:
                return self.last_report(root)
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            thread.join(timeout=remaining)
            if thread.is_alive():  # timed out
                return self.last_report(root)

    def drain(self, timeout: float = constants.BACKGROUND_SYNC_DRAIN_SECONDS) -> None:
        """Give every in-flight push a bounded window to finish. Registered
        via `atexit`: worker threads are daemons, so without this a process
        that exits right after a write would routinely strand its push (the
        commit still survives locally and syncs later)."""
        deadline = time.monotonic() + timeout
        with self._states_lock:
            states = list(self._states.values())
        for state in states:
            with state.lock:
                thread = state.thread if state.running else None
            if thread is not None:
                thread.join(timeout=max(0.0, deadline - time.monotonic()))

    def _state(self, root: Path) -> _RepoState:
        key = Path(root).resolve()
        with self._states_lock:
            if key not in self._states:
                self._states[key] = _RepoState()
            return self._states[key]

    def _work(self, root: Path, state: _RepoState) -> None:
        while True:
            with state.lock:
                state.rerun = False
                message = state.message
            report = gitio.sync_report(root, message)
            with state.lock:
                state.last = {**report, "at": time.time()}
                if not state.rerun:
                    state.running = False
                    state.thread = None
                    return


_SYNCER = BackgroundSyncer()
atexit.register(_SYNCER.drain)


def shared_syncer() -> BackgroundSyncer:
    """The process-wide syncer the MCP tools use. One instance, so the
    one-in-flight-push-per-store invariant holds across every tool call."""
    return _SYNCER
