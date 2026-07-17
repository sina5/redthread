"""PhaseAdapter: the generic phase lifecycle every domain adapter builds on.

Everything here is domain-neutral: it knows about phases, entries,
artifacts, summaries, and handoffs — never about epochs or build warnings.
Metrics are buffered and flushed as one batched entry (never one entry per
call) to keep git churn down, per the architecture doc's open question on
entry volume. A synchronous flush on `publish_handoff` and on `__exit__`
means curated output never depends on a background daemon being alive.
"""

import contextlib
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from redthread.blobs.base import BlobBackend
from redthread.models import Artifact, ContextEntry, Handoff
from redthread.store import LocalStore, StoreError


def _git_head_sha(code_dir: Path) -> str | None:
    with contextlib.suppress(OSError, subprocess.CalledProcessError):
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=code_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    return None


class PhaseAdapter:
    def __init__(
        self,
        store: LocalStore,
        run_id: str,
        phase: str,
        code_dir: Path | None = None,
        agent: str | None = None,
        metric_batch_size: int = 50,
        metric_batch_interval: float = 60.0,
    ):
        self.store = store
        self.run_id = run_id
        self.phase = phase
        self.agent = agent
        self.project_git_sha = _git_head_sha(code_dir) if code_dir else None
        self.metric_batch_size = metric_batch_size
        self.metric_batch_interval = metric_batch_interval
        self._metric_buffer: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()

    # ---- lifecycle ---------------------------------------------------

    def __enter__(self) -> "PhaseAdapter":
        if self.phase not in self.store.manifest.phases:
            raise StoreError(
                f"phase {self.phase!r} is not in this project's pipeline "
                f"{self.store.manifest.phases}"
            )
        record = self.store.get_run(self.run_id)
        if record.phases.get(self.phase) == "pending":
            record.phases[self.phase] = "active"
            self.store.save_run(record)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.flush_metrics()
        if exc is not None:
            self.log_error(str(exc), exception_type=exc_type.__name__ if exc_type else None)
            record = self.store.get_run(self.run_id)
            record.phases[self.phase] = "failed"
            self.store.save_run(record)

    # ---- structured logging -------------------------------------------

    def _log(
        self, type: str, payload: dict[str, Any], tags: list[str] | None = None
    ) -> ContextEntry:
        return self.store.log(
            self.run_id,
            self.phase,
            type,
            payload=payload,
            tags=tags,
            agent=self.agent,
            project_git_sha=self.project_git_sha,
        )

    def log_metric(self, tags: list[str] | None = None, **fields: Any) -> None:
        """Buffer one metric sample; flushes automatically on batch size or
        elapsed time so high-frequency logging doesn't churn the store."""
        self._metric_buffer.append({**fields, "_ts": datetime.now(UTC).isoformat()})
        due = time.monotonic() - self._last_flush >= self.metric_batch_interval
        if len(self._metric_buffer) >= self.metric_batch_size or due:
            self.flush_metrics(tags=tags)

    def flush_metrics(self, tags: list[str] | None = None) -> None:
        if not self._metric_buffer:
            return
        self._log("metric", {"samples": self._metric_buffer}, tags=tags)
        self._metric_buffer = []
        self._last_flush = time.monotonic()

    def log_decision(self, note: str, **extra: Any) -> ContextEntry:
        return self._log("decision", {"note": note, **extra})

    def log_error(self, message: str, **extra: Any) -> ContextEntry:
        return self._log("error", {"message": message, **extra})

    def log_milestone(self, event: str, **extra: Any) -> ContextEntry:
        return self._log("milestone", {"event": event, **extra})

    def log_note(self, **fields: Any) -> ContextEntry:
        return self._log("note", fields)

    # ---- artifacts -------------------------------------------------------

    def add_artifact(self, source: Path, kind: str, artifact_id: str | None = None) -> Artifact:
        return self.store.add_artifact(
            self.run_id, self.phase, source, kind, artifact_id=artifact_id
        )

    def add_blob_artifact(
        self,
        source: Path,
        kind: str,
        backend_name: str,
        backend: BlobBackend,
        artifact_id: str | None = None,
    ) -> Artifact:
        return self.store.add_blob_artifact(
            self.run_id, self.phase, source, kind, backend_name, backend, artifact_id=artifact_id
        )

    # ---- summary & handoff -------------------------------------------------

    def set_summary(self, markdown: str) -> None:
        self.store.set_summary(self.run_id, self.phase, markdown)

    def upstream(self, from_phase: str) -> Handoff:
        """Read another phase's curated handoff — never its raw entries."""
        return self.store.get_handoff(self.run_id, from_phase)

    def publish_handoff(
        self,
        headline: str,
        key_results: dict[str, Any] | None = None,
        best_artifacts: list[str] | None = None,
        decisions: list[str] | None = None,
        open_questions: list[str] | None = None,
        figures: list[str] | None = None,
    ) -> Handoff:
        self.flush_metrics()
        handoff = Handoff(
            from_phase=self.phase,
            run_id=self.run_id,
            headline=headline,
            key_results=key_results or {},
            best_artifacts=best_artifacts or [],
            decisions=decisions or [],
            open_questions=open_questions or [],
            figures=figures or [],
        )
        self.store.publish_handoff(handoff)
        record = self.store.get_run(self.run_id)
        record.phases[self.phase] = "done"
        self.store.save_run(record)
        return handoff
