"""Background sync: keeps a store's git repo pushed without an explicit call."""

from redthread.sync.daemon import run_daemon

__all__ = ["run_daemon"]
