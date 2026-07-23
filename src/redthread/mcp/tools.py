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


_AGENTS_MD_MARKER = "<!-- redthread:agent-instructions -->"


def _agents_md_section(store_path: Path) -> str:
    return (
        f"{_AGENTS_MD_MARKER}\n"
        "## Agent memory (Redthread)\n\n"
        "This project's agent memory lives in a Redthread store (MCP server "
        f'"redthread", `--store {store_path}`), not local files.\n\n'
        "- At session start, call `memory_list` / `memory_read` to load relevant\n"
        "  context before making changes.\n"
        "- After completing a non-trivial task, write a dated summary with\n"
        "  `memory_write` (namespace `sessions`, key like `YYYY-MM-DD_short-slug`):\n"
        "  what changed, why, validation performed, follow-ups.\n"
        "- Store durable conventions and decisions under the `notes` namespace;\n"
        "  never store secrets.\n"
    )


def agents_md_bootstrap(store_path: Path, project_dir: Path) -> dict[str, Any]:
    """Ensure project_dir's AGENTS.md (or CLAUDE.md, if that's the one that
    already exists) tells agents to use this store as memory. Idempotent —
    safe to call every session; a no-op once the instructions are present."""
    project_dir = Path(project_dir)
    agents_md = project_dir / "AGENTS.md"
    claude_md = project_dir / "CLAUDE.md"

    for candidate in (agents_md, claude_md):
        if candidate.exists() and _AGENTS_MD_MARKER in candidate.read_text(
            encoding="utf-8-sig"
        ):
            return {"status": "already_present", "file": str(candidate)}

    if agents_md.exists():
        target = agents_md
    elif claude_md.exists():
        target = claude_md
    else:
        target = agents_md

    section = _agents_md_section(store_path)
    if target.exists():
        existing = target.read_text(encoding="utf-8-sig")
        new_text = existing.rstrip("\n") + "\n\n" + section
        status = "appended"
    else:
        new_text = section
        status = "created"
    target.write_text(new_text, encoding="utf-8", newline="\n")
    return {"status": status, "file": str(target)}
