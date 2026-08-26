# Changelog

All notable changes to this project are documented in this file.

## [0.12] - 2026-08-26

### Added

- **Discovery mode: one MCP registration, the right store in every repo.**
  `redthread mcp-serve` with no `--store` now resolves the store per call
  instead of pinning one for the life of the process. Each call walks up
  from its workspace to the nearest committed `.redthread.yaml` and serves
  the store that marker names. This is the fix for clients that keep a
  single global MCP registration and reuse it for every project window
  (Cursor's `~/.cursor/mcp.json`, Windsurf, VS Code's user-level
  `mcp.json`), where one `--store` meant every repo wrote into the first
  repo's store.

  The workspace comes from the first source that answers: the new
  `workspace` argument on `context_bootstrap` (also on `store_init`,
  `memory_write`, and `agents_md_bootstrap`), which sticks for the rest of
  the session; the client's declared MCP roots, asked for automatically;
  the `REDTHREAD_WORKSPACE` environment variable; or the launch directory.
  A workspace with no marker is refused, naming the `redthread init` /
  `redthread attach` command that fixes it — never silently served another
  project's store.

- **`agents_md_bootstrap` now tells agents to pass `workspace`** on their
  first `context_bootstrap` call, so a globally-registered server lands on
  the right store without the user configuring anything per project.

### Changed

- `--store` is now optional on `mcp-serve`. Passing it keeps the previous
  behaviour exactly, including the `store.binding` mismatch warning.

## [0.11] - 2026-08-25

### Fixed

- **A broken presentation stack no longer takes down the whole CLI.** The
  CLI imported the `present` adapter (→ `python-pptx` → `lxml`, a native
  DLL) at module import time, so an environment where that DLL cannot load
  (observed: Windows Application Control blocking a freshly-installed
  `lxml`) crashed *every* command — `mcp-serve` included. The import now
  happens inside the `present` command, the only place that needs it.

### Changed

- **`memory_write` no longer blocks on the network.** The MCP tools
  `memory_write` and `memory_import` used to run the full
  commit → pull --rebase → push sequence synchronously inside the tool
  call, so every write paid two network round trips while an agent (and a
  human) waited — long enough on a slow link that users interrupted it.
  The commit stays synchronous (it is what makes the write durable, and a
  durability failure is still reported immediately); the pull+push now
  runs on a per-store background worker (`redthread.sync.background`),
  and the tool returns at local-disk speed with `sync.status: "pushing"`.
  - At most one push per store is in flight; commits that land mid-push
    set a rerun flag on the same worker, so bursts of writes coalesce and
    nothing committed after a push started is left behind.
  - A failed background push is not swallowed: the next `memory_write` on
    the store attaches it under `sync.previous` and calls it out in
    `_next`, and the new `sync_status` MCP tool reports in-flight state,
    the last push outcome, and the count of unpublished commits on demand.
  - Process exit drains in-flight pushes for up to
    `BACKGROUND_SYNC_DRAIN_SECONDS` (30s); a push cut off by a hard kill
    costs nothing but latency, since the commit is local and any later
    sync republishes it.
  - Stores without a remote keep the old fully-synchronous (and fully
    local) `committed` report; the `redthread` CLI and the auto-commit
    daemon are unchanged.

## [0.10] - 2026-08-17

### Fixed

- **Git operations can no longer hang waiting for a human.** Every git
  invocation in the package funnels through `store.gitio._run`, which ran
  `subprocess.run` with no timeout, with stdout and stderr on pipes, and
  with the parent's stdin inherited. When git decided to ask for
  credentials it blocked forever on a prompt nobody could see — a single
  `memory_write` blocked a session for ~30 minutes with no output and no
  error, even though the commit had already been made and pushed. `_run`
  now:
  - redirects stdin to `DEVNULL`;
  - sets `GIT_TERMINAL_PROMPT=0` and `GCM_INTERACTIVE=never` over a copy of
    the environment, so a GUI credential helper cannot open a dialog that
    sits unnoticed behind another window;
  - carries a `GIT_TIMEOUT_SECONDS = 60` budget (`clone` is the documented
    exception, below);
  - converts `subprocess.TimeoutExpired` into `GitError` *regardless of the
    `check` argument*, since `push` and `pull_rebase` pass `check=False`
    and would otherwise swallow the stall silently.

  This is what makes `sync_report`'s existing design hold: a stalled push is
  now reported as `{"status": "failed"}` with the entry safely committed on
  disk, instead of never returning. It also stops `sync`'s 5-attempt retry
  loop from multiplying one stall across ten blocking network calls.

  Trade-off: first-time authentication no longer prompts. A machine with no
  stored credentials must run `git push` once by hand to establish them —
  the right trade for a tool that runs headless inside an MCP server.

- **A timed-out git call now kills its transport helper too.** Terminating
  the `git` process alone left `git-remote-https` — a child, not the process
  we hold a handle to — running with the connection and its file handles
  into the repo still open. `_run` tears down the whole process tree
  (`taskkill /T` on Windows, `killpg` on POSIX, where git is now started in
  its own process group).

- **`clone` no longer has a wall-clock timeout, and reports progress
  instead.** A 600s cap punished the honest case — a large store is
  legitimately slow to clone — while silence made a slow clone
  indistinguishable from a hang. Clone now runs unbounded in elapsed time
  and reports every `CLONE_PROGRESS_INTERVAL_SECONDS` (5s), passing either
  git's own newest progress line or a bare "still running" plus elapsed
  time. What bounds it instead is git's own throughput floor: the clone runs
  under `http.lowSpeedLimit`/`http.lowSpeedTime`, so a transfer that has
  effectively stopped still aborts rather than hanging forever. `clone`,
  `resume`, and `hostconfig.attach` take an `on_progress` callback; the CLI
  prints it to stderr, keeping machine-readable stdout clean.

- **A failed clone cleans up after itself and says what to do next.** Git
  creates the destination and starts filling it immediately, so a clone that
  died partway left a directory that was neither absent nor usable: the
  obvious retry hit "destination path already exists and is not an empty
  directory", and `hostconfig.attach` — which probes for the path — mistook
  the wreckage for a real store. The partial directory is now removed (never
  a directory that already existed), and the `GitError` names the manual
  `git clone` command, since the usual cause is a credential prompt this
  module deliberately refuses to show.

### Added

- **`redthread mcp` checks PyPI for a newer release.** The MCP server is
  long-lived and launched by an agent client, so its user never sees a
  release note — which is how a machine ends up two versions behind without
  anyone noticing. When a newer version is published, the notice arrives
  both on the server's stderr at startup and as an `update_available` field
  on `context_bootstrap`, the latter being what actually reaches the user
  via the agent. It names the upgrade command
  (`uv pip install --upgrade redthread`, `pip install --upgrade redthread`,
  or `uv tool install --reinstall redthread`).

  Best-effort by construction: a 3s timeout, throttled to once a day, and
  every failure path — no network, PyPI down, malformed response, corrupt
  cache, unparseable version — resolves to no message rather than an error.
  Versions compare numerically, so `0.9.0` correctly reads as older than
  `0.10.0`. Set `REDTHREAD_NO_UPDATE_CHECK=1` to disable it entirely; the
  test suite does, so no test reaches the network.

### Changed

- **Every tunable default now lives in `redthread.constants`.** Timeouts,
  retry budgets, poll intervals, batch sizes, well-known filenames, and the
  domain vocabularies (`RUN_STATUSES`, `ENTRY_TYPES`, `ARTIFACT_BACKENDS`,
  `TEXT_SUFFIXES`) were literals scattered across a dozen modules, so
  changing one meant knowing which file it happened to live in. Modules now
  import from `constants`; a few re-export under their existing names, so
  `gitio.DEFAULT_TIMEOUT_SECONDS` and `hostconfig.MARKER_FILENAME` keep
  working.

## [0.9] - 2026-08-06

### Added

- **Wrong-store detection.** `context_bootstrap` now checks the store it is
  serving against the workspace it was launched for and reports the result
  as `store.binding`: `ok`, `unverified` (nothing ties the store to this
  workspace), or `mismatch` (this repo's `.redthread.yaml` names a
  different store). Anything but `ok` adds a `warning` field and replaces
  `_next` with a stop instruction. MCP clients that register a server once
  and reuse that registration for every workspace (Cursor, Windsurf, VS
  Code) otherwise serve the same store to every project an agent opens —
  and nothing in a store's contents reveals that it belongs to a different
  project, so an agent reads a real pipeline and a populated memory index
  and files this project's work into another project's history.
  - `redthread.hostconfig.check_binding(host_repo, store_path)` exposes the
    same check as a pure function.
  - `memory_write` returns the `project_id` it actually wrote to, so a
    session that skipped `context_bootstrap` still has a signal.
  - The MCP server instructions and the `context_bootstrap`/`memory_write`
    tool descriptions tell the agent to check `store.binding` before
    writing anything.
  - `agents_md_bootstrap` pins the expected `project_id` into the
    `AGENTS.md`/`CLAUDE.md` policy it writes. That file travels with the
    repo, so the check still works when the MCP server is registered
    globally and points somewhere else entirely.
- `redthread --version` (`-V`) prints the installed version.

## [0.8] - 2026-08-02

### Added

- **Port existing memory into a store.** New `memory_import` MCP tool and
  `redthread memory import <path>` command: point it at a file or a
  directory and each text file becomes one memory entry, keyed by its path
  under the source with the extension dropped, so nesting like
  `decisions/db.md` survives as `decisions/db`. Most projects meet
  Redthread with memory already written somewhere else — a harness's own
  memory directory (`~/.claude/projects/**/memory/`), a notes folder,
  another store's `memory/` tree — and asking people to re-type it by hand
  is how it stays where it is.
  - Entries are copied verbatim, so frontmatter the source already had
    (`description`, `tags`) keeps working in `memory_list` and
    `memory_search` with no conversion step.
  - It is a copy, never a move: source files are left untouched.
  - Existing keys are skipped rather than clobbered unless
    `overwrite=True` (`--overwrite`), and a key whose content already
    matches is skipped either way — re-running an import is cheap and
    non-destructive.
  - Unreadable or non-UTF-8 files are reported per-file in `failed`
    instead of aborting the batch, and the whole import commits and pushes
    in one commit rather than one per entry.
  - `--namespace` (default `imported`), `--tags`, `--recursive/--no-recursive`,
    and `--no-push` are available on both the tool and the CLI.
- `redthread.memory_port` — `discover` and `key_for` as pure path-walking
  and key-derivation functions, independent of any store. Hidden files and
  directories are skipped (a `.git` inside a notes folder is not memory),
  and a segment that reduces to nothing is dropped rather than emitted as a
  traversal.

## [0.7] - 2026-07-30

### Changed

- **Writing memory now publishes it.** `memory_write` (MCP tool and
  `redthread memory write`) commits and pushes the store by default,
  instead of leaving the entry uncommitted and telling the caller to run
  `redthread sync` — an agent that has to remember a second call sometimes
  won't, and unpushed memory is invisible to the next machine. The tool
  result gains a `sync` field (`pushed`, `committed`, `no_changes`, or
  `failed` with a `detail`); a failed push is reported there rather than
  raised, since the entry is already on disk. Pass `push=False`
  (`--no-push` on the CLI) to batch several writes and sync once.
- **`redthread init --worktree-repo` now finishes the setup.** It `git
  init`s the host repo if it isn't one yet, adds the store directory to the
  host repo's `.gitignore`, and commits `.redthread.yaml` to the branch
  you're on — the three manual steps the docs used to list after `init`. A
  brand-new project directory becomes a Redthread host in one command, and
  the marker is committed, which is the only state in which it can do its
  job of telling the *next* clone where the store is. The commit is a
  pathspec commit touching those two files only, so anything else you had
  staged is left alone; pass `--no-commit-marker` to opt out. A commit that
  fails (no git identity, say) is a warning, not a failed init.
- `agents_md_bootstrap`, the MCP server instructions, and
  `context_bootstrap`'s `_next` now say memory is pushed on write, so
  agents stop being told to sync separately.

### Added

- `gitio.sync_report` — `sync` as a reportable status dict rather than an
  exception, for callers whose own write already succeeded.
- `gitio.is_repo`, `gitio.ensure_repo`, `gitio.commit_paths`, and
  `hostconfig.ensure_ignored`/`hostconfig.publish_marker`.
- `LocalStore.marker_status`, recording what `init`/`init_worktree` did
  with the host repo's marker commit.

## [0.6] - 2026-07-30

### Added

- `context_bootstrap` MCP tool (and `redthread bootstrap` on the CLI) — one
  call returning the project's phase pipeline, recent runs with status,
  published handoffs, and the full memory index, plus a `_next` field
  saying what to do with it. Replaces the `run_list` → `memory_list` →
  `handoff_get` chain a cold agent had to guess its way through, and is now
  the documented first call of every session.
- Self-describing memory: `memory_write` takes `description` and `tags`,
  stored as YAML frontmatter (`redthread.memory_doc`), and `memory_list`
  returns a description per entry instead of bare keys — entries written
  without one fall back to their first meaningful line. New `memory_search`
  tool and `redthread memory search` command cover keys, descriptions,
  tags, and bodies, reporting the line that matched.
- Read-only MCP **resources** mirroring the read tools, for clients that
  can attach context without a tool round-trip: `redthread://project`,
  `redthread://memory`, `redthread://bootstrap`, and templated
  `redthread://memory/{namespace}/{key}`,
  `redthread://handoff/{run_id}/{phase}`,
  `redthread://summary/{run_id}/{phase}`.
- `LocalStore.current_run_id`, `memory_namespaces`, `memory_index`, and
  `memory_search`.

### Changed

- **Breaking (MCP tool surface):** run-scoped tools now take `run_id` last
  and optional. Omitted, it resolves to the store's newest `active` run,
  and the resolved id is echoed in the response — so an agent can't
  silently write to the wrong run. Pass it explicitly when several runs are
  in flight. Tools returning bare scalars now return objects to carry that
  id: `context_log` → `{entry_id, run_id, phase, type}`, `context_read` →
  `{run_id, count, entries}`, `summary_get` → `{run_id, phase, markdown}`,
  `summary_update` → `{run_id, phase, bytes}`.
- **Breaking (MCP tool surface):** `memory_list` returns
  `[{namespace, key, description, tags, size_bytes}]` instead of `[key]`,
  and its `namespace` argument is optional (spans every namespace when
  omitted). `memory_write` returns a result object rather than nothing.
  `LocalStore.memory_list` still returns bare keys; the descriptive form is
  `LocalStore.memory_index`.
- Store errors now name the call that fixes them — a missing store points
  at `store_init`, an unknown run at `run_list`, a phase outside the
  pipeline at `redthread project add-phase`, a missing handoff at
  `summary_get`/`context_read`, and an unknown artifact lists the ids that
  do exist.
- Server `instructions` and the `agents_md_bootstrap` policy now lead with
  `context_bootstrap` and note that subagents don't inherit the main
  agent's instructions, so they need to call it themselves.
- Docs site: Google Analytics, consent-gated so the tag only loads once a
  visitor accepts.

### Fixed

- Pin `mcp>=1.28.1,<2`. The MCP SDK's 2.0 release (implementing spec
  revision `2026-07-28`) removes `mcp.server.fastmcp`, which this server is
  built on, so an unbounded range broke every fresh dependency resolve —
  CI, and `uvx redthread` for anyone installing from PyPI. Verified against
  1.29.0, the newest release the pin allows. Migrating to the 2.0 SDK is
  tracked separately.
- MCP server tests no longer fall back to `Path.cwd()` for `host_repo`,
  which made them attach to the developer's own `.redthread.yaml` store
  instead of the temporary one under test.

## [0.5] - 2026-07-23

### Added

- `.redthread.yaml` — a small, git-committed marker in the host (code)
  repo recording how a project's store attaches (worktree branch, or repo
  URL), so a fresh clone can find it without a human remembering
  `--worktree-repo`/`--branch`/`--remote` flags. Written automatically by
  `redthread init --worktree-repo` (and by plain `redthread init
  --host-repo PATH`).
- `redthread attach [--store PATH] [--host-repo PATH] [--allow-clone]` —
  makes a store exist per its marker: attaches an existing or fresh
  worktree branch, clones a repo-mode store (with `--allow-clone`), or
  syncs a repo-mode marker's `url` from the store's actual remote once
  one has been added.
- `redthread mcp-serve` now reads `.redthread.yaml` (via `--host-repo`,
  defaulting to its working directory) and attaches the store
  automatically the first time a tool needs it — including `store_init`,
  which now returns the existing manifest instead of erroring if another
  machine already populated the store. Worktree mode attaches freely;
  repo mode requires `--allow-clone`, since auto-cloning a URL read from a
  committed file is a real trust boundary. Net effect: a second machine's
  setup is "clone the code repo, register the same MCP command" — no
  flags to remember, no manual `git clone` of the store.
- `redthread.hostconfig` module: `HostConfig`/`StoreRef` models and
  `read_host_config`/`write_host_config`/`attach` — the implementation
  behind all of the above, directly unit-tested.

## [0.4] - 2026-07-23

### Added

- `redthread project add-phase <phase>` (and `LocalStore.add_phase`) —
  extend a project's declared phase pipeline after `init`. By default
  backfills the new phase as `pending` into every run that isn't already
  `done`/`failed`; completed runs keep their original phase-status
  snapshot untouched. `--no-backfill` limits the change to future runs.
- `agents_md_bootstrap` MCP tool (15th tool on the server) — writes a
  short Redthread usage policy into the current project's `AGENTS.md`
  (or `CLAUDE.md`, whichever already exists) so agents use this store as
  memory automatically in future sessions, without being told each time.
  Idempotent — a no-op once the instructions are present — and documented
  as the first tool an agent should call on a new project.
- macOS added to the CI test matrix, alongside Windows and Ubuntu.

## [0.3] - 2026-07-16

### Added

- First PyPI release: `pip install redthread` (or `uv tool install
  redthread`); the MCP server runs checkout-free via `uvx redthread
  mcp-serve`.
- Documented how to register the MCP server with Claude Code (`claude mcp
  add`, scopes, `.mcp.json`, `/mcp` verification) in the usage guide.
- Documented MCP setup for other clients: Cursor, Windsurf, Claude
  Desktop, VS Code (GitHub Copilot), Codex CLI, Gemini CLI, and the
  Claude Agent SDK, including the config-format deviations (VS Code
  `servers` key, Codex TOML).

### Changed

- Added a release workflow that builds and publishes to PyPI when a
  `v*` tag is pushed.
- Synced `redthread.__version__` (previously stale at 0.1.0) with the
  package version.

## [0.2] - 2026-07-17

### Fixed

- Deploy docs via the native GitHub Actions Pages flow
  (`actions/upload-pages-artifact` + `actions/deploy-pages`) instead of
  `mkdocs gh-deploy` pushing to a `gh-pages` branch, which GitHub Pages
  ignores when the repository's Pages source is set to "GitHub Actions"
  rather than "Deploy from a branch".

## [0.1] - 2026-07-16

Add Redthread: portable, git-backed memory for multi-phase agentic workflows.

Redthread treats cross-phase context (train/eval, build/test, or any
declared pipeline) as an append-only, content-addressed memory whose
source of truth is a git remote — so context never depends on a hostname or
folder path. Any node can clone the store and continue a run; each phase
publishes a curated handoff to the next.

Core capabilities:

- Store core: versioned pydantic schemas, a LocalStore API, and a typer
  CLI (init/run/log/read/artifact/summary/handoff). Phase names are
  project-declared data, never a code enum.
- Portable sync: a git-remote hub with pull-rebase-retry, a
  content-addressed blob backend, an auto-commit daemon, and `redthread
  resume` for picking a run up on a new machine after the old one dies —
  proven across two clones with a shared blob fetched by content hash,
  never from the dead node's disk.
- Phase adapters: a generic PhaseAdapter lifecycle (batched metric
  logging, artifacts, summaries, handoffs) with two example pipelines (ML
  train/eval, app build/test) proving the core carries zero domain
  vocabulary — enforced by a static analysis guard test.
- Present layer: renders a markdown report, a slide deck, and a docs-site
  tree from a run's handoffs alone, never raw entries.
- Agent memory over MCP: a stdio MCP server exposing the store as
  portable agent memory, so a coding agent's memory is git-backed and
  visible on every machine that clones the store.
- Worktree mode: a store can live as an orphan-branch git worktree of an
  existing repo instead of needing its own, without ever touching that
  repo's checked-out branch.

125 tests, ruff-clean, docs published via MkDocs Material with a GitHub
Pages deploy workflow.
