"""Auto-commit daemon: debounced pull-rebase-commit-push on a poll interval.

v1 debounces on a timer (default 10s) rather than filesystem events — the
architecture doc's target is "every 5-15s or N entries," and a poll loop
meets that without the added complexity/flakiness of FS-event watching
across platforms. Event-driven triggering can be layered on top later
without changing this function's contract.
"""

import time
from pathlib import Path

from redthread import constants
from redthread.store import LocalStore, StoreError, gitio


def run_daemon(
    store_root: Path,
    interval: float = constants.SYNC_DAEMON_INTERVAL_SECONDS,
    message: str = "redthread auto-commit",
    max_iterations: int | None = None,
) -> None:
    store_root = Path(store_root)
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        # The commit always happens; the push is the store's own decision,
        # re-read each cycle so enabling publishing takes effect without a
        # restart. A store that can't be opened still gets committed — a
        # malformed manifest is no reason to let content go untracked.
        if _publishes(store_root):
            gitio.sync(store_root, message)
        else:
            gitio.commit_report(store_root, message)
        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)


def _publishes(store_root: Path) -> bool:
    """Whether this store's own manifest allows pushing (see
    `redthread.store.publish.PublishPolicy`); True if the store can't be
    opened, which leaves the previous behaviour for anything that isn't a
    readable store."""
    try:
        return LocalStore(store_root).publish_policy().allowed
    except (StoreError, OSError):
        return True
