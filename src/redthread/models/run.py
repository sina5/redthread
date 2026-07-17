"""RunRecord (run.yaml): run status, per-phase states, and node lineage."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

RUN_STATUSES = frozenset({"created", "active", "done", "failed"})
PHASE_STATUSES = frozenset({"pending", "active", "done", "failed"})


class NodeStint(BaseModel):
    """One node's tenure on a run. Every node that touches a run is recorded."""

    node_id: str
    host: str | None = None
    joined: datetime
    left: datetime | None = None


class RunRecord(BaseModel):
    schema_version: int = 1
    run_id: str
    status: str = "created"
    parent_run_id: str | None = None  # reserved for sweep/fork lineage (no behavior yet)
    phases: dict[str, str] = Field(default_factory=dict)  # phase name -> phase status
    nodes: list[NodeStint] = Field(default_factory=list)
    created_ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
