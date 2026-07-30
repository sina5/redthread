"""LocalStore: single-machine read/write operations on a Redthread store.

Entries are immutable, one file each, named ``<seq>-<ulid>.json``. The seq is
advisory and local; the ULID is the identity, so concurrent writers on
different nodes can never collide on a filename.
"""

import contextlib
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from redthread import memory_doc
from redthread.blobs.base import BlobBackend
from redthread.hashing import sha256_file
from redthread.ids import get_node_id, new_ulid
from redthread.models import (
    Artifact,
    ArtifactIndex,
    ContextEntry,
    Handoff,
    NodeStint,
    ProjectManifest,
    Provenance,
    RunRecord,
)
from redthread.store import gitio
from redthread.store.errors import StoreError
from redthread.store.layout import StoreLayout

_GITATTRIBUTES = "* text=auto eol=lf\n*.ndjson merge=union\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _dump_yaml(path: Path, model: Any) -> None:
    _write_text(path, yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False))


def _publish_host_marker(host_repo: Path, store_path: Path) -> dict[str, Any]:
    # Deferred for the same reason as _write_host_marker below: importing
    # redthread.hostconfig at module level would be circular.
    from redthread.hostconfig import publish_marker

    return publish_marker(host_repo, store_path)


class LocalStore:
    def __init__(self, root: Path):
        #: What `init`/`init_worktree` did with the host repo's marker commit
        #: (None when this store was merely opened, or publishing was off).
        self.marker_status: dict[str, Any] | None = None
        self.layout = StoreLayout(Path(root))
        if not self.layout.project_yaml.exists():
            raise StoreError(
                f"no Redthread store at {root} (missing project.yaml) — create one with "
                "the store_init tool (or `redthread init`), or check that the --store "
                "path is right; if another machine already made it, `redthread attach` "
                "recreates it from the committed .redthread.yaml marker"
            )
        self.manifest = ProjectManifest.model_validate(
            yaml.safe_load(self.layout.project_yaml.read_text(encoding="utf-8"))
        )

    # ---- lifecycle -------------------------------------------------------

    @classmethod
    def init(
        cls,
        root: Path,
        project_id: str,
        phases: list[str],
        name: str | None = None,
        host_repo: Path | None = None,
        publish_marker: bool = True,
    ) -> "LocalStore":
        root = Path(root)
        layout = StoreLayout(root)
        if layout.project_yaml.exists():
            raise StoreError(
                f"a Redthread store already exists at {root} — open it instead of "
                "re-initializing (the store_init tool does this for you)"
            )
        cls._write_initial_files(layout, project_id, phases, name)
        if not (root / ".git").exists():
            # Pin the branch name explicitly: relying on the ambient
            # init.defaultBranch config would make store repos diverge
            # (main vs master) depending on which machine created them.
            with contextlib.suppress(OSError, subprocess.CalledProcessError):
                subprocess.run(
                    ["git", "init", "-q", "-b", "main"], cwd=root, check=True, capture_output=True
                )
        store = cls(root)
        if host_repo is not None:
            cls._write_host_marker(host_repo, mode="repo", store_path=root)
            if publish_marker:
                store.marker_status = _publish_host_marker(host_repo, root)
        return store

    @classmethod
    def init_worktree(
        cls,
        host_repo: Path,
        worktree_path: Path,
        branch: str,
        project_id: str,
        phases: list[str],
        name: str | None = None,
        publish_marker: bool = True,
    ) -> "LocalStore":
        """Create a store as an orphan-branch git worktree of `host_repo`,
        so the host repo's currently checked-out branch is never touched —
        the same portability as `init`, without needing a separate repo.

        `host_repo` is `git init`-ed if it isn't a repo yet, so this works on
        a project started five minutes ago. Unless `publish_marker` is False,
        the store directory is added to the host repo's `.gitignore` and the
        `.redthread.yaml` marker is committed to its current branch — that
        commit is what lets the next clone find the store, and it touches
        those two paths only.
        """
        host_repo = Path(host_repo)
        worktree_path = Path(worktree_path)
        layout = StoreLayout(worktree_path)
        if layout.project_yaml.exists():
            raise StoreError(f"a Redthread store already exists at {worktree_path}")
        gitio.ensure_repo(host_repo)
        gitio.ensure_worktree(host_repo, worktree_path, branch)
        if layout.project_yaml.exists():
            raise StoreError(
                f"branch {branch!r} in {host_repo} already holds a store "
                f"({worktree_path}); open it with LocalStore(...) instead"
            )
        cls._write_initial_files(layout, project_id, phases, name)
        cls._write_host_marker(host_repo, mode="worktree", store_path=worktree_path, branch=branch)
        store = cls(worktree_path)
        if publish_marker:
            store.marker_status = _publish_host_marker(host_repo, worktree_path)
        return store

    @staticmethod
    def _write_host_marker(
        host_repo: Path,
        mode: str,
        store_path: Path,
        branch: str | None = None,
    ) -> None:
        """Record how this store attaches in `<host_repo>/.redthread.yaml`,
        so a fresh clone of the host repo (or an MCP server launched from
        it) can find the store without a human remembering flags."""
        # Deferred: redthread.hostconfig imports redthread.store.gitio, and
        # importing anything under redthread.store first runs this package's
        # own __init__ (which imports this module) — a module-level import
        # here would be circular.
        from redthread.hostconfig import HostConfig, StoreRef, write_host_config

        host_repo = Path(host_repo)
        try:
            rel_path = Path(store_path).resolve().relative_to(host_repo.resolve())
        except ValueError:
            rel_path = Path(store_path).resolve()
        write_host_config(
            host_repo,
            HostConfig(store=StoreRef(mode=mode, path=str(rel_path), branch=branch)),
        )

    @staticmethod
    def _write_initial_files(
        layout: StoreLayout, project_id: str, phases: list[str], name: str | None
    ) -> None:
        manifest = ProjectManifest(project_id=project_id, name=name, phases=phases)
        _dump_yaml(layout.project_yaml, manifest)
        _write_text(layout.gitattributes, _GITATTRIBUTES)
        layout.runs_dir.mkdir(parents=True, exist_ok=True)
        (layout.root / "memory").mkdir(exist_ok=True)

    def start_run(self, parent_run_id: str | None = None) -> RunRecord:
        run_id = new_ulid()
        now = datetime.now(UTC)
        record = RunRecord(
            run_id=run_id,
            status="active",
            parent_run_id=parent_run_id,
            phases={phase: "pending" for phase in self.manifest.phases},
            nodes=[NodeStint(node_id=get_node_id(), host=socket.gethostname(), joined=now)],
            created_ts=now,
        )
        for phase in self.manifest.phases:
            self.layout.entries_dir(run_id, phase).mkdir(parents=True, exist_ok=True)
            self.layout.artifacts_dir(run_id, phase).mkdir(parents=True, exist_ok=True)
        _dump_yaml(self.layout.run_yaml(run_id), record)
        index = ArtifactIndex(run_id=run_id)
        _write_text(self.layout.artifacts_index(run_id), index.model_dump_json(indent=2))
        return record

    def get_run(self, run_id: str) -> RunRecord:
        path = self.layout.run_yaml(run_id)
        if not path.exists():
            raise StoreError(
                f"unknown run {run_id!r} in this store — run_list shows every run_id, "
                "run_start creates a new one, or omit run_id to use the newest active run"
            )
        return RunRecord.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def save_run(self, record: RunRecord) -> None:
        _dump_yaml(self.layout.run_yaml(record.run_id), record)

    def list_runs(self) -> list[str]:
        if not self.layout.runs_dir.exists():
            return []
        return sorted(p.name for p in self.layout.runs_dir.iterdir() if p.is_dir())

    def current_run_id(self) -> str | None:
        """The newest run still marked ``active``, or None if there is none.

        Lets callers omit ``run_id`` in the overwhelmingly common case of one
        run in flight, without giving up the explicit id that makes
        concurrent runs across nodes unambiguous. Run ids are ULIDs, so
        ``list_runs`` is already in creation order.
        """
        for run_id in reversed(self.list_runs()):
            try:
                record = self.get_run(run_id)
            except StoreError:
                continue  # a half-written run dir shouldn't hide older valid ones
            if record.status == "active":
                return run_id
        return None

    def add_phase(self, phase: str, *, backfill_open_runs: bool = True) -> ProjectManifest:
        """Append a new phase to the project's declared pipeline.

        Runs already have their own phase-status snapshot in ``run.yaml``
        taken at ``start_run`` time, so a new phase doesn't automatically
        appear there. By default this backfills every run that isn't
        already ``done``/``failed`` with the new phase as ``pending``, so
        mid-flight runs can immediately log against it. Completed runs are
        left untouched — their status dict is a historical record.
        """
        if phase in self.manifest.phases:
            raise StoreError(
                f"phase {phase!r} is already in this project's pipeline "
                f"{self.manifest.phases} — nothing to add"
            )
        updated = ProjectManifest(
            project_id=self.manifest.project_id,
            name=self.manifest.name,
            phases=[*self.manifest.phases, phase],
            created_ts=self.manifest.created_ts,
        )
        _dump_yaml(self.layout.project_yaml, updated)
        self.manifest = updated
        if backfill_open_runs:
            for run_id in self.list_runs():
                record = self.get_run(run_id)
                if record.status in ("done", "failed") or phase in record.phases:
                    continue
                record.phases[phase] = "pending"
                self.save_run(record)
                self.layout.entries_dir(run_id, phase).mkdir(parents=True, exist_ok=True)
                self.layout.artifacts_dir(run_id, phase).mkdir(parents=True, exist_ok=True)
        return updated

    def _check_phase(self, phase: str) -> None:
        if phase not in self.manifest.phases:
            raise StoreError(
                f"phase {phase!r} is not in this project's pipeline {self.manifest.phases} "
                "— use one of those, or extend the pipeline with `redthread project "
                "add-phase`"
            )

    # ---- entries ---------------------------------------------------------

    def log(
        self,
        run_id: str,
        phase: str,
        type: str,
        payload: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        links: list[str] | None = None,
        agent: str | None = None,
        project_git_sha: str | None = None,
    ) -> ContextEntry:
        self._check_phase(phase)
        self.get_run(run_id)
        entry = ContextEntry(
            entry_id=new_ulid(),
            run_id=run_id,
            phase=phase,
            type=type,
            provenance=Provenance(
                node_id=get_node_id(),
                host=socket.gethostname(),
                agent=agent,
                project_git_sha=project_git_sha,
            ),
            payload=payload or {},
            tags=tags or [],
            links=links or [],
        )
        entries_dir = self.layout.entries_dir(run_id, phase)
        entries_dir.mkdir(parents=True, exist_ok=True)
        seq = sum(1 for p in entries_dir.glob("*.json")) + 1
        entry_path = entries_dir / f"{seq:04d}-{entry.entry_id}.json"
        _write_text(entry_path, entry.model_dump_json(indent=2))
        return entry

    def read_entries(
        self,
        run_id: str,
        phase: str | None = None,
        type: str | None = None,
        tags: list[str] | None = None,
    ) -> list[ContextEntry]:
        self.get_run(run_id)
        phases = [phase] if phase else self.manifest.phases
        entries: list[ContextEntry] = []
        for ph in phases:
            entries_dir = self.layout.entries_dir(run_id, ph)
            if not entries_dir.exists():
                continue
            for path in entries_dir.glob("*.json"):
                entry = ContextEntry.model_validate_json(path.read_text(encoding="utf-8"))
                if type and entry.type != type:
                    continue
                if tags and not set(tags).issubset(entry.tags):
                    continue
                entries.append(entry)
        return sorted(entries, key=lambda e: e.entry_id)  # ULIDs sort by creation time

    # ---- summary ---------------------------------------------------------

    def set_summary(self, run_id: str, phase: str, markdown: str) -> None:
        self._check_phase(phase)
        self.get_run(run_id)
        _write_text(self.layout.summary_md(run_id, phase), markdown)

    def get_summary(self, run_id: str, phase: str) -> str | None:
        path = self.layout.summary_md(run_id, phase)
        return path.read_text(encoding="utf-8") if path.exists() else None

    # ---- long-term agent memory (not run-scoped) --------------------------

    def memory_write(
        self,
        namespace: str,
        key: str,
        content: str,
        description: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        text = memory_doc.with_frontmatter(content, description=description, tags=tags)
        _write_text(self.layout.memory_file(namespace, key), text)

    def memory_read(self, namespace: str, key: str) -> str | None:
        path = self.layout.memory_file(namespace, key)
        return path.read_text(encoding="utf-8") if path.exists() else None

    def memory_list(self, namespace: str) -> list[str]:
        base = self.layout.memory_dir(namespace)
        if not base.exists():
            return []
        return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())

    def memory_namespaces(self) -> list[str]:
        base = self.layout.root / "memory"
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir())

    def memory_index(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """Every memory entry with a one-line description, so a caller can
        tell what's worth reading without opening each file. Spans every
        namespace unless one is named."""
        namespaces = [namespace] if namespace else self.memory_namespaces()
        index: list[dict[str, Any]] = []
        for ns in namespaces:
            base = self.layout.memory_dir(ns)
            if not base.exists():
                continue
            for path in sorted(p for p in base.rglob("*") if p.is_file()):
                text = self._read_memory_text(path)
                index.append(
                    {
                        "namespace": ns,
                        "key": path.relative_to(base).as_posix(),
                        "description": memory_doc.describe(text),
                        "tags": memory_doc.tags_of(text),
                        "size_bytes": path.stat().st_size,
                    }
                )
        return index

    def memory_search(
        self, query: str, namespace: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Case-insensitive substring search over memory keys, descriptions,
        tags, and bodies. Each hit carries the line that matched, so a caller
        can judge relevance before spending a `memory_read` on it."""
        needle = query.strip().lower()
        if not needle:
            return []
        hits: list[dict[str, Any]] = []
        for item in self.memory_index(namespace):
            path = self.layout.memory_file(item["namespace"], item["key"])
            text = self._read_memory_text(path)
            haystacks = (item["key"], item["description"] or "", " ".join(item["tags"]))
            in_meta = any(needle in h.lower() for h in haystacks)
            # Match against the body only: the frontmatter's own
            # `description:`/`tags:` lines are already reported as fields, so
            # echoing them back as "the line that matched" is noise.
            _, body = memory_doc.split(text)
            match_line = next(
                (line.strip() for line in body.splitlines() if needle in line.lower()), None
            )
            if not in_meta and match_line is None:
                continue
            hits.append({**item, "match": match_line})
            if len(hits) >= limit:
                break
        return hits

    @staticmethod
    def _read_memory_text(path: Path) -> str:
        # Memory entries are written as UTF-8, but a store is a git repo that
        # humans edit too; a stray non-UTF-8 byte should degrade one
        # description, not break listing the whole namespace.
        return path.read_text(encoding="utf-8", errors="replace")

    # ---- handoff ---------------------------------------------------------

    def publish_handoff(self, handoff: Handoff) -> None:
        self._check_phase(handoff.from_phase)
        self.get_run(handoff.run_id)
        path = self.layout.handoff_json(handoff.run_id, handoff.from_phase)
        _write_text(path, handoff.model_dump_json(indent=2))

    def get_handoff(self, run_id: str, phase: str) -> Handoff:
        self._check_phase(phase)
        path = self.layout.handoff_json(run_id, phase)
        if not path.exists():
            raise StoreError(
                f"phase {phase!r} of run {run_id} has not published a handoff yet — read "
                "its rolling summary with summary_get, or the raw log with context_read"
            )
        return Handoff.model_validate_json(path.read_text(encoding="utf-8"))

    # ---- artifacts ----------------------------------------------------------

    def add_artifact(
        self,
        run_id: str,
        phase: str,
        source: Path,
        kind: str,
        artifact_id: str | None = None,
    ) -> Artifact:
        """Register a small file as an inline artifact: copy it into the store,
        content-address it, and index the pointer. For large files, use
        `add_blob_artifact` instead so bytes don't bloat the git-tracked store."""
        self._check_phase(phase)
        self.get_run(run_id)
        source = Path(source)
        if not source.is_file():
            raise StoreError(
                f"artifact source {source} is not a file — pass a path to an existing "
                "file (directories are not supported; archive them first)"
            )
        artifact_id = artifact_id or source.stem
        dest = self.layout.artifacts_dir(run_id, phase) / (artifact_id + source.suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        artifact = Artifact(
            artifact_id=artifact_id,
            kind=kind,
            sha256=sha256_file(dest),
            size_bytes=dest.stat().st_size,
            backend="inline",
            uri=self.layout.relative_uri(dest),
            produced_by_phase=phase,
        )
        index = self.get_artifact_index(run_id)
        if artifact.artifact_id in index.artifacts:
            raise StoreError(
                f"artifact id {artifact.artifact_id!r} already exists in run {run_id} — "
                "artifacts are immutable; pass a different artifact_id"
            )
        index.artifacts[artifact.artifact_id] = artifact
        _write_text(self.layout.artifacts_index(run_id), index.model_dump_json(indent=2))
        self.log(
            run_id,
            phase,
            "artifact_ref",
            payload={"artifact_id": artifact.artifact_id, "kind": kind, "sha256": artifact.sha256},
        )
        return artifact

    def get_artifact_index(self, run_id: str) -> ArtifactIndex:
        path = self.layout.artifacts_index(run_id)
        if not path.exists():
            raise StoreError(
                f"unknown run {run_id!r} — run_list shows every run_id (a run created "
                "before this store tracked artifacts has no index yet)"
            )
        return ArtifactIndex.model_validate_json(path.read_text(encoding="utf-8"))

    def add_blob_artifact(
        self,
        run_id: str,
        phase: str,
        source: Path,
        kind: str,
        backend_name: str,
        backend: BlobBackend,
        artifact_id: str | None = None,
    ) -> Artifact:
        """Register a large artifact via a content-addressed blob backend.

        Only the pointer is committed to the store repo; the bytes live in
        `backend`, resolved by every node from `backend_name` through its own
        local paths.map (see `redthread.paths`) — never an absolute path.
        """
        self._check_phase(phase)
        self.get_run(run_id)
        source = Path(source)
        if not source.is_file():
            raise StoreError(
                f"artifact source {source} is not a file — pass a path to an existing "
                "file (directories are not supported; archive them first)"
            )
        artifact_id = artifact_id or source.stem
        index = self.get_artifact_index(run_id)
        if artifact_id in index.artifacts:
            raise StoreError(
                f"artifact id {artifact_id!r} already exists in run {run_id} — "
                "artifacts are immutable; pass a different artifact_id"
            )
        digest = backend.put(source)
        artifact = Artifact(
            artifact_id=artifact_id,
            kind=kind,
            sha256=digest,
            size_bytes=source.stat().st_size,
            backend="rsync",
            uri=f"rsync://{backend_name}/{digest}",
            produced_by_phase=phase,
        )
        index.artifacts[artifact.artifact_id] = artifact
        _write_text(self.layout.artifacts_index(run_id), index.model_dump_json(indent=2))
        self.log(
            run_id,
            phase,
            "artifact_ref",
            payload={"artifact_id": artifact.artifact_id, "kind": kind, "sha256": digest},
        )
        return artifact

    def resolve_artifact(
        self,
        run_id: str,
        artifact_id: str,
        backends: dict[str, BlobBackend] | None = None,
        dest: Path | None = None,
    ) -> tuple[Artifact, Path]:
        """Return the pointer and a verified local path for any artifact.

        Inline artifacts resolve from within the store repo. Blob-backed
        artifacts require `backends`, a mapping from the logical backend name
        (the authority in the artifact's `rsync://<name>/<sha256>` uri) to an
        already-opened `BlobBackend` for this machine.
        """
        index = self.get_artifact_index(run_id)
        if artifact_id not in index.artifacts:
            known = ", ".join(sorted(index.artifacts)) or "none registered yet"
            raise StoreError(
                f"unknown artifact {artifact_id!r} in run {run_id} — known ids: {known}"
            )
        artifact = index.artifacts[artifact_id]
        if artifact.backend == "inline":
            path = self.layout.root / Path(*artifact.uri.split("/"))
            if not path.exists():
                raise StoreError(
                    f"inline artifact missing from store: {artifact.uri} — the pointer is "
                    "committed but the bytes aren't here; `redthread sync` pulls whatever "
                    "another machine has already pushed"
                )
            if sha256_file(path) != artifact.sha256:
                raise StoreError(
                    f"artifact {artifact_id!r} failed sha256 verification — the file in the "
                    "store no longer matches its recorded digest; do not trust it, and "
                    "re-register it from a known-good source"
                )
            return artifact, path

        backend_name = artifact.uri.split("://", 1)[1].split("/", 1)[0]
        if not backends or backend_name not in backends:
            raise StoreError(
                f"artifact {artifact_id!r} needs backend {backend_name!r}; "
                "configure it with `redthread backend set` and pass it to resolve_artifact"
            )
        dest = dest or (self.layout.root / ".cache" / artifact.sha256)
        path = backends[backend_name].get(artifact.sha256, dest)
        return artifact, path
