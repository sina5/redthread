"""Path builders for the store tree. All store-internal references are
relative POSIX paths; absolute paths never enter the store."""

from pathlib import Path, PurePosixPath


class StoreLayout:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def project_yaml(self) -> Path:
        return self.root / "project.yaml"

    @property
    def gitattributes(self) -> Path:
        return self.root / ".gitattributes"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def run_yaml(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.yaml"

    def artifacts_index(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "artifacts.index.json"

    def phase_dir(self, run_id: str, phase: str) -> Path:
        return self.run_dir(run_id) / "phases" / phase

    def entries_dir(self, run_id: str, phase: str) -> Path:
        return self.phase_dir(run_id, phase) / "entries"

    def artifacts_dir(self, run_id: str, phase: str) -> Path:
        return self.phase_dir(run_id, phase) / "artifacts"

    def summary_md(self, run_id: str, phase: str) -> Path:
        return self.phase_dir(run_id, phase) / "summary.md"

    def handoff_json(self, run_id: str, phase: str) -> Path:
        return self.phase_dir(run_id, phase) / "handoff.json"

    def memory_dir(self, namespace: str) -> Path:
        return self.root / "memory" / self._safe_segment(namespace)

    def memory_file(self, namespace: str, key: str) -> Path:
        return self.memory_dir(namespace) / self._safe_relative(key)

    def relative_uri(self, path: Path) -> str:
        """A store-internal URI: the POSIX-style path relative to the root."""
        return str(PurePosixPath(*path.relative_to(self.root).parts))

    @staticmethod
    def _safe_segment(value: str) -> str:
        if not value or value in (".", "..") or "/" in value or "\\" in value:
            raise ValueError(f"invalid path segment: {value!r}")
        return value

    @staticmethod
    def _safe_relative(value: str) -> Path:
        if not value or "\\" in value:
            raise ValueError(f"invalid relative path: {value!r}")
        posix = PurePosixPath(value)
        if posix.is_absolute() or any(part in ("..", "") for part in posix.parts):
            raise ValueError(f"invalid relative path: {value!r}")
        return Path(*posix.parts)
