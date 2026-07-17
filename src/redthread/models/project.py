"""ProjectManifest (project.yaml): project identity and its phase pipeline."""

from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class ProjectManifest(BaseModel):
    schema_version: int = 1
    project_id: str  # slug
    name: str | None = None
    phases: list[str]  # ordered pipeline, e.g. [train, eval, present] or [build, test, present]
    created_ts: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("phases")
    @classmethod
    def _nonempty_unique(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("a project must declare at least one phase")
        if len(set(v)) != len(v):
            raise ValueError("phase names must be unique")
        return v
