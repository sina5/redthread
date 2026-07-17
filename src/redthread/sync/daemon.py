"""Auto-commit daemon: debounced pull-rebase-commit-push on a poll interval.

v1 debounces on a timer (default 10s) rather than filesystem events — the
architecture doc's target is "every 5-15s or N entries," and a poll loop
meets that without the added complexity/flakiness of FS-event watching
across platforms. Event-driven triggering can be layered on top later
without changing this function's contract.
"""

import time
from pathlib import Path

from redthread.store import gitio


def run_daemon(
    store_root: Path,
    interval: float = 10.0,
    message: str = "redthread auto-commit",
    max_iterations: int | None = None,
) -> None:
    store_root = Path(store_root)
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        gitio.sync(store_root, message)
        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(interval)
