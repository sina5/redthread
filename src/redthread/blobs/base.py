"""BlobBackend: the interface every large-artifact storage target implements.

Content-addressed and write-once: `put` is idempotent by sha256, so
concurrent uploads of the same content never race.
"""

from pathlib import Path
from typing import Protocol


class BlobBackend(Protocol):
    def put(self, source: Path) -> str:
        """Upload `source`, return its sha256. Idempotent if already present."""
        ...

    def get(self, sha256: str, dest: Path) -> Path:
        """Fetch the blob addressed by `sha256` to `dest`. Verifies content."""
        ...

    def exists(self, sha256: str) -> bool: ...
