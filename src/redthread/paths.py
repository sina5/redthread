"""paths.map: per-machine resolution of logical backend names to local dirs.

This is the mechanism that keeps absolute paths out of the store: an
artifact's uri names a logical backend ("objects", "ci-cache"), and each
machine independently resolves that name to wherever it happens to be
mounted locally. The map itself is per-machine config, never committed.
"""

import json
from pathlib import Path

from redthread.blobs.rsync import RsyncBackend
from redthread.config_dir import default_config_dir

_MAP_FILE = "paths.json"


class PathsMap:
    def __init__(self, config_dir: Path | None = None):
        base = config_dir if config_dir is not None else default_config_dir()
        self.path = base / _MAP_FILE

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, name: str) -> Path | None:
        raw = self._load().get(name)
        return Path(raw) if raw else None

    def set(self, name: str, target: Path) -> None:
        data = self._load()
        data[name] = str(Path(target))
        self._save(data)

    def list(self) -> dict[str, str]:
        return self._load()

    def open_backend(self, name: str) -> RsyncBackend:
        target = self.get(name)
        if target is None:
            raise KeyError(
                f"backend {name!r} is not configured on this machine; "
                "run `redthread backend set` first"
            )
        return RsyncBackend(target)
