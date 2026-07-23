---
title: AGENTS.md example — set up Redthread as your project's agent memory
description: A copy-paste AGENTS.md (or CLAUDE.md) file that installs Redthread via uv or pip, registers its MCP server, and tells your coding agent how to use it as memory for this project.
---

# AGENTS.md example

`AGENTS.md` (also read as `CLAUDE.md` by Claude Code) is the file most
coding agents check first for project-specific instructions. MCP
registration alone only gives an agent the *capability* to use Redthread —
nothing tells it to actually reach for those tools. Putting a section like
this in `AGENTS.md` gives it the *habit*: install steps so a fresh clone
can bootstrap itself, the MCP registration command, and a short policy on
when to read and write memory.

## Full example

Copy this into `AGENTS.md` (or `CLAUDE.md`) at your project root and adjust
the store path and namespaces to taste.

````markdown
## Agent memory (Redthread)

This project's agent memory is a Redthread store, not local files —
install it and register it before doing anything else this session if the
`redthread` MCP server isn't already connected.

### One-time setup

Install Redthread:

```bash
uv tool install redthread   # or: pip install redthread
```

Create the store (skip if `./redthread-store` already exists):

```bash
redthread init this-project --phases build,test,present --store ./redthread-store
```

Register the MCP server:

```bash
claude mcp add redthread -- redthread mcp-serve --store ./redthread-store
```

Give the store a remote and sync it, so memory follows the project across
machines instead of staying stuck on this one:

```bash
git -C ./redthread-store remote add origin <your-store-remote-url>
redthread sync --store ./redthread-store
```

### How to use it

- At session start, call `memory_list` / `memory_read` to load relevant
  context before making changes.
- After completing a non-trivial task, write a dated summary with
  `memory_write` (namespace `sessions`, key like
  `2026-07-22_short-slug`): what changed, why, validation performed,
  follow-ups.
- Store durable conventions and decisions under the `notes` namespace;
  never store secrets.
- Run `redthread sync --store ./redthread-store` (or let the auto-commit
  daemon handle it) after writing memory, so other machines see it.
````

## Why bake install steps into AGENTS.md

An agent reading `AGENTS.md` on a fresh clone or a new machine can't
assume `redthread` is already on `PATH`. Including the install command
means the *first* thing the agent does with an unfamiliar repo is make
its own memory tooling available, rather than silently skipping memory for
that session because the MCP server failed to spawn.

`uv tool install` and `pip install` are equivalent here — pick whichever
your team already standardizes on. If you'd rather not require a prior
install at all, swap the `mcp add` line for the `uvx`-based one from
[Usage](usage.md#claude-code), which fetches `redthread` from PyPI on
first launch with no separate install step:

```bash
claude mcp add redthread -- uvx redthread mcp-serve --store ./redthread-store
```

## Source-checkout variant

Working from a Redthread source checkout instead of an installed package?
Replace the install and registration steps with:

```bash
uv sync
claude mcp add redthread -- uv run --directory /path/to/checkout redthread mcp-serve --store ./redthread-store
```

## Where this fits

This page is the full, self-contained version — install, MCP
registration, and usage policy in one block, meant to be pasted into a
project that has none of it yet. If your project's `AGENTS.md` already
covers setup and you just need the memory-usage policy on its own, see the
shorter snippet in [Usage](usage.md#make-your-agent-actually-use-it-agentsmd).
