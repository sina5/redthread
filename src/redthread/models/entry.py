"""ContextEntry: the atomic, append-only unit of memory."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Domain-neutral event vocabulary. "metric" means any measured result:
# val_acc for an ML run, coverage or bundle size for an app build.
ENTRY_TYPES = frozenset(
    {"metric", "decision", "code_change", "artifact_ref", "error", "milestone", "note"}
)


class Provenance(BaseModel):
    """Where an entry came from. Metadata only — never used for addressing."""

    node_id: str
    host: str | None = None
    agent: str | None = None
    project_git_sha: str | None = None


class ContextEntry(BaseModel):
    schema_version: int = 1
    entry_id: str
    run_id: str
    phase: str
    type: str
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provenance: Provenance
    payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if v not in ENTRY_TYPES:
            raise ValueError(f"unknown entry type {v!r}; expected one of {sorted(ENTRY_TYPES)}")
        return v
