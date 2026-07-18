# Redthread

Portable, git-backed memory for multi-phase agentic workflows.

[![CI](https://github.com/sina5/redthread/actions/workflows/ci.yml/badge.svg)](https://github.com/sina5/redthread/actions/workflows/ci.yml)
[![Docs](https://github.com/sina5/redthread/actions/workflows/docs.yml/badge.svg)](https://sina5.github.io/redthread/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3-blue.svg)](CHANGELOG.md)

![Redthread — a red thread running through every phase of a pipeline](docs/assets/redthread.png)

Redthread treats cross-phase context (e.g. train → eval → present, or
build → test → present) as an **append-only, content-addressed memory** whose
source of truth is a **git remote**, so context never depends on a hostname or
folder path. Any node can clone the store and continue a run; each phase
publishes a **curated handoff** to the next.

Phase names are data, not code: every project declares its own pipeline in
`project.yaml`. Nothing domain-specific lives below the adapter layer.

**[Read the docs →](https://sina5.github.io/redthread/)**

## Features

- **Portable by construction** — every entry is keyed by `project_id` /
  `run_id` / `phase` / `entry_id`, never by hostname or absolute path. Swap
  the machine running a phase mid-run with `redthread resume`.
- **Domain-neutral phase adapters** — the same core drives an ML pipeline
  (train/eval) and an app pipeline (build/test) with zero special-casing.
- **Content-addressed artifacts** — small files commit inline; large ones go
  through a pluggable blob backend, referenced by sha256.
- **Curated handoffs** — each phase publishes one small, validated contract
  for the next phase to consume, never the raw entry log.
- **Report, deck, and docs from handoffs** — `redthread present` renders a
  markdown report, a slide deck, and a docs-site tree from any run.
- **Agent memory over MCP** — point a coding agent's MCP config at a
  Redthread store instead of a local `.claude`/`.agent` folder.
- **Worktree mode** — run the store as an orphan-branch `git worktree` of
  your existing code repo, so its active branch is never touched.

## Install

```bash
pip install redthread          # or: uv tool install redthread
```

## Quick start

```bash
redthread init my-project --phases build,test,present --store ./my-store
redthread run start --store ./my-store
redthread log <run_id> build note '{"msg": "hello"}' --store ./my-store
redthread read <run_id> --store ./my-store
```

Working from a source checkout instead: `uv sync`, then prefix each command
with `uv run`.

## Docs

Full docs (usage, architecture, store format) are published at
[sina5.github.io/redthread](https://sina5.github.io/redthread/) and live in
`docs/`, built with MkDocs Material:

```bash
uv run --group docs mkdocs serve
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```
