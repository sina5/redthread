"""RsyncBackend: a content-addressed directory tree.

An rsync target is, at bottom, a directory — local, mounted, or reached over
SSH by the real `rsync` binary. v1 operates against an already-resolved
local/mounted directory (see `redthread.paths`, which maps a logical backend
name to that directory per machine); shelling out to `rsync` for a remote
host is a drop-in extension of `put`/`get` behind this same interface.
"""

import shutil
from pathlib import Path

from redthread.hashing import sha256_file


class RsyncBackend:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, sha256: str) -> Path:
        return self.root / sha256[:2] / sha256

    def exists(self, sha256: str) -> bool:
        return self._path_for(sha256).exists()

    def put(self, source: Path) -> str:
        source = Path(source)
        digest = sha256_file(source)
        dest = self._path_for(digest)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            shutil.copyfile(source, tmp)
            tmp.replace(dest)
        return digest

    def get(self, sha256: str, dest: Path) -> Path:
        src = self._path_for(sha256)
        if not src.exists():
            raise FileNotFoundError(f"blob {sha256} not found in backend at {self.root}")
        if sha256_file(src) != sha256:
            raise ValueError(f"blob {sha256} failed verification in backend at {self.root}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return dest
