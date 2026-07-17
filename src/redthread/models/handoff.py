"""Handoff: the curated, domain-neutral contract a phase publishes downstream.

A downstream phase depends only on this schema, never on raw entry internals.
"""

from typing import Any

from pydantic import BaseModel, Field


class Handoff(BaseModel):
    schema_version: int = 1
    from_phase: str
    run_id: str
    headline: str
    key_results: dict[str, Any] = Field(default_factory=dict)
    best_artifacts: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
