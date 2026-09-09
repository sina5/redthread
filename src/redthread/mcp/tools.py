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

from redthread import __version__, constants, hostconfig, memory_port, update_check
from redthread.models import Handoff
from redthread.store import LocalStore, StoreError, gitio
from redthread.sync import shared_syncer


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
    store: LocalStore,
    run_id: str | None = None,
    recent_runs: int = 5,
    memory_limit: int = 100,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Everything an agent needs to orient itself in this project, in one call.

    Exists because the alternative is a cold agent chaining run_list ->
    memory_list (per namespace it doesn't know about yet) -> handoff_get and
    usually giving up before it gets there. One front door is what makes
    memory actually get read.

    Being the front door also makes this the one place a wrong-store
    misconfiguration can be caught before anything is written: when
    ``workspace`` is given, the served store is checked against it and a
    mismatch leads the response instead of being buried in it.
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
    binding = (
        hostconfig.check_binding(workspace, store.layout.root) if workspace is not None else None
    )
    payload: dict[str, Any] = {
        "project": {
            "project_id": manifest.project_id,
            "name": manifest.name,
            "phases": manifest.phases,
        },
        "store": {
            "path": str(store.layout.root.resolve()),
            "workspace": binding["workspace"] if binding else None,
            "binding": binding["status"] if binding else "unchecked",
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
        "_next": _bootstrap_next(resolved, memory, binding, manifest.project_id),
    }
    if binding and binding["status"] != "ok":
        payload["warning"] = _binding_warning(binding, manifest.project_id)
    # Surfaced through the agent, which is the only party here with a way to
    # reach the human. Throttled and failure-silent, so it costs nothing on
    # the sessions where there is nothing to say.
    upgrade = update_check.update_message(__version__)
    if upgrade:
        payload["update_available"] = upgrade
    return payload


def _binding_warning(binding: dict[str, object], project_id: str) -> str:
    """The wrong-store message, phrased so an agent stops rather than reads
    past it. Names the project the store belongs to, because that is what
    makes the mismatch legible to whoever has to fix the registration."""
    lead = (
        f"WRONG STORE: this store belongs to project {project_id!r}, which is not the "
        f"project open in this workspace."
        if binding["status"] == "mismatch"
        else f"UNVERIFIED STORE: this store belongs to project {project_id!r}; nothing "
        f"confirms it is this workspace's store."
    )
    return (
        f"{lead} {binding['detail']} Do not write memory, entries, or handoffs here until "
        f"this is resolved — anything written lands in the wrong project's history and is "
        f"invisible to this one. Tell the user the redthread MCP server is pointed at the "
        f"wrong store and needs a per-project `--store` (or a `.redthread.yaml` marker in "
        f"this repo); `redthread init --worktree-repo .` creates this project its own store."
    )


def _bootstrap_next(
    run_id: str | None,
    memory: list[dict[str, Any]],
    binding: dict[str, object] | None = None,
    project_id: str | None = None,
) -> str:
    # A wrong-store warning has to displace the normal next steps, not sit
    # beside them: "read memory, then write a session note" is precisely the
    # sequence that misfiles work into another project.
    if binding is not None and binding["status"] == "mismatch":
        return (
            "STOP — do not read this store's memory as if it were this project's, and do "
            "not write anything here. Report the misconfiguration in `warning` to the user "
            "and get the store path fixed first."
        )
    steps = []
    if binding is not None and binding["status"] == "unverified":
        steps.append(
            "first confirm with the user that this really is this project's store "
            "(see `warning`) — if it isn't, stop and fix the MCP `--store` before writing"
        )
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
        "(namespace `sessions`, key `YYYY-MM-DD_short-slug`), which commits and "
        "pushes the store for you"
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


_PUSH_NEXT = {
    "pushing": "Memory is written and committed; the push is running in the background. "
    "Its outcome is reported by the next redthread call on this store (or sync_status), "
    "and an unpushed commit is republished by any later sync, so nothing is ever lost.",
    "pushed": "Memory is written and pushed — other machines get it on their next sync.",
    "committed": "Memory is written and committed locally — durable here, but it has "
    "not left this machine; the detail below says why.",
    "no_changes": "Memory is written; git reported nothing new to push (the content was "
    "already committed, most likely by the auto-commit daemon).",
    "failed": "Memory is written to disk but the push failed — it is safe locally and "
    "nothing was lost, but it will not reach other machines until this is resolved. "
    "Fix the cause below and re-run `redthread sync --store <store>`.",
    "skipped": "Memory is written but neither committed nor pushed; nothing is durable "
    "yet — `redthread sync --store <store>` commits and publishes it.",
}


def _commit_and_maybe_push(store: LocalStore, message: str, push: bool) -> dict[str, Any]:
    """Commit now (fast, local, makes the write durable), push if allowed.

    The commit is unconditional: it is what makes the write survive, it has
    no consequences off this machine, and a caller declining to publish is
    never asking to lose data. Only the network half is optional, and only
    it can be refused by the store's `PublishPolicy` — a worktree store
    shares its host repo's remote, which is not somewhere memory should go
    without being asked.

    The synchronous version of the push — pull --rebase, then push, inside
    the tool call — made every memory write wait on two network round trips
    for something that doesn't affect whether the write succeeded, so it
    moved to a background worker. A store without a remote skips the worker
    entirely: `sync_report` is local-only there and its `committed` detail
    explains how to add one.
    """
    root = store.layout.root
    policy = store.publish_policy()
    if not push or not policy.allowed:
        report = gitio.commit_report(root, message)
        if report["status"] != "failed":
            report["detail"] = f"not pushed: {policy.reason}" if push else "not pushed (push=False)"
        return report
    if not gitio.has_remote(root):
        return gitio.sync_report(root, message)
    try:
        gitio.commit_if_dirty(root, message)
    except (gitio.GitError, OSError) as e:
        return {"status": "failed", "detail": str(e)}
    return shared_syncer().schedule(root, message)


def _push_next_text(sync: dict[str, Any]) -> str:
    next_text = _PUSH_NEXT[sync["status"]]
    if sync.get("detail"):
        next_text = f"{next_text} ({sync['detail']})"
    previous = sync.get("previous")
    if previous is not None:
        next_text = (
            f"{next_text} NOTE: the previous background push of this store FAILED "
            f"({previous.get('detail', 'no detail')}) — report this, and run "
            "`redthread sync --store <store>` to publish the stranded commits."
        )
    return next_text


def sync_status(store: LocalStore) -> dict[str, Any]:
    """Where this store stands against its remote: whether a background push
    is in flight, how the last one ended, and how many commits have not
    been published yet."""
    root = store.layout.root
    syncer = shared_syncer()
    policy = store.publish_policy()
    status: dict[str, Any] = {
        "project_id": store.manifest.project_id,
        "has_remote": gitio.has_remote(root),
        "remote": policy.remote_url,
        "publishes": policy.allowed,
        "publish_reason": policy.reason,
        "branch_has_commits": gitio.has_commits(root),
        "in_flight": syncer.in_flight(root),
        "last_push": syncer.last_report(root),
        "unpushed_commits": gitio.ahead_count(root),
        "dirty": gitio.is_dirty(root),
        "uncommitted_memory": sorted(store.uncommitted_memory_keys()),
    }
    if status["in_flight"]:
        status["_next"] = "A background push is running — call again to see how it ended."
    elif not policy.allowed:
        status["_next"] = (
            f"Memory is committed locally but never pushed: {policy.reason}. That is a "
            "deliberate setting, not a failure — say so if the user expects memory on "
            "other machines."
        )
    elif not status["has_remote"]:
        status["_next"] = (
            "No remote on the store repo, so memory can't leave this machine — add one "
            "with `git -C <store> remote add origin <url>`."
        )
    elif status["unpushed_commits"] or status["dirty"]:
        status["_next"] = (
            "Unpublished local state — the next write pushes it, or run "
            "`redthread sync --store <store>` to publish now."
        )
    else:
        status["_next"] = "Fully published — the remote has everything."
    return status


def memory_write(
    store: LocalStore,
    namespace: str,
    key: str,
    content: str,
    description: str | None = None,
    tags: list[str] | None = None,
    push: bool = True,
) -> dict[str, Any]:
    """Write a memory entry, commit it, and by default start a push.

    Pushing is the default because an unpushed memory is invisible to the
    next machine, which is the whole point of the store — and an agent that
    has to remember a second call will sometimes not make it. The push runs
    in the background (`status: pushing`) so the caller never waits on the
    network; a push failure is surfaced by the next call on this store.

    `push=False` declines only the publish step: the entry is committed
    either way, because an uncommitted entry is not memory, it is a file
    waiting to be lost.
    """
    store.memory_write(namespace, key, content, description=description, tags=tags)
    # Naming the project written to costs nothing and is the last chance to
    # notice a write that went to another project's store — a session that
    # skipped context_bootstrap has had no other signal.
    result: dict[str, Any] = {
        "namespace": namespace,
        "key": key,
        "description": description,
        "project_id": store.manifest.project_id,
    }
    sync = _commit_and_maybe_push(store, f"redthread: memory {namespace}/{key}", push)
    result["sync"] = sync
    result["_next"] = _push_next_text(sync)
    return result


_IMPORT_NEXT_NO_FILES = (
    "Nothing was imported — no text files found at that path. Check the path, "
    "and pass recursive=True if the entries are in subdirectories."
)
_IMPORT_NEXT_ALL_SKIPPED = (
    "Nothing was written — every file found is already in this namespace "
    "(see `skipped`). Pass overwrite=True to replace entries that differ."
)


def memory_import(
    store: LocalStore,
    source: str | Path,
    namespace: str = "imported",
    recursive: bool = True,
    overwrite: bool = False,
    tags: list[str] | None = None,
    push: bool = True,
) -> dict[str, Any]:
    """Copy existing memory files at `source` into `namespace`, one entry
    per file, then commit+push once for the whole batch.

    Entries are copied verbatim: whatever frontmatter the source already had
    survives, and `memory_list` derives a description from it (or from the
    first meaningful line) the same way it does for anything else. This is a
    copy, never a move — the source files are left untouched, so a bad
    import costs nothing but a namespace.

    Existing keys are skipped rather than clobbered unless `overwrite`, and
    a key whose content already matches is skipped either way, so re-running
    an import is cheap and non-destructive.
    """
    source = Path(source).expanduser()
    if not source.exists():
        raise StoreError(f"nothing to import: {source} does not exist")

    paths = memory_port.discover(source, recursive=recursive)
    imported: list[str] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []

    for path in paths:
        try:
            key = memory_port.key_for(path, source)
            content = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError, ValueError) as e:
            failed.append({"path": str(path), "error": str(e)})
            continue
        try:
            existing = store.memory_read(namespace, key)
            if existing is not None:
                # An unchanged re-import is a no-op even with overwrite on:
                # rewriting identical bytes only makes noise in the history.
                if existing == content:
                    skipped.append({"key": key, "reason": "unchanged"})
                    continue
                if not overwrite:
                    skipped.append({"key": key, "reason": "exists"})
                    continue
            store.memory_write(namespace, key, content, tags=tags)
        except (StoreError, ValueError, OSError) as e:
            failed.append({"path": str(path), "error": str(e)})
            continue
        imported.append(key)

    result: dict[str, Any] = {
        "source": str(source),
        "namespace": namespace,
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "counts": {
            "imported": len(imported),
            "skipped": len(skipped),
            "failed": len(failed),
        },
    }

    # Nothing written means nothing to publish — a sync here would report
    # `no_changes` and read like the import half-worked.
    if not imported:
        result["sync"] = {"status": "skipped"}
        result["_next"] = _IMPORT_NEXT_NO_FILES if not paths else _IMPORT_NEXT_ALL_SKIPPED
        return result

    sync = _commit_and_maybe_push(
        store, f"redthread: import {len(imported)} entries into {namespace}", push
    )
    result["sync"] = sync
    result["_next"] = _push_next_text(sync)
    return result


def memory_read(store: LocalStore, namespace: str, key: str) -> str | None:
    return store.memory_read(namespace, key)


def memory_list(store: LocalStore, namespace: str | None = None) -> list[dict[str, Any]]:
    """The memory index, each entry flagged `uncommitted` when it exists
    only as a working-tree file.

    Listing is how a caller checks that a write worked, so it has to be able
    to tell "written" from "written and durable" — otherwise it keeps
    confirming a write that git would happily throw away.
    """
    uncommitted = store.uncommitted_memory_keys()
    return [
        {**item, "uncommitted": f"{item['namespace']}/{item['key']}" in uncommitted}
        for item in store.memory_index(namespace)
    ]


def memory_search(
    store: LocalStore, query: str, namespace: str | None = None, limit: int = 20
) -> list[dict[str, Any]]:
    return store.memory_search(query, namespace=namespace, limit=limit)


_AGENTS_MD_MARKER = constants.AGENTS_MD_MARKER


def _agents_md_section(store_path: Path, project_id: str | None = None) -> str:
    # The expected project_id is pinned into the file on purpose: AGENTS.md
    # travels with the repo, so it stays correct even when the MCP server is
    # registered globally and points somewhere else entirely. That makes the
    # check possible from the agent's side, with no cooperation from the
    # client's configuration.
    identity = (
        f"- **Check you are in the right store before writing.** This project's store\n"
        f"  is `{project_id}`. If `context_bootstrap` reports a different\n"
        f"  `project.project_id`, or `store.binding` is not `ok`, STOP: the MCP server\n"
        f"  is pointed at another project's store. Say so and do not write — memory\n"
        f"  written there is filed under the wrong project and invisible to this one.\n"
        if project_id
        else "- **Check you are in the right store before writing.** If\n"
        "  `context_bootstrap` reports `store.binding` other than `ok`, STOP: the MCP\n"
        "  server is pointed at another project's store. Say so and do not write.\n"
    )
    return (
        f"{_AGENTS_MD_MARKER}\n"
        "## Agent memory (Redthread)\n\n"
        "This project's long-term memory is a Redthread store (MCP server "
        f'"redthread", `--store {store_path}`) shared by every session, machine,\n'
        "and agent working on this project. It is the only memory that counts here.\n\n"
        "- At session start, call `context_bootstrap` once — it returns this\n"
        "  project's pipeline, recent runs, and the memory index in one call — then\n"
        "  `memory_read` what looks relevant before making changes.\n"
        "- Pass this repo's absolute path as `workspace` on that first\n"
        "  `context_bootstrap` call. One MCP registration is often shared by every\n"
        "  project a client has open, and `workspace` is what selects this\n"
        "  project's store out of them. It sticks for the rest of the session.\n"
        f"{identity}"
        "- Never record durable knowledge anywhere else: not in the harness's own\n"
        "  memory directory (e.g. `~/.claude/projects/**/memory/`), not in a scratch\n"
        "  notes file. Those are invisible to other sessions, machines, and agents.\n"
        "- After completing a non-trivial task, write a dated summary with\n"
        "  `memory_write` (namespace `sessions`, key like `YYYY-MM-DD_short-slug`,\n"
        "  always with a one-line `description`): what changed, why, validation\n"
        "  performed, follow-ups. Write when the task finishes, not batched at the\n"
        "  end of the session, and without being asked.\n"
        "- `memory_write` commits synchronously and pushes in the background, so\n"
        "  memory reaches other machines without a second step and without making\n"
        "  you wait on the network. Check the `sync` field it returns; if it says\n"
        "  `failed`, or a later call reports a previous push FAILED, say so and\n"
        "  fix it rather than leaving the entry stranded on this machine\n"
        "  (`sync_status` confirms a push landed when that matters).\n"
        "- Store durable conventions and decisions under the `notes` namespace;\n"
        "  check `memory_search` first and update the existing entry instead of\n"
        "  adding a near-duplicate. Never store secrets.\n"
        "- If the MCP server isn't connected, use the CLI on the same store rather\n"
        f"  than skipping memory: `redthread bootstrap --store {store_path}`,\n"
        f"  `redthread memory list|search|read|write ... --store {store_path}`.\n"
        "- Subagents do not inherit this file. When you delegate work that should\n"
        "  be remembered, tell the subagent to call `context_bootstrap` too.\n"
    )


def agents_md_bootstrap(
    store_path: Path, project_dir: Path, project_id: str | None = None
) -> dict[str, Any]:
    """Ensure project_dir's AGENTS.md (or CLAUDE.md, if that's the one that
    already exists) tells agents to use this store as memory. Idempotent —
    safe to call every session; a no-op once the instructions are present.

    `project_id` pins which project this repo's memory belongs to, so a
    later session can catch an MCP server pointed at a different store."""
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

    section = _agents_md_section(store_path, project_id)
    if target.exists():
        existing = target.read_text(encoding="utf-8-sig")
        new_text = existing.rstrip("\n") + "\n\n" + section
        status = "appended"
    else:
        new_text = section
        status = "created"
    target.write_text(new_text, encoding="utf-8", newline="\n")
    return {"status": status, "file": str(target)}
