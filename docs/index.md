---
description: Redthread is a portable, git-backed memory for multi-phase agentic workflows — train/eval, build/test, or any pipeline — that never depends on a hostname or folder path.
---

# Redthread

Portable, cross-phase managed memory for agentic workflows.

Redthread treats cross-phase context as an **append-only, content-addressed
memory** whose source of truth is a **git remote**, so context never depends
on a hostname or folder path. Any node can clone the store and continue a
run; each phase publishes a **curated handoff** to the next.

## Why

Coding-agent memory today is folder- and machine-specific. When the machine
running a phase of your work changes — a dev server gets swapped, you move
from a remote box to your laptop — the context is stranded. Redthread fixes
that by making memory **logical, not physical**: entries are keyed by
`project_id` / `run_id` / `phase` / `entry_id`, never by hostname or absolute
path.

## Any multi-phase pipeline

The design uses train → eval → present as one example, but phase names are
**data**, declared per-project — `build → test → present` works identically.
Nothing domain-specific lives below the [adapter layer](architecture.md#phase-adapters-handoff-contracts).

## Where to go next

- [Quickstart](quickstart.md) — install and drive the CLI
- [Usage](usage.md) — the full CLI reference
- [Architecture](architecture.md) — data model, store layout, sync design
- [Store format](store-format.md) — the on-disk schema reference
