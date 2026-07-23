"""FastMCP server wrapping a single Redthread store as an agent's memory.

Point a coding agent's MCP config at this instead of its local
`.claude/`/`.agent/` folder: the store is git-backed, so the same memory is
visible on every machine that clones it.
"""

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from redthread.mcp import tools
from redthread.store import LocalStore


def build_server(store_path: Path) -> FastMCP:
    store_path = Path(store_path)
    mcp = FastMCP(
        "redthread",
        instructions=(
            "Git-backed, portable working memory for this project. On a "
            "new project, call agents_md_bootstrap first, before any other "
            "tool here — it's idempotent, so calling it every session is "
            "fine, and it's what makes future sessions use this memory "
            "automatically instead of needing to be told. Runs are "
            "identified by run_id; phases come from this store's own "
            "declared pipeline. Read handoffs, not raw entries, when "
            "picking up another phase's work."
        ),
    )

    def _store() -> LocalStore:
        return LocalStore(store_path)

    @mcp.tool()
    def store_init(project_id: str, phases: list[str], name: str | None = None) -> dict[str, Any]:
        """Create the store this server points at, if it doesn't exist yet."""
        store = LocalStore.init(store_path, project_id=project_id, phases=phases, name=name)
        return store.manifest.model_dump(mode="json")

    @mcp.tool()
    def run_start() -> dict[str, Any]:
        """Start a new run and return its record, including the new run_id."""
        return tools.run_start(_store())

    @mcp.tool()
    def run_list() -> list[str]:
        """List every run_id in this store."""
        return tools.run_list(_store())

    @mcp.tool()
    def context_log(
        run_id: str,
        phase: str,
        type: str,
        payload: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Append an immutable context entry; returns the new entry_id.
        type is one of metric|decision|code_change|artifact_ref|error|milestone|note."""
        return tools.context_log(_store(), run_id, phase, type, payload=payload, tags=tags)

    @mcp.tool()
    def context_read(
        run_id: str, phase: str | None = None, type: str | None = None
    ) -> list[dict[str, Any]]:
        """Read raw context entries for a run, optionally filtered by phase/type."""
        return tools.context_read(_store(), run_id, phase=phase, type=type)

    @mcp.tool()
    def artifact_put(
        run_id: str, phase: str, source_path: str, kind: str, artifact_id: str | None = None
    ) -> dict[str, Any]:
        """Register a small local file as a content-addressed artifact pointer."""
        return tools.artifact_put(_store(), run_id, phase, source_path, kind, artifact_id)

    @mcp.tool()
    def artifact_get(run_id: str, artifact_id: str) -> dict[str, Any]:
        """Resolve an inline artifact to a verified local path."""
        return tools.artifact_get(_store(), run_id, artifact_id)

    @mcp.tool()
    def summary_update(run_id: str, phase: str, markdown: str) -> None:
        """Replace the rolling markdown summary for a phase."""
        tools.summary_update(_store(), run_id, phase, markdown)

    @mcp.tool()
    def summary_get(run_id: str, phase: str) -> str | None:
        """Read a phase's rolling markdown summary."""
        return tools.summary_get(_store(), run_id, phase)

    @mcp.tool()
    def handoff_publish(
        run_id: str,
        phase: str,
        headline: str,
        key_results: dict[str, Any] | None = None,
        best_artifacts: list[str] | None = None,
        decisions: list[str] | None = None,
        open_questions: list[str] | None = None,
        figures: list[str] | None = None,
    ) -> dict[str, Any]:
        """Publish this phase's curated handoff for the next phase to consume."""
        return tools.handoff_publish(
            _store(),
            run_id,
            phase,
            headline,
            key_results=key_results,
            best_artifacts=best_artifacts,
            decisions=decisions,
            open_questions=open_questions,
            figures=figures,
        )

    @mcp.tool()
    def handoff_get(run_id: str, phase: str) -> dict[str, Any]:
        """Read a phase's curated handoff. Prefer this over context_read
        when picking up another phase's work."""
        return tools.handoff_get(_store(), run_id, phase)

    @mcp.tool()
    def memory_write(namespace: str, key: str, content: str) -> None:
        """Write a long-term memory file (not tied to any run), portable
        across every machine that clones this store."""
        tools.memory_write(_store(), namespace, key, content)

    @mcp.tool()
    def memory_read(namespace: str, key: str) -> str | None:
        """Read a long-term memory file."""
        return tools.memory_read(_store(), namespace, key)

    @mcp.tool()
    def memory_list(namespace: str) -> list[str]:
        """List every key written under a memory namespace."""
        return tools.memory_list(_store(), namespace)

    @mcp.tool()
    def agents_md_bootstrap(project_dir: str | None = None) -> dict[str, Any]:
        """Add a short Redthread usage policy to this project's AGENTS.md
        (or CLAUDE.md, if that's the one that already exists) so agents use
        this store as memory automatically in future sessions, without
        being told each time. Idempotent — call this first, before any
        other tool, on every session; it's a no-op once already present.
        project_dir defaults to the server's working directory."""
        target_dir = Path(project_dir) if project_dir else Path.cwd()
        return tools.agents_md_bootstrap(store_path, target_dir)

    return mcp


def main(store_path: Path) -> None:
    build_server(store_path).run(transport="stdio")
