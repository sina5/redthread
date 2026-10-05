---
title: Architecture — how Redthread's git-backed agent memory works
description: How the git-backed store, the sync without conflicts, the phase adapters, worktree mode, and MCP agent memory of Redthread operate together. Two design decisions are the base of the full design.
---

# Architecture

Two decisions are the base of the full design:

- **Logical identity, never physical.** The key of each item is
  `project_id` / `run_id` / `phase` / `entry_id`. Redthread records
  hostnames, absolute paths, and server IPs only as *provenance metadata*.
  It never uses them as addresses.
- **The git remote is the hub, not a node.** All nodes are clients of the
  same type, and you can replace one with a different one. If you lose or
  replace a node, you lose no data, because the node was never the source
  of truth.

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

The `run_id` is a **ULID**. You can sort ULIDs in time sequence, and a node
can make one without a central service. Thus, each node can make a new ID
offline, and no two IDs are the same.

### ContextEntry

A context entry is the smallest unit of memory, and it does not change.
Each entry is one JSON file with the name `<seq>-<entry_id>.json`. The ULID
`entry_id` identifies the entry. Thus, when two nodes write at the same
time, they do not use the same filename, and merges have no conflicts.

### Artifact

An artifact record is a content-addressed **pointer**. It does not contain
the data.

- Redthread commits small text artifacts inline.
- Redthread pushes large binary artifacts (checkpoints, datasets, build
  outputs) to an object store. A sha256 hash identifies each artifact.

### handoff.json

The handoff is the curated contract that a phase publishes for the
subsequent phase. A downstream phase uses **only** this schema. It never
uses the raw entries. Thus, the phases stay loosely coupled. The final
output (report, deck, docs site) is also clear, and it is not a dump of all
the data.

## Store layout

The store is a git repo. It can be one of these two types:

- **A separate repo** with its own remote. Use `redthread init`.
- **An orphan-branch worktree of a repo that exists**, usually your code
  repo. Use `redthread init --worktree-repo <path>`.

Worktree mode never checks out or moves the active branch of the host repo.
It attaches a second working directory to an orphan branch. This branch
has no shared history with your code. Thus, `git status` and `git log` in
your working tree show no changes. Refer to [Worktree mode](#worktree-mode)
below.

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

Metadata and context sync through the git remote. This data is small, and
a clone takes only some seconds. Large artifacts sync through a
content-addressed blob backend.

A small auto-commit daemon collects entry writes. After a short delay, it
does `pull --rebase → commit → push`.

To move a phase to a different machine, do `clone + resume`. No data stays
on the old machine, because no node ever *owned* the data.

## Worktree mode

`LocalStore.init_worktree(host_repo, worktree_path, branch, project_id,
phases)` makes the store as an orphan branch of `host_repo`. Usually,
`host_repo` is your code repo. The function attaches the branch with
`git worktree add --orphan`. Thus, the branch has no shared commit history
with your code. The branch that is checked out in the host repo does not
move.

`redthread.store.gitio.ensure_worktree` is the only entry point for this
procedure. It does one of these three steps:

- If the orphan branch does not exist, it makes the branch.
- If this machine already has the branch locally, it attaches to it.
- If a different machine made the branch first, it fetches the branch from
  `origin` and attaches to it.

`redthread resume` does the same three steps for stores that are plain
repos.

A git worktree shares the objects, refs, and remote configuration of its
parent repo. Thus, **the sync functions (`gitio.sync`, `pull_rebase`,
`push`) operate on a worktree path without changes**. The sync layer has no
special cases for worktrees.

`resume_worktree(host_repo, worktree_path, branch, run_id)` is the
worktree-mode version of `resume()`. It does not use a separate `--remote`
argument. The remote of the store is the `origin` of the host repo (your
code repo).

### Worktree mode compared with a separate store repo

The auto-commit daemon of the store pushes each 5–15 seconds, after a
short delay. These commits go into the *same* repo as your code, on a
different branch.

- This is convenient for one person or a small team. You have one repo,
  one remote, and no more setup.
- But a store with many commits can show in the branch list of the repo.
  With some hosting providers, it can also show in the activity feed.

A separate store repo prevents these problems. Use a separate store repo
if the store must have its own access control or lifecycle, independent of
the code.

## Discovering a store on a fresh machine (`.redthread.yaml`)

`redthread init` and `redthread init --worktree-repo` do not record the
mode of a project. Both are only CLI flags. Thus, no file on the disk
records "the store of this project is a worktree of this repo on branch
X". A person or an agent cannot find this information later.

Without more data, a second machine cannot know which flag to use:
`--remote`, `--worktree-repo`, or no flag. Only the person (or the
documentation that the person wrote) knows.

The `.redthread.yaml` file gives this information. It is a small marker
that is committed in the **host (code) repo**, near
`AGENTS.md`/`.mcp.json`. It records the mode of the store and how to get
to it:

```yaml
schema_version: 1
store:
  mode: worktree          # or "repo"
  path: ./redthread-store
  branch: redthread-store # worktree mode
  # url: git@github.com:you/project-memories.git   # repo mode instead
```

`LocalStore.init_worktree` writes this file automatically. Worktree mode
always knows its host repo, so no more configuration is necessary.

Plain `LocalStore.init` writes the file only when you call it with
`host_repo=...` (CLI: `redthread init --host-repo PATH`). In repo mode, the
`url` is usually not known yet when you run `init`.

`redthread.hostconfig.attach(host_repo, store_path, allow_clone=False)`
reads the marker and makes `store_path`:

- **Worktree mode** attaches without conditions.
  `gitio.ensure_worktree` does its usual three checks for the `branch` in
  the marker. It tries the local branch first. Then it fetches from the
  `origin` of the host repo. Then it makes a new orphan branch. This is safe to do automatically. The "remote"
  is the code repo that you already cloned. It is not a new security
  boundary.
- **Repo mode** must have `allow_clone=True` to clone a missing store
  from the `url` in the marker. When Redthread runs `git clone` on a URL
  from a committed file, this *is* a real security boundary. A dangerous
  repo can point to a poisoned store, and agents do what they read in
  memory. Thus, Redthread never crosses this boundary without permission.
- If the store already exists locally, `attach` does the opposite. It
  copies the `origin` URL of the store into the `url` of the marker. If
  you make a repo-mode marker before the remote exists, do these steps:
  run `git remote add origin ...`, then run `redthread attach` again. This
  fills in the `url`. A separate update command is not necessary.

Two commands use this function:

- **`redthread attach [--store PATH] [--host-repo PATH] [--allow-clone]`**:
  A person or a script uses this command to make the store immediately.
- **`redthread mcp-serve`**: The server uses the same function when a tool
  first uses the store. If `--store` does not exist but `--host-repo` has a
  marker, the server attaches the store before it opens it. The default
  `--host-repo` is the working directory of the server, usually the root of
  the project.

`store_init` also obeys this procedure. If the attach shows that a
different machine already filled the store, `store_init` returns the
manifest of that store. It does not return an "already exists" error.

The result: on a second machine, you only clone the code repo and register
the same MCP server command as all other users. You do not have to
remember flags, and you do not clone the store manually.

## Phase adapters & handoff contracts

Each phase reads from and writes to the shared store through a thin
adapter. Adapters are the only phase-specific code in the system. The
store and the sync stay generic. An ML pipeline (`train → eval →
present`) and an app pipeline (`build → test → present`) use the same core.

`redthread.adapters.base.PhaseAdapter` is the generic lifecycle for all
domain adapters. It does these steps:

- When the phase starts, it sets the phase to active.
- It collects metrics and writes them as one entry. It does not write one
  entry for each call.
- It registers artifacts.
- It updates the rolling summary.
- It publishes the handoff.

The adapter always writes its data immediately on `publish_handoff` and on
exit. Thus, the curated output does not depend on the sync daemon. If an
unhandled exception occurs, the adapter logs an `error` entry and sets the
phase to `failed`. Then it raises the exception again.

`redthread.adapters.examples` contains two thin pipelines that use
`PhaseAdapter`: `ml_train`/`ml_eval` and `app_build`/`app_test`. They show
that the core contains no domain-specific words. A CI test parses each
module outside `adapters/examples/`. If an ML or app term (`epoch`,
`checkpoint`, `coverage_pct`, ...) occurs outside a docstring, the test
fails.

`redthread.adapters.present` is the domain-neutral output side. It uses
**only** the handoffs from the phases before `present` in the pipeline of
the project (`store.manifest.phases`). From these handoffs, it makes a
markdown report, a slide deck (python-pptx), and a docs-site markdown
tree. The output is the same for train/eval and for build/test upstream
phases. This module also passes the CI test for domain-specific words.

## Agent memory (MCP)

`redthread.mcp` makes the store available as an MCP server (stdio
transport). The server has 19 tools for runs, context entries,
artifacts, summaries, and handoffs. It also has a `memory/<namespace>/`
tree for long-term agent memory that is not related to a run.

Set the MCP configuration of a coding agent to this server, not to its
local `.claude/`/`.agent/` folder. Then each machine that clones the store
shows the same memory. This is the same portability that the remaining
parts of Redthread give to scripts.

- `mcp/tools.py` contains the operations as plain functions that you can
  test directly.
- `mcp/server.py` is a thin `FastMCP` wrapper around these functions.

Redthread validates memory keys against path traversal (`../`, absolute
paths, backslashes) before it writes to the disk. The memory keys are the
only part of the store schema that an LLM agent writes in free form.
