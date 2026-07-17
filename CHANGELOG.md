# Changelog

All notable changes to this project are documented in this file.

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
