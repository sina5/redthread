"""Artifact pointer records: content-addressed references, never payloads."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

BACKENDS = frozenset({"s3", "minio", "rsync", "gitlfs", "inline"})


class Artifact(BaseModel):
    schema_version: int = 1
    artifact_id: str
    kind: str  # open-ended: checkpoint, config, plot, log, build, docs, report, ...
    sha256: str
    size_bytes: int
    backend: str
    uri: str
    produced_by_phase: str
    created_ts: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("backend")
    @classmethod
    def _known_backend(cls, v: str) -> str:
        if v not in BACKENDS:
            raise ValueError(f"unknown backend {v!r}; expected one of {sorted(BACKENDS)}")
        return v

    @field_validator("sha256")
    @classmethod
    def _valid_sha256(cls, v: str) -> str:
        if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        return v


class ArtifactIndex(BaseModel):
    """Registry of all artifact pointers for a run (artifacts.index.json)."""

    schema_version: int = 1
    run_id: str
    artifacts: dict[str, Artifact] = Field(default_factory=dict)
