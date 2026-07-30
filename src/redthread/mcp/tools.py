"""The operations an MCP tool call actually performs, as plain functions
over an already-open LocalStore. Kept separate from server.py so they're
directly unit-testable without going through the MCP protocol.

Run-scoped operations take ``run_id`` last and optional: omitted, it
resolves to the store's newest active run (see ``resolve_run_id``), and the
id it resolved to comes back in the response so the caller is never guessing
which run it just wrote to.
"""

from pathlib import Path
from typing import Any

from redthread.models import Handoff
from redthread.store import LocalStore, StoreError


def resolve_run_id(store: LocalStore, run_id: str | None) -> str:
    """The run a call applies to: the one given, else the newest active run."""
    if run_id:
        return run_id
    current = store.current_run_id()
    if current is None:
        raise StoreError(
            "no active run in this store — call run_start to begin one, "
            "or pass run_id explicitly (run_list shows every run)"
        )
    return current


def context_bootstrap(
    store: LocalStore, run_id: str | None = None, recent_runs: int = 5, memory_limit: int = 100
) -> dict[str, Any]:
    """Everything an agent needs to orient itself in this project, in one call.

    Exists because the alternative is a cold agent chaining run_list ->
    memory_list (per namespace it doesn't know about yet) -> handoff_get and
    usually giving up before it gets there. One front door is what makes
    memory actually get read.
    """
    manifest = store.manifest
    runs = store.list_runs()
    resolved = run_id or store.current_run_id()

    recent: list[dict[str, Any]] = []
    for rid in reversed(runs[-recent_runs:]):
        try:
            record = store.get_run(rid)
        except StoreError:
            continue
        recent.append(
            {
                "run_id": rid,
                "status": record.status,
                "phases": record.phases,
                "created_ts": record.created_ts.isoformat(),
            }
        )

    handoffs: list[dict[str, Any]] = []
    summaries: list[str] = []
    if resolved:
        for phase in manifest.phases:
            try:
                handoff = store.get_handoff(resolved, phase)
            except StoreError:
                pass
            else:
                handoffs.append({"phase": phase, "headline": handoff.headline})
            if store.get_summary(resolved, phase) is not None:
                summaries.append(phase)

    memory = store.memory_index()
    return {
        "project": {
            "project_id": manifest.project_id,
            "name": manifest.name,
            "phases": manifest.phases,
        },
        "current_run": resolved,
        "runs": {"total": len(runs), "recent": recent},
        "handoffs": handoffs,
        "summaries": summaries,
        "memory": {
            "namespaces": store.memory_namespaces(),
            "total": len(memory),
            "entries": memory[:memory_limit],
        },
        "_next": _bootstrap_next(resolved, memory),
    }


def _bootstrap_next(run_id: str | None, memory: list[dict[str, Any]]) -> str:
    steps = []
    if memory:
        steps.append(
            "memory_read the entries above that look relevant before changing anything "
            "(memory_search if you're after something specific)"
        )
    else:
        steps.append(
            "this store has no long-term memory yet — write conventions and decisions "
            "as you learn them with memory_write (namespace `notes`, always with a description)"
        )
    if run_id is None:
        steps.append("call run_start if this session's work belongs to a tracked run")
    else:
        steps.append(f"run {run_id} is active, so run_id can be omitted from later calls")
    steps.append(
        "before finishing, record what you did with memory_write "
        "(namespace `sessions`, key `YYYY-MM-DD_short-slug`)"
    )
    return "; ".join(steps) + "."


def run_start(store: LocalStore) -> dict[str, Any]:
    record = store.start_run()
    return {
        **record.model_dump(mode="json"),
        "_next": "This is now the store's active run, so run_id can be omitted from "
        "later calls. Log decisions and milestones with context_log as you go, and "
        "publish a handoff with handoff_publish when a phase finishes.",
    }


def run_list(store: LocalStore) -> list[str]:
    return store.list_runs()


def context_log(
    store: LocalStore,
    phase: str,
    type: str,
    payload: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
    entry = store.log(run_id, phase, type, payload=payload, tags=tags)
    return {"entry_id": entry.entry_id, "run_id": run_id, "phase": phase, "type": type}


def context_read(
    store: LocalStore,
    phase: str | None = None,
    type: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
    entries = store.read_entries(run_id, phase=phase, type=type)
    return {
        "run_id": run_id,
        "count": len(entries),
        "entries": [e.model_dump(mode="json") for e in entries],
    }


def artifact_put(
    store: LocalStore,
    phase: str,
    source_path: str,
    kind: str,
    artifact_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
    artifact = store.add_artifact(run_id, phase, Path(source_path), kind, artifact_id=artifact_id)
    return {**artifact.model_dump(mode="json"), "run_id": run_id}


def artifact_get(store: LocalStore, artifact_id: str, run_id: str | None = None) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
    artifact, path = store.resolve_artifact(run_id, artifact_id)
    return {"artifact": artifact.model_dump(mode="json"), "path": str(path), "run_id": run_id}


def summary_update(
    store: LocalStore, phase: str, markdown: str, run_id: str | None = None
) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
    store.set_summary(run_id, phase, markdown)
    return {"run_id": run_id, "phase": phase, "bytes": len(markdown.encode("utf-8"))}


def summary_get(store: LocalStore, phase: str, run_id: str | None = None) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
    return {"run_id": run_id, "phase": phase, "markdown": store.get_summary(run_id, phase)}


def handoff_publish(
    store: LocalStore,
    phase: str,
    headline: str,
    key_results: dict[str, Any] | None = None,
    best_artifacts: list[str] | None = None,
    decisions: list[str] | None = None,
    open_questions: list[str] | None = None,
    figures: list[str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
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


def handoff_get(store: LocalStore, phase: str, run_id: str | None = None) -> dict[str, Any]:
    run_id = resolve_run_id(store, run_id)
    return store.get_handoff(run_id, phase).model_dump(mode="json")


def memory_write(
    store: LocalStore,
    namespace: str,
    key: str,
    content: str,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    store.memory_write(namespace, key, content, description=description, tags=tags)
    return {
        "namespace": namespace,
        "key": key,
        "description": description,
        "_next": "Memory is written but not yet pushed; `redthread sync` publishes it "
        "to other machines (the auto-commit daemon does this for you if it's running).",
    }


def memory_read(store: LocalStore, namespace: str, key: str) -> str | None:
    return store.memory_read(namespace, key)


def memory_list(store: LocalStore, namespace: str | None = None) -> list[dict[str, Any]]:
    return store.memory_index(namespace)


def memory_search(
    store: LocalStore, query: str, namespace: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    return store.memory_search(query, namespace=namespace, limit=limit)


_AGENTS_MD_MARKER = "<!-- redthread:agent-instructions -->"


def _agents_md_section(store_path: Path) -> str:
    return (
        f"{_AGENTS_MD_MARKER}\n"
        "## Agent memory (Redthread)\n\n"
        "This project's agent memory lives in a Redthread store (MCP server "
        f'"redthread", `--store {store_path}`), not local files.\n\n'
        "- At session start, call `context_bootstrap` once — it returns this\n"
        "  project's pipeline, recent runs, and the memory index in one call.\n"
        "- Read what looks relevant with `memory_read` before making changes.\n"
        "- After completing a non-trivial task, write a dated summary with\n"
        "  `memory_write` (namespace `sessions`, key like `YYYY-MM-DD_short-slug`,\n"
        "  always with a one-line `description`): what changed, why, validation\n"
        "  performed, follow-ups.\n"
        "- Store durable conventions and decisions under the `notes` namespace;\n"
        "  never store secrets.\n"
        "- Subagents do not inherit this file. When you delegate work that should\n"
        "  be remembered, tell the subagent to call `context_bootstrap` too.\n"
    )


def agents_md_bootstrap(store_path: Path, project_dir: Path) -> dict[str, Any]:
    """Ensure project_dir's AGENTS.md (or CLAUDE.md, if that's the one that
    already exists) tells agents to use this store as memory. Idempotent —
    safe to call every session; a no-op once the instructions are present."""
    project_dir = Path(project_dir)
    agents_md = project_dir / "AGENTS.md"
    claude_md = project_dir / "CLAUDE.md"

    for candidate in (agents_md, claude_md):
        if candidate.exists() and _AGENTS_MD_MARKER in candidate.read_text(encoding="utf-8-sig"):
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
