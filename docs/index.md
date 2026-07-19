---
title: Redthread — portable, git-backed memory for AI agents (MCP)
description: Give your AI coding agent portable, git-backed memory over MCP. Redthread syncs agent memory, pipeline context, and artifacts across machines through a git remote — works with Claude Code, Cursor, Windsurf, and more.
---

# Redthread

![Redthread — a red thread running through every phase of a pipeline](assets/redthread.png)

**Portable, git-backed memory for AI agents and multi-phase workflows.**

Your coding agent's memory lives in a local folder (`.claude/`, `.agent/`)
on one machine. Redthread replaces that folder with a **git-backed memory
store served over MCP**: the same memory is visible to your agent on your
laptop, a dev server, and any machine that clones the store. The same store
also carries multi-phase pipeline context — build → test, train → eval —
with a curated handoff between phases.

## Install

```bash
pip install redthread          # or: uv tool install redthread
```

## Use it in your project

Create a store for your project, then point your agent at it:

```bash
# 1. Create a git-backed memory store (phases are your choice of names)
redthread init my-project --phases build,test,present --store ./my-store

# 2. Give your coding agent that store as its memory, over MCP
claude mcp add redthread -- redthread mcp-serve --store /path/to/my-store
```

That's it — the agent now reads and writes memory through Redthread's MCP
tools (`memory_write`, `memory_read`, `context_log`, ...). Push the store to
any git remote and every machine that clones it sees the same memory. To
make the agent use its memory unprompted, drop a
[three-bullet snippet](usage.md#make-your-agent-actually-use-it-agentsmd)
into your project's `AGENTS.md`.
[Cursor, Windsurf, Claude Desktop, VS Code, and other MCP clients](usage.md#other-mcp-clients)
use the same one-line server command.

Prefer to keep everything in your existing code repo? [Worktree
mode](architecture.md#worktree-mode) runs the store as an orphan branch of
that repo — no second remote to provision, and your active branch is never
touched.

## Why Redthread?

Agent and pipeline memory today is **folder- and machine-bound**. When the
machine changes — a dev server gets swapped, you move from a remote box to
your laptop, a teammate picks up the run — the context is stranded.
Redthread makes memory **logical, not physical**:

- **Portable by construction** — every entry is keyed by `project_id` /
  `run_id` / `phase` / `entry_id`, never by hostname or absolute path.
  Continue a run on a new machine with `redthread resume`.
- **Git remote as the source of truth** — no server to run, no database to
  host. Any git remote (GitHub, GitLab, a bare repo on a NAS) is the hub.
- **Append-only and conflict-free** — entries are immutable ULID-named
  files, so two machines writing concurrently merge cleanly.
- **Curated handoffs between phases** — each phase publishes one small,
  validated contract for the next, never a raw data dump; `redthread
  present` turns those handoffs into a report, a slide deck, and a docs
  tree.

## Any multi-phase pipeline

Phase names are **data**, declared per-project — `build → test → present`
and `train → eval → present` run on the exact same core. Nothing
domain-specific lives below the [adapter layer](architecture.md#phase-adapters-handoff-contracts).

## Where to go next

- [Quickstart](quickstart.md) — install, hook up an agent, drive the CLI
- [Usage](usage.md) — the full CLI and MCP reference
- [FAQ](faq.md) — common questions, compared alternatives
- [Architecture](architecture.md) — data model, store layout, sync design
- [Store format](store-format.md) — the on-disk schema reference
