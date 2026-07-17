"""The operations an MCP tool call actually performs, as plain functions
over an already-open LocalStore. Kept separate from server.py so they're
directly unit-testable without going through the MCP protocol.
"""

from pathlib import Path
from typing import Any

from redthread.models import Handoff
from redthread.store import LocalStore


def run_start(store: LocalStore) -> dict[str, Any]:
    return store.start_run().model_dump(mode="json")


def run_list(store: LocalStore) -> list[str]:
    return store.list_runs()


def context_log(
    store: LocalStore,
    run_id: str,
    phase: str,
    type: str,
    payload: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> str:
    return store.log(run_id, phase, type, payload=payload, tags=tags).entry_id


def context_read(
    store: LocalStore, run_id: str, phase: str | None = None, type: str | None = None
) -> list[dict[str, Any]]:
    entries = store.read_entries(run_id, phase=phase, type=type)
    return [e.model_dump(mode="json") for e in entries]


def artifact_put(
    store: LocalStore,
    run_id: str,
    phase: str,
    source_path: str,
    kind: str,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    artifact = store.add_artifact(run_id, phase, Path(source_path), kind, artifact_id=artifact_id)
    return artifact.model_dump(mode="json")


def artifact_get(store: LocalStore, run_id: str, artifact_id: str) -> dict[str, Any]:
    artifact, path = store.resolve_artifact(run_id, artifact_id)
    return {"artifact": artifact.model_dump(mode="json"), "path": str(path)}


def summary_update(store: LocalStore, run_id: str, phase: str, markdown: str) -> None:
    store.set_summary(run_id, phase, markdown)


def summary_get(store: LocalStore, run_id: str, phase: str) -> str | None:
    return store.get_summary(run_id, phase)


def handoff_publish(
    store: LocalStore,
    run_id: str,
    phase: str,
    headline: str,
    key_results: dict[str, Any] | None = None,
    best_artifacts: list[str] | None = None,
    decisions: list[str] | None = None,
    open_questions: list[str] | None = None,
    figures: list[str] | None = None,
) -> dict[str, Any]:
    handoff = Handoff(
        from_phase=phase,
        run_id=run_id,
        headline=headline,
        key_results=key_results or {},
        best_artifacts=best_artifacts or [],
        decisions=decisions or [],
        open_questions=open_questions or [],
        figures=figures or [],
    )
    store.publish_handoff(handoff)
    return handoff.model_dump(mode="json")


def handoff_get(store: LocalStore, run_id: str, phase: str) -> dict[str, Any]:
    return store.get_handoff(run_id, phase).model_dump(mode="json")


def memory_write(store: LocalStore, namespace: str, key: str, content: str) -> None:
    store.memory_write(namespace, key, content)


def memory_read(store: LocalStore, namespace: str, key: str) -> str | None:
    return store.memory_read(namespace, key)


def memory_list(store: LocalStore, namespace: str) -> list[str]:
    return store.memory_list(namespace)
