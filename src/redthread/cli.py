"""Redthread CLI: init, run, log, artifact, summary, handoff, backend, resume, sync."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from redthread import hostconfig
from redthread.adapters.present import run_present
from redthread.mcp.server import main as run_mcp_server
from redthread.models import Handoff
from redthread.paths import PathsMap
from redthread.resume import resume as resume_run
from redthread.resume import resume_worktree as resume_worktree_run
from redthread.store import LocalStore, StoreError, gitio
from redthread.sync import run_daemon

# Store content (memory notes, handoffs, summaries) is UTF-8 and often has
# non-ASCII text; the default console stdout encoding on Windows is not
# UTF-8, so printing it there would otherwise mangle or replace characters.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

app = typer.Typer(no_args_is_help=True, add_completion=False)

StoreOpt = Annotated[Path, typer.Option("--store", help="Path to the Redthread store")]


def _open(store: Path) -> LocalStore:
    try:
        return LocalStore(store)
    except StoreError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e


def _fail(e: Exception) -> None:
    typer.secho(str(e), fg=typer.colors.RED, err=True)
    raise typer.Exit(1) from e


@app.command()
def init(
    project_id: str,
    phases: Annotated[
        str, typer.Option(help="Comma-separated phase pipeline")
    ] = "build,test,present",
    store: StoreOpt = Path("./redthread-store"),
    name: str | None = None,
    worktree_repo: Annotated[
        Path | None,
        typer.Option(
            help="Create the store as an orphan-branch worktree of this repo "
            "instead of its own repo — the repo's checked-out branch is never touched"
        ),
    ] = None,
    branch: Annotated[
        str, typer.Option(help="Orphan branch name, used only with --worktree-repo")
    ] = "redthread-store",
    host_repo: Annotated[
        Path | None,
        typer.Option(
            help="Repo-mode only (ignored with --worktree-repo, which always records its "
            "own host repo): also write .redthread.yaml here, so `redthread attach` or "
            "an MCP server launched from this repo can find the store later"
        ),
    ] = None,
) -> None:
    """Create a new Redthread store with a declared phase pipeline."""
    phase_list = [p.strip() for p in phases.split(",") if p.strip()]
    try:
        if worktree_repo:
            LocalStore.init_worktree(
                worktree_repo, store, branch, project_id=project_id, phases=phase_list, name=name
            )
        else:
            LocalStore.init(
                store, project_id=project_id, phases=phase_list, name=name, host_repo=host_repo
            )
    except StoreError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    typer.echo(f"initialized store at {store} (phases: {', '.join(phase_list)})")


project_app = typer.Typer(no_args_is_help=True, help="Manage a project's declared pipeline")
app.add_typer(project_app, name="project")


@project_app.command("add-phase")
def project_add_phase(
    phase: str,
    store: StoreOpt = Path("./redthread-store"),
    backfill: Annotated[
        bool,
        typer.Option(help="Add the phase as 'pending' to runs that aren't done/failed yet"),
    ] = True,
) -> None:
    """Add a new phase to the project's pipeline, e.g. as requirements grow."""
    s = _open(store)
    try:
        manifest = s.add_phase(phase, backfill_open_runs=backfill)
    except StoreError as e:
        _fail(e)
    typer.echo(f"phases: {', '.join(manifest.phases)}")


run_app = typer.Typer(no_args_is_help=True, help="Manage runs")
app.add_typer(run_app, name="run")


@run_app.command("start")
def run_start(store: StoreOpt = Path("./redthread-store")) -> None:
    record = _open(store).start_run()
    typer.echo(record.run_id)


@run_app.command("list")
def run_list(store: StoreOpt = Path("./redthread-store")) -> None:
    for run_id in _open(store).list_runs():
        typer.echo(run_id)


@app.command()
def log(
    run_id: str,
    phase: str,
    type: str,
    payload: Annotated[str, typer.Argument(help="JSON object")] = "{}",
    tags: Annotated[str, typer.Option(help="Comma-separated tags")] = "",
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    """Append a context entry."""
    s = _open(store)
    try:
        parsed_payload = json.loads(payload)
    except json.JSONDecodeError as e:
        typer.secho(f"payload is not valid JSON: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    try:
        entry = s.log(run_id, phase, type, payload=parsed_payload, tags=tag_list)
    except StoreError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    typer.echo(entry.entry_id)


@app.command()
def read(
    run_id: str,
    phase: Annotated[str | None, typer.Option(help="Filter to one phase")] = None,
    type: Annotated[str | None, typer.Option(help="Filter to one entry type")] = None,
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    """Read context entries for a run, newest-safe (creation order)."""
    s = _open(store)
    try:
        entries = s.read_entries(run_id, phase=phase, type=type)
    except StoreError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    for entry in entries:
        typer.echo(entry.model_dump_json())


artifact_app = typer.Typer(no_args_is_help=True, help="Manage artifacts")
app.add_typer(artifact_app, name="artifact")


@artifact_app.command("add")
def artifact_add(
    run_id: str,
    phase: str,
    source: Path,
    kind: str,
    artifact_id: Annotated[str | None, typer.Option()] = None,
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    s = _open(store)
    try:
        artifact = s.add_artifact(run_id, phase, source, kind, artifact_id=artifact_id)
    except StoreError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    typer.echo(artifact.artifact_id)


@artifact_app.command("add-blob")
def artifact_add_blob(
    run_id: str,
    phase: str,
    source: Path,
    kind: str,
    backend: Annotated[str, typer.Option(help="Logical backend name (see `redthread backend`)")],
    artifact_id: Annotated[str | None, typer.Option()] = None,
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    """Register a large artifact via a content-addressed blob backend."""
    s = _open(store)
    try:
        blob_backend = PathsMap().open_backend(backend)
        artifact = s.add_blob_artifact(
            run_id, phase, source, kind, backend, blob_backend, artifact_id=artifact_id
        )
    except (StoreError, KeyError) as e:
        _fail(e)
    typer.echo(artifact.artifact_id)


@artifact_app.command("get")
def artifact_get(
    run_id: str,
    artifact_id: str,
    dest: Annotated[Path | None, typer.Option(help="Where to copy blob-backed artifacts")] = None,
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    """Resolve any artifact (inline or blob-backed) to a local, verified path."""
    s = _open(store)
    try:
        index = s.get_artifact_index(run_id)
        pointer = index.artifacts.get(artifact_id)
        backends = {}
        if pointer and pointer.backend != "inline":
            name = pointer.uri.split("://", 1)[1].split("/", 1)[0]
            backends[name] = PathsMap().open_backend(name)
        _, path = s.resolve_artifact(run_id, artifact_id, backends=backends, dest=dest)
    except (StoreError, KeyError) as e:
        _fail(e)
    typer.echo(str(path))


summary_app = typer.Typer(no_args_is_help=True, help="Manage rolling phase summaries")
app.add_typer(summary_app, name="summary")


@summary_app.command("set")
def summary_set(
    run_id: str,
    phase: str,
    file: Annotated[Path, typer.Argument(help="Markdown file to use as the summary")],
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    s = _open(store)
    try:
        s.set_summary(run_id, phase, file.read_text(encoding="utf-8-sig"))
    except StoreError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e


@summary_app.command("get")
def summary_get(run_id: str, phase: str, store: StoreOpt = Path("./redthread-store")) -> None:
    text = _open(store).get_summary(run_id, phase)
    if text is None:
        raise typer.Exit(1)
    typer.echo(text)


handoff_app = typer.Typer(no_args_is_help=True, help="Publish/read curated phase handoffs")
app.add_typer(handoff_app, name="handoff")


@handoff_app.command("publish")
def handoff_publish(
    run_id: str,
    phase: str,
    file: Annotated[Path, typer.Argument(help="JSON file matching the Handoff schema")],
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    s = _open(store)
    try:
        data = json.loads(file.read_text(encoding="utf-8-sig"))
        data.setdefault("run_id", run_id)
        data.setdefault("from_phase", phase)
        handoff = Handoff.model_validate(data)
        s.publish_handoff(handoff)
    except (json.JSONDecodeError, StoreError, ValueError) as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e


@handoff_app.command("get")
def handoff_get(run_id: str, phase: str, store: StoreOpt = Path("./redthread-store")) -> None:
    s = _open(store)
    try:
        handoff = s.get_handoff(run_id, phase)
    except StoreError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from e
    typer.echo(handoff.model_dump_json(indent=2))


backend_app = typer.Typer(no_args_is_help=True, help="Configure per-machine blob backend paths")
app.add_typer(backend_app, name="backend")


@backend_app.command("set")
def backend_set(name: str, path: Path) -> None:
    """Map a logical backend name to a local/mounted directory on this machine."""
    PathsMap().set(name, path)
    typer.echo(f"backend {name!r} -> {path}")


@backend_app.command("list")
def backend_list() -> None:
    for name, path in PathsMap().list().items():
        typer.echo(f"{name}\t{path}")


memory_app = typer.Typer(no_args_is_help=True, help="Read/write portable long-term agent memory")
app.add_typer(memory_app, name="memory")


@memory_app.command("write")
def memory_write(
    namespace: str,
    key: str,
    file: Annotated[Path, typer.Argument(help="File whose content becomes the memory entry")],
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    s = _open(store)
    try:
        s.memory_write(namespace, key, file.read_text(encoding="utf-8-sig"))
    except (StoreError, ValueError) as e:
        _fail(e)


@memory_app.command("read")
def memory_read(namespace: str, key: str, store: StoreOpt = Path("./redthread-store")) -> None:
    s = _open(store)
    try:
        content = s.memory_read(namespace, key)
    except ValueError as e:
        _fail(e)
    if content is None:
        raise typer.Exit(1)
    typer.echo(content)


@memory_app.command("list")
def memory_list(namespace: str, store: StoreOpt = Path("./redthread-store")) -> None:
    s = _open(store)
    try:
        keys = s.memory_list(namespace)
    except ValueError as e:
        _fail(e)
    for key in keys:
        typer.echo(key)


@app.command()
def resume(
    run_id: str,
    store: StoreOpt = Path("./redthread-store"),
    remote: Annotated[
        str | None, typer.Option(help="Clone from this URL if store is missing")
    ] = None,
    worktree_repo: Annotated[
        Path | None,
        typer.Option(help="Attach as an orphan-branch worktree of this (already-cloned) repo"),
    ] = None,
    branch: Annotated[
        str, typer.Option(help="Orphan branch name, used only with --worktree-repo")
    ] = "redthread-store",
) -> None:
    """Pick up a run on this machine: clone if needed, extend node lineage."""
    try:
        if worktree_repo:
            record = resume_worktree_run(worktree_repo, store, branch, run_id)
        else:
            record = resume_run(store, run_id, remote=remote)
    except StoreError as e:
        _fail(e)
    typer.echo(f"resumed {record.run_id} on this node ({len(record.nodes)} node stints total)")


@app.command()
def attach(
    store: StoreOpt = Path("./redthread-store"),
    host_repo: Annotated[
        Path, typer.Option(help="Repo holding .redthread.yaml (defaults to the current directory)")
    ] = Path("."),
    allow_clone: Annotated[
        bool,
        typer.Option(help="Repo-mode only: clone the store from the url recorded in the marker"),
    ] = False,
) -> None:
    """Make the store at --store exist, per .redthread.yaml in --host-repo —
    attaching a worktree branch, cloning a store repo (with --allow-clone),
    or syncing the marker's url once a repo-mode store has a remote."""
    try:
        config = hostconfig.attach(host_repo, store, allow_clone=allow_clone)
    except StoreError as e:
        _fail(e)
    typer.echo(f"attached {store} ({config.store.mode} mode)")


@app.command()
def sync(
    store: StoreOpt = Path("./redthread-store"),
    message: str = "redthread sync",
) -> None:
    """One-shot commit + pull --rebase + push against the store's git remote."""
    try:
        pushed = gitio.sync(Path(store), message)
    except StoreError as e:
        _fail(e)
    typer.echo("synced (pushed)" if pushed else "synced (nothing to push)")


daemon_app = typer.Typer(no_args_is_help=True, help="Run the auto-commit sync daemon")
app.add_typer(daemon_app, name="daemon")


@daemon_app.command("run")
def daemon_run(
    store: StoreOpt = Path("./redthread-store"),
    interval: Annotated[float, typer.Option(help="Seconds between sync cycles")] = 10.0,
    message: str = "redthread auto-commit",
) -> None:
    """Foreground loop: sync the store on a debounce interval until interrupted."""
    run_daemon(Path(store), interval=interval, message=message)


@app.command()
def present(
    run_id: str,
    output_dir: Path,
    phase: str = "present",
    store: StoreOpt = Path("./redthread-store"),
) -> None:
    """Render report.md, deck.pptx, and a docs/ tree from upstream handoffs."""
    s = _open(store)
    try:
        handoff = run_present(s, run_id, output_dir, phase=phase)
    except StoreError as e:
        _fail(e)
    typer.echo(handoff.model_dump_json(indent=2))


@app.command("mcp-serve")
def mcp_serve(
    store: StoreOpt = Path("./redthread-store"),
    host_repo: Annotated[
        Path,
        typer.Option(
            help="Repo to look for .redthread.yaml in if --store doesn't exist yet "
            "(defaults to the current directory, which is normally the project root)"
        ),
    ] = Path("."),
    allow_clone: Annotated[
        bool,
        typer.Option(
            help="Repo-mode only: allow auto-attach to `git clone` the store from the "
            "url recorded in .redthread.yaml if it isn't present locally"
        ),
    ] = False,
) -> None:
    """Run the MCP server (stdio) exposing this store as agent memory."""
    run_mcp_server(Path(store), host_repo=Path(host_repo), allow_clone=allow_clone)


if __name__ == "__main__":
    app()
