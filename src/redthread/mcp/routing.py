"""Which store does this tool call belong to?

A stdio MCP server is launched once with one ``--store`` and serves it for
its whole life. That is exactly right for a client that registers servers
per project (Claude Code's ``.mcp.json``), and exactly wrong for one that
keeps a single global registration and reuses it for every window it opens
(Cursor, Windsurf, VS Code): every repo then talks to the first repo's
store, and ``hostconfig.check_binding`` can only report the damage after
the fact.

Discovery mode fixes that by deciding the store per call instead of per
process: a workspace directory comes in (from the tool argument, the
client's declared roots, ``REDTHREAD_WORKSPACE``, or the launch cwd), the
nearest ancestor holding a ``.redthread.yaml`` marker is the workspace
root, and the store that marker names is the one served. One global
registration, the right store in every repo.
"""

import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from redthread import constants, hostconfig
from redthread.store import LocalStore
from redthread.store.errors import StoreError


@dataclass(frozen=True)
class ResolvedStore:
    """The store a call resolved to, and the workspace it was resolved for."""

    store: LocalStore
    workspace: Path


class WorkspaceLocator:
    """Finds the workspace root that declares a store: the nearest ancestor
    of a starting directory (itself included) holding a marker file.

    Walking up matters because the directory an agent reports is often a
    subdirectory of the repo — the file it happens to be editing, or a
    package inside a monorepo — while the marker is committed at the root.
    """

    def __init__(self, marker_filename: str = constants.MARKER_FILENAME) -> None:
        self._marker_filename = marker_filename

    def locate(self, start: Path) -> Path | None:
        """The nearest ancestor of ``start`` holding the marker, or None."""
        start = Path(start).resolve()
        for candidate in (start, *start.parents):
            if (candidate / self._marker_filename).exists():
                return candidate
        return None


class StoreRouter:
    """Resolves and opens the store for a workspace, once per store.

    Two modes, decided at construction:

    - **pinned** (``fixed_store`` given) — every call gets that one store,
      the historical single-``--store`` behaviour. The workspace still
      travels with the result so bootstrap can check the binding.
    - **discovery** (``fixed_store`` is None) — the store comes from the
      workspace's marker, so one registration serves every repo.

    The workspace of the first explicitly addressed call sticks, so tools
    that take no workspace argument keep resolving to the same store for
    the rest of the session.
    """

    def __init__(
        self,
        fixed_store: Path | None = None,
        default_workspace: Path | None = None,
        allow_clone: bool = False,
        locator: WorkspaceLocator | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        self._fixed_store = Path(fixed_store) if fixed_store else None
        self._default_workspace = Path(default_workspace) if default_workspace else Path.cwd()
        self._allow_clone = allow_clone
        self._locator = locator or WorkspaceLocator()
        self._environ = environ if environ is not None else dict(os.environ)
        self._bound_workspace: Path | None = None
        self._open_stores: dict[Path, LocalStore] = {}

    @property
    def discovering(self) -> bool:
        """True when the store is chosen per workspace rather than pinned."""
        return self._fixed_store is None

    def locate(
        self, workspace: str | Path | None = None, *, bind: bool = False
    ) -> tuple[Path, Path]:
        """The workspace root and store path a call applies to, without
        opening (or requiring) the store — what ``store_init`` needs.

        Raises StoreError if discovery mode can find no marker: refusing to
        serve is the point, since the alternative is writing this project's
        memory into whichever store the server happened to start with.
        """
        hint = self._workspace_hint(workspace)
        if self._fixed_store is not None:
            root, store_path = hint, self._fixed_store.resolve()
        else:
            located = self._locator.locate(hint)
            config = hostconfig.read_host_config(located) if located else None
            if located is None or config is None:
                raise StoreError(self._no_marker_message(hint))
            root, store_path = located, (located / config.store.path).resolve()
        if bind:
            self._bound_workspace = root
        return root, store_path

    def resolve(self, workspace: str | Path | None = None, *, bind: bool = False) -> ResolvedStore:
        """Open the store for ``workspace`` (or the current best guess)."""
        root, store_path = self.locate(workspace, bind=bind)
        return ResolvedStore(self._open(root, store_path), root)

    def store_path_for(self, workspace: str | Path | None = None) -> Path:
        """Where this workspace's store lives, whether or not it exists."""
        return self.locate(workspace)[1]

    def ensure_attached(self, workspace: str | Path | None = None) -> tuple[Path, Path]:
        """Locate this workspace's store and materialize it from the marker
        if another machine already created it. Returns the workspace root and
        the store path, which may still not exist — that is the genuinely
        new project that `store_init` goes on to create."""
        root, store_path = self.locate(workspace)
        self._attach_if_needed(root, store_path)
        return root, store_path

    def workspace_for(self, workspace: str | Path | None = None) -> Path:
        """The project directory this call applies to."""
        return self.locate(workspace)[0]

    def forget(self, store_path: Path) -> None:
        """Drop a cached store, so the next call re-reads its manifest."""
        self._open_stores.pop(Path(store_path).resolve(), None)

    # ---- internals -------------------------------------------------------

    def _workspace_hint(self, workspace: str | Path | None) -> Path:
        """Where to start looking: the caller's answer, else the last one
        that stuck, else the environment, else where the server was
        launched."""
        if workspace:
            return Path(workspace).expanduser().resolve()
        if self._bound_workspace is not None:
            return self._bound_workspace
        from_env = self._environ.get(constants.WORKSPACE_ENV_VAR)
        if from_env:
            return Path(from_env).expanduser().resolve()
        return self._default_workspace.resolve()

    def _open(self, workspace: Path, store_path: Path) -> LocalStore:
        store_path = Path(store_path).resolve()
        cached = self._open_stores.get(store_path)
        if cached is not None:
            return cached
        self._attach_if_needed(workspace, store_path)
        store = LocalStore(store_path)
        self._open_stores[store_path] = store
        return store

    def _attach_if_needed(self, workspace: Path, store_path: Path) -> None:
        # A marker but no store yet means another machine already set this
        # project up — attach automatically instead of erroring. No marker
        # at all is a genuinely fresh project; store_init creates one.
        if (store_path / constants.PROJECT_FILENAME).exists():
            return
        if hostconfig.read_host_config(workspace):
            hostconfig.attach(workspace, store_path, allow_clone=self._allow_clone)

    def _no_marker_message(self, hint: Path) -> str:
        return (
            f"no {constants.MARKER_FILENAME} found in {hint} or any parent directory, so this "
            f"workspace does not declare a Redthread store. This server is running in "
            f"discovery mode (no --store), which means it serves each project the store its "
            f"own marker names, and refuses rather than guess. Tell the user to run one of:\n"
            f"  redthread init <project-id> --phases <a,b,c> --worktree-repo . "
            f"--store ./{constants.DEFAULT_STORE_DIRNAME}   # new store for this repo\n"
            f"  redthread attach --store <path-to-existing-store> --host-repo .            "
            f"   # store already exists\n"
            f"Both write and commit {constants.MARKER_FILENAME}, after which this server "
            f"finds the store on its own. If the agent's working directory is not the repo "
            f"root, pass the repo root as the `workspace` argument instead."
        )


class ClientRootsProbe:
    """Asks the MCP client which directories are open, when it will say.

    The roots capability is the protocol's own answer to "which project is
    this?", so it is tried before falling back to environment or cwd
    guesses. Clients that don't implement it simply error the request, which
    is not a failure worth surfacing — it just means the next fallback wins.
    """

    def __init__(self, locator: WorkspaceLocator | None = None) -> None:
        self._locator = locator or WorkspaceLocator()

    async def probe(self, session: object) -> Path | None:
        """The best workspace the client's roots offer, or None."""
        try:
            result = await session.list_roots()  # type: ignore[attr-defined]
            roots = list(result.roots)
        except Exception:  # noqa: BLE001 - any client that won't answer is a no-op here
            return None
        return self.choose(self._to_paths(roots))

    def choose(self, candidates: list[Path]) -> Path | None:
        """Prefer a root that actually declares a store; else the first one."""
        for candidate in candidates:
            if self._locator.locate(candidate) is not None:
                return candidate
        return candidates[0] if candidates else None

    @staticmethod
    def _to_paths(roots: list[object]) -> list[Path]:
        paths: list[Path] = []
        for root in roots:
            uri = str(getattr(root, "uri", "") or "")
            if not uri.startswith("file:"):
                continue
            parsed = urlparse(uri)
            with suppress(ValueError, OSError):
                paths.append(Path(url2pathname(unquote(parsed.path))))
        return paths
