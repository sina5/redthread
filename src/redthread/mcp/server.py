"""FastMCP server wrapping a single Redthread store as an agent's memory.

Point a coding agent's MCP config at this instead of its local
`.claude/`/`.agent/` folder: the store is git-backed, so the same memory is
visible on every machine that clones it.
"""

import json
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from redthread import __version__, constants, update_check
from redthread.mcp import tools
from redthread.mcp.routing import ClientRootsProbe, StoreRouter
from redthread.store import LocalStore, StoreError


def build_server(
    store_path: Path | None = None, host_repo: Path | None = None, allow_clone: bool = False
) -> FastMCP:
    """Build the server over one pinned store, or - with no ``store_path`` -
    over whichever store the calling workspace declares.

    Discovery mode exists for clients that keep a single global MCP
    registration and reuse it for every project window; see
    :mod:`redthread.mcp.routing`.
    """
    store_path = Path(store_path) if store_path else None
    host_repo = Path(host_repo) if host_repo else Path.cwd()
    router = StoreRouter(
        fixed_store=store_path, default_workspace=host_repo, allow_clone=allow_clone
    )
    roots_probe = ClientRootsProbe()
    mcp = FastMCP(
        "redthread",
        instructions=(
            "Git-backed, portable working memory for this project. Call "
            "context_bootstrap first, every session, before any other tool "
            "here — it returns this project's pipeline, recent runs, and the "
            "memory index in one call, and tells you what to do next. "
            "Pass the absolute path of the project directory you are "
            "working in as `workspace` on that first call: a client that "
            "registers this server globally reuses one registration for "
            "every project, and `workspace` is what picks that project's "
            "own store. It sticks for the rest of the session. Then check "
            "the `store.binding` field context_bootstrap returns. If it is "
            "not `ok`, a `warning` field explains why: stop, report it to "
            "the user, and do not write memory, entries, or handoffs, "
            "because they would be filed under another project and be "
            "invisible to this one. On a "
            "new project also call agents_md_bootstrap; it's idempotent, so "
            "calling it every session is fine, and it's what makes future "
            "sessions use this memory without being told. Run-scoped tools "
            "take run_id last and optional — omitted, it means this store's "
            "newest active run. Phases come from this store's own declared "
            "pipeline. Read handoffs, not raw entries, when picking up "
            "another phase's work. Write memory before you finish, not after "
            "you're asked — memory_write commits your entry and pushes it "
            "in the background, so no separate sync step is needed and the "
            "call returns without waiting on the network."
        ),
    )

    def _store(workspace: str | None = None) -> LocalStore:
        return router.resolve(workspace).store

    @mcp.tool()
    def store_init(
        project_id: str,
        phases: list[str],
        name: str | None = None,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Create the store this server points at, if it doesn't exist yet.
        If a .redthread.yaml marker points here and another machine already
        populated the store, attaches to it instead of erroring.
        In discovery mode (the server started with no --store) the workspace
        must already declare a store with a .redthread.yaml marker, which
        `redthread init` writes."""
        _, target = router.ensure_attached(workspace)
        if (target / constants.PROJECT_FILENAME).exists():
            return _store(workspace).manifest.model_dump(mode="json")
        store = LocalStore.init(target, project_id=project_id, phases=phases, name=name)
        router.forget(target)
        return store.manifest.model_dump(mode="json")

    async def _workspace_from_client(ctx: Context) -> str | None:
        """Ask the client which directory is open, if it implements roots."""
        root = await roots_probe.probe(ctx.session)
        return str(root) if root else None

    @mcp.tool()
    async def context_bootstrap(
        run_id: str | None = None,
        recent_runs: int = 5,
        memory_limit: int = 100,
        workspace: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """START HERE. One call that orients you in this project: its phase
        pipeline, recent runs and their status, published handoffs, and the
        full index of long-term memory with a description per entry. Call this
        at the start of every session — including inside a subagent, which
        does not inherit the main agent's instructions — before reading
        anything else or making changes. The `_next` field says what to do
        with what it returns.

        Also verifies that the store this server was pointed at is really
        this workspace's store, and reports it as `store.binding`: `ok`,
        `unverified` (nothing ties the store to this workspace), or
        `mismatch` (this repo's .redthread.yaml names a different store).
        Anything but `ok` comes with a `warning` field — read it and stop
        before writing, rather than filing this project's work under
        another project.

        Pass `workspace` — the absolute path of the project directory you
        are working in — whenever you know it. One MCP registration is
        commonly shared by every project a client has open, and `workspace`
        is what selects that project's own store; it sticks for the rest of
        the session, so later calls need not repeat it."""
        if workspace is None and ctx is not None:
            workspace = await _workspace_from_client(ctx)
        resolved = router.resolve(workspace, bind=True)
        return tools.context_bootstrap(
            resolved.store,
            run_id=run_id,
            recent_runs=recent_runs,
            memory_limit=memory_limit,
            workspace=resolved.workspace,
        )

    @mcp.tool()
    def run_start() -> dict[str, Any]:
        """Start a new run and return its record, including the new run_id.
        It becomes this store's active run, so run_id can be omitted from
        subsequent calls."""
        return tools.run_start(_store())

    @mcp.tool()
    def run_list() -> list[str]:
        """List every run_id in this store, oldest first."""
        return tools.run_list(_store())

    @mcp.tool()
    def context_log(
        phase: str,
        type: str,
        payload: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Append an immutable context entry; returns the new entry_id and the
        run it landed in. type is one of
        metric|decision|code_change|artifact_ref|error|milestone|note.
        Log decisions as you make them rather than reconstructing them later.
        run_id defaults to this store's newest active run."""
        return tools.context_log(_store(), phase, type, payload=payload, tags=tags, run_id=run_id)

    @mcp.tool()
    def context_read(
        phase: str | None = None, type: str | None = None, run_id: str | None = None
    ) -> dict[str, Any]:
        """Read raw context entries for a run, optionally filtered by
        phase/type. Prefer handoff_get or summary_get when you just need
        another phase's conclusions — this is the unabridged log.
        run_id defaults to this store's newest active run."""
        return tools.context_read(_store(), phase=phase, type=type, run_id=run_id)

    @mcp.tool()
    def artifact_put(
        phase: str,
        source_path: str,
        kind: str,
        artifact_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Register a small local file as a content-addressed artifact pointer.
        run_id defaults to this store's newest active run."""
        return tools.artifact_put(
            _store(), phase, source_path, kind, artifact_id=artifact_id, run_id=run_id
        )

    @mcp.tool()
    def artifact_get(artifact_id: str, run_id: str | None = None) -> dict[str, Any]:
        """Resolve an inline artifact to a verified local path.
        run_id defaults to this store's newest active run."""
        return tools.artifact_get(_store(), artifact_id, run_id=run_id)

    @mcp.tool()
    def summary_update(phase: str, markdown: str, run_id: str | None = None) -> dict[str, Any]:
        """Replace the rolling markdown summary for a phase — the short
        version a later phase or session reads first.
        run_id defaults to this store's newest active run."""
        return tools.summary_update(_store(), phase, markdown, run_id=run_id)

    @mcp.tool()
    def summary_get(phase: str, run_id: str | None = None) -> dict[str, Any]:
        """Read a phase's rolling markdown summary.
        run_id defaults to this store's newest active run."""
        return tools.summary_get(_store(), phase, run_id=run_id)

    @mcp.tool()
    def handoff_publish(
        phase: str,
        headline: str,
        key_results: dict[str, Any] | None = None,
        best_artifacts: list[str] | None = None,
        decisions: list[str] | None = None,
        open_questions: list[str] | None = None,
        figures: list[str] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Publish this phase's curated handoff for the next phase to consume.
        Do this when a phase finishes — it's what the next phase reads instead
        of replaying the raw log.
        run_id defaults to this store's newest active run."""
        return tools.handoff_publish(
            _store(),
            phase,
            headline,
            key_results=key_results,
            best_artifacts=best_artifacts,
            decisions=decisions,
            open_questions=open_questions,
            figures=figures,
            run_id=run_id,
        )

    @mcp.tool()
    def handoff_get(phase: str, run_id: str | None = None) -> dict[str, Any]:
        """Read a phase's curated handoff. Prefer this over context_read
        when picking up another phase's work.
        run_id defaults to this store's newest active run."""
        return tools.handoff_get(_store(), phase, run_id=run_id)

    @mcp.tool()
    def memory_write(
        namespace: str,
        key: str,
        content: str,
        description: str | None = None,
        tags: list[str] | None = None,
        push: bool = True,
        workspace: str | None = None,
    ) -> dict[str, Any]:
        """Write a long-term memory file (not tied to any run), portable
        across every machine that clones this store. Always pass a one-line
        `description` — it is what `memory_list` shows, so an entry without
        one is far less likely to be read again. Conventions and decisions go
        under namespace `notes`; dated session summaries under `sessions`
        (key `YYYY-MM-DD_short-slug`). Never write secrets: the store is a
        git repo, usually pushed to a shared remote.

        Write only after context_bootstrap reported `store.binding: ok` —
        this server serves one fixed store, so a global MCP registration
        will happily accept this project's memory into another project's
        history. The returned `project_id` names the project actually
        written to; if it isn't this one, say so rather than continuing.

        The store is committed synchronously and pushed in the background;
        the returned `sync` field says what happened (`pushing`, `committed`,
        `failed` with a `detail`, …). `pushing` means the entry is already
        safe locally and the network half is running — its outcome is
        reported by the next call on this store, and `sync_status` can
        confirm the push landed when that matters. A failed push never
        loses the entry. Pass push=False only to batch several writes and
        sync once at the end."""
        return tools.memory_write(
            _store(workspace),
            namespace,
            key,
            content,
            description=description,
            tags=tags,
            push=push,
        )

    @mcp.tool()
    def sync_status() -> dict[str, Any]:
        """Where this store stands against its remote: whether a background
        push is in flight, how the last one ended, and how many commits are
        not published yet. Check it before ending a session if the last
        memory_write reported `pushing` and the push must be confirmed."""
        return tools.sync_status(_store())

    @mcp.tool()
    def memory_read(namespace: str, key: str) -> str | None:
        """Read one long-term memory file in full. Find the key with
        memory_list or memory_search first."""
        return tools.memory_read(_store(), namespace, key)

    @mcp.tool()
    def memory_list(namespace: str | None = None) -> list[dict[str, Any]]:
        """Index of long-term memory: every key with a one-line description,
        so you can tell what's worth reading without opening each entry.
        Spans every namespace unless you name one. Call this at session start
        before making changes, then memory_read whatever looks relevant."""
        return tools.memory_list(_store(), namespace)

    @mcp.tool()
    def memory_search(
        query: str, namespace: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Substring search over memory keys, descriptions, tags, and bodies.
        Each hit includes the line that matched. Prefer this over reading
        entries one by one when you're looking for something specific."""
        return tools.memory_search(_store(), query, namespace=namespace, limit=limit)

    @mcp.tool()
    def memory_import(
        source: str,
        namespace: str = "imported",
        recursive: bool = True,
        overwrite: bool = False,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Port memory that already exists as files at `source` into this
        store — a harness's own memory directory (e.g.
        ~/.claude/projects/<project>/memory/), a notes folder, another
        store's memory/ tree. `source` may be a file or a directory; one
        text file becomes one entry, keyed by its path under `source` with
        the extension dropped, and any frontmatter it already had is kept.

        Copies, never moves: the source files are left where they are.
        Existing keys are skipped unless overwrite=True, and identical
        content is skipped either way, so re-running is safe. Commits and
        pushes once for the whole batch. Use this instead of re-typing
        memory by hand when a project arrives with notes already written."""
        return tools.memory_import(
            _store(),
            source,
            namespace=namespace,
            recursive=recursive,
            overwrite=overwrite,
            tags=tags,
        )

    @mcp.tool()
    def agents_md_bootstrap(
        project_dir: str | None = None, workspace: str | None = None
    ) -> dict[str, Any]:
        """Add a short Redthread usage policy to this project's AGENTS.md
        (or CLAUDE.md, if that's the one that already exists) so agents use
        this store as memory automatically in future sessions, without
        being told each time. Idempotent — call this first, before any
        other tool, on every session; it's a no-op once already present.
        project_dir defaults to this session's workspace."""
        target_dir = Path(project_dir) if project_dir else router.workspace_for(workspace)
        target_store = router.store_path_for(workspace)
        try:
            project_id = _store(workspace).manifest.project_id
        except StoreError:
            project_id = None  # store not created yet; the policy still applies
        return tools.agents_md_bootstrap(target_store, target_dir, project_id)

    # ---- resources -------------------------------------------------------
    # The same reads as the tools above, exposed as resources so clients that
    # support attaching them can put this context in front of the model
    # without spending a tool round-trip on it. Read-only by construction:
    # nothing here mutates the store.

    @mcp.resource(
        "redthread://project",
        name="Redthread project",
        description="This project's manifest: id, name, and declared phase pipeline.",
        mime_type="application/json",
    )
    def project_resource() -> str:
        return json.dumps(_store().manifest.model_dump(mode="json"), indent=2)

    @mcp.resource(
        "redthread://memory",
        name="Redthread memory index",
        description="Every long-term memory entry with a one-line description.",
        mime_type="application/json",
    )
    def memory_index_resource() -> str:
        return json.dumps(_store().memory_index(), indent=2)

    @mcp.resource(
        "redthread://bootstrap",
        name="Redthread orientation",
        description="Pipeline, recent runs, handoffs, and the memory index in one payload.",
        mime_type="application/json",
    )
    def bootstrap_resource() -> str:
        return json.dumps(tools.context_bootstrap(_store()), indent=2)

    @mcp.resource(
        "redthread://memory/{namespace}/{key}",
        name="Redthread memory entry",
        description="One long-term memory entry, verbatim.",
        mime_type="text/markdown",
    )
    def memory_entry_resource(namespace: str, key: str) -> str:
        content = _store().memory_read(namespace, key)
        if content is None:
            raise StoreError(
                f"no memory entry {namespace}/{key} — the memory_list tool "
                "or the redthread://memory resource shows what exists"
            )
        return content

    @mcp.resource(
        "redthread://handoff/{run_id}/{phase}",
        name="Redthread phase handoff",
        description="A phase's curated handoff for the next phase to consume.",
        mime_type="application/json",
    )
    def handoff_resource(run_id: str, phase: str) -> str:
        return json.dumps(tools.handoff_get(_store(), phase, run_id=run_id), indent=2)

    @mcp.resource(
        "redthread://summary/{run_id}/{phase}",
        name="Redthread phase summary",
        description="A phase's rolling markdown summary.",
        mime_type="text/markdown",
    )
    def summary_resource(run_id: str, phase: str) -> str:
        markdown = _store().get_summary(run_id, phase)
        if markdown is None:
            raise StoreError(f"phase {phase!r} of run {run_id} has no summary yet")
        return markdown

    return mcp


def main(
    store_path: Path | None = None, host_repo: Path | None = None, allow_clone: bool = False
) -> None:
    _announce_update()
    build_server(store_path, host_repo=host_repo, allow_clone=allow_clone).run(transport="stdio")


def _announce_update() -> None:
    """Note a newer release on stderr as the server comes up.

    stderr specifically: stdout is the MCP transport, and one stray line on it
    corrupts the session. `context_bootstrap` carries the same notice to the
    agent, which is what actually reaches the user — this copy is for whoever
    reads the server log.
    """
    message = update_check.update_message(__version__)
    if message:
        print(message, file=sys.stderr)
