---
title: Architecture — how Redthread's git-backed agent memory works
description: How Redthread's git-backed store, conflict-free sync, phase adapters, worktree mode, and MCP agent memory fit together — and the two design decisions that carry it all.
---

# Architecture

Two decisions carry the whole design:

- **Logical identity, never physical.** Everything is keyed by `project_id` /
  `run_id` / `phase` / `entry_id`. Hostnames, absolute paths, and server IPs
  are recorded only as *provenance metadata*, never as addresses.
- **The git remote is the hub, not any node.** Nodes are interchangeable
  clients. Losing or swapping a node loses nothing, because the node was
  never the source of truth.

## Data model

```
Project        A long-lived body of work.            id: slug
 └─ Run        One end-to-end attempt.               id: ULID
     └─ Phase  arbitrary, project-declared (e.g. build | test | present)
         ├─ ContextEntry   append-only events (the raw memory)
         ├─ Artifact       pointer records (config, plot, checkpoint, log)
         ├─ summary.md      rolling, agent-maintained digest of the phase
         └─ handoff.json    curated contract published to the next phase
```

`run_id` is a **ULID** — lexicographically sortable and generated without
coordination, so any node can mint one offline with no collisions.

### ContextEntry

The atomic, immutable unit of memory. One JSON file per entry, named
`<seq>-<entry_id>.json`; the ULID `entry_id` is the real identity, so two
nodes writing concurrently never collide on a filename and merges stay
conflict-free.

### Artifact

A content-addressed **pointer**, not a payload. Small/textual artifacts are
committed inline; large/binary artifacts (checkpoints, datasets, build
outputs) are pushed to an object store and referenced by sha256.

### handoff.json

The curated contract a phase publishes for the next phase to consume. A
downstream phase depends **only** on this schema, never on raw entry
internals — this is what keeps phases loosely coupled and keeps the final
output (report, deck, docs site) coherent instead of a data dump.

## Store layout

The store is a git repo. It can be **its own repo** (separate remote, `redthread
init`) or an **orphan-branch worktree of an existing repo** — typically your
code repo — via `redthread init --worktree-repo <path>`. Worktree mode never
checks out or moves the host repo's active branch; it attaches a second working
directory pointed at an orphan branch that shares no history with your code,
so `git status`/`git log` in your actual working tree are completely
unaffected. See [Worktree mode](#worktree-mode) below.

```
redthread-store/                 (its own git repo, or an orphan-branch worktree)
├── project.yaml                 # phase pipeline declaration
├── runs/
│   └── <run_id>/
│       ├── run.yaml             # status, phase states, node lineage
│       ├── phases/
│       │   ├── build/
│       │   │   ├── entries/     # 0001-<ulid>.json, ...
│       │   │   ├── artifacts/
│       │   │   ├── summary.md
│       │   │   └── handoff.json
│       │   ├── test/ ...
│       │   └── present/ ...
│       └── artifacts.index.json
└── memory/
    └── <namespace>/             # portable long-term agent memory
```

## Sync

Metadata/context syncs through the git remote (tiny, clones in seconds);
large artifacts sync through a content-addressed blob backend. A small
auto-commit daemon batches entry writes and does `pull --rebase → commit →
push` on a debounce. Swapping the machine running a phase becomes
`clone + resume` — nothing is stranded because nothing was ever *owned* by a
node.

## Worktree mode

`LocalStore.init_worktree(host_repo, worktree_path, branch, project_id,
phases)` creates the store as an orphan branch of `host_repo` — usually your
code repo — attached via `git worktree add --orphan`, so the branch shares
no commit history with your code and the host repo's currently checked-out
branch never moves. `redthread.store.gitio.ensure_worktree` is the single
entry point for this: it creates the orphan branch if it doesn't exist
anywhere yet, attaches to an existing local branch if this machine already
has it, or fetches and attaches to the existing branch on `origin` if a
different machine created it first — the same three-way case `redthread
resume` already handles for plain-repo stores.

Because a git worktree shares its parent repo's objects, refs, and remote
config, **all existing sync machinery (`gitio.sync`, `pull_rebase`, `push`)
works against a worktree path completely unchanged** — no special-casing
was needed anywhere else in the sync layer. `resume_worktree(host_repo,
worktree_path, branch, run_id)` is the worktree-mode counterpart to
`resume()`; it needs no separate `--remote` argument, since the store's
remote is simply whatever `origin` the host repo (your code repo) already
has.

Trade-off versus a dedicated store repo: the store's auto-commit daemon
pushes every 5–15s on a debounce, and those commits land in the *same* repo
as your code (on a different branch). That's convenient for solo/small-scale
use — one repo, one remote, no extra provisioning — but a chatty store can
still show up in that repo's branch list and, depending on hosting-provider
settings, its activity feed. A dedicated store repo avoids that entirely and
is the better choice once a store needs its own access control or lifecycle
independent of the code it corresponds to.

## Phase adapters & handoff contracts

Each phase is a producer/consumer of the shared store via a thin adapter —
the only phase-specific code in the system. The store and sync stay generic;
an ML pipeline (`train → eval → present`) and an app pipeline
(`build → test → present`) run on the exact same core.

`redthread.adapters.base.PhaseAdapter` is the generic lifecycle every domain
adapter builds on: it marks a phase active on entry, buffers metrics and
flushes them as one batched entry (never one entry per call), registers
artifacts, maintains the rolling summary, and publishes the handoff — always
flushing synchronously on `publish_handoff` and on exit, so curated output
never depends on the sync daemon being alive. On an unhandled exception it
logs an `error` entry and marks the phase `failed` before re-raising.

`redthread.adapters.examples` holds two thin pipelines built on
`PhaseAdapter` — `ml_train`/`ml_eval` and `app_build`/`app_test` — proving
the core carries zero domain vocabulary: a CI test parses every module
outside `adapters/examples/` and fails if an ML- or app-specific term
(`epoch`, `checkpoint`, `coverage_pct`, ...) appears anywhere but a
docstring.

`redthread.adapters.present` is the domain-neutral flip side: it consumes
**only** the handoffs published by whichever phases precede `present` in
the project's own pipeline (`store.manifest.phases`), and renders a
markdown report, a slide deck (python-pptx), and a docs-site markdown tree
from them — reading identically whether upstream was train/eval or
build/test. It passes the same domain-vocabulary CI guard as the rest of
the core.

## Agent memory (MCP)

`redthread.mcp` wraps the store as an MCP server (stdio transport): fourteen
tools covering runs, context entries, artifacts, summaries, handoffs, and a
`memory/<namespace>/` tree for long-term agent memory that isn't tied to any
run. Point a coding agent's MCP config at this instead of its local
`.claude/`/`.agent/` folder, and the same memory is visible on every machine
that clones the store — the same portability guarantee the rest of
Redthread makes, now exposed to an agent instead of a script. `mcp/tools.py`
holds the actual operations as plain, directly-testable functions;
`mcp/server.py` is a thin `FastMCP` wrapper around them.

Memory keys are validated against path traversal (`../`, absolute paths,
backslashes) before touching disk, since these are the one part of the
store schema an LLM agent supplies free-form.
