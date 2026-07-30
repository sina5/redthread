# Changelog

All notable changes to this project are documented in this file.

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
