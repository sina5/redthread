---
title: FAQ — Redthread agent memory and pipeline context
description: Frequently asked questions about Redthread. How it compares to local agent memory folders, which MCP clients it supports, how it merges writes that occur at the same time, how it keeps large files, and which operating systems it supports.
---

# FAQ

## What is Redthread?

Redthread is a portable, git-backed memory store for AI agents and
multi-phase pipelines. The store keeps context entries, artifacts,
long-term agent memory, and handoffs between phases. It is a git
repository, and its remote is the source of truth. Thus, the memory moves
with the project, not with the machine.

## How is Redthread different from the local memory folder of my agent?

A `.claude/` or `.agent/` folder is bound to one directory on one machine.
A Redthread store is a git repo. Clone it on a different machine, and the
agent sees the same memory. This is true for your laptop, a dev server, or
the machine of a colleague.

The store is also append-only and content-addressed. Thus, Redthread does
not overwrite history without a record. When two writers write at the same
time, git merges the changes without conflicts.

## Must I operate a server?

No. You do not have to keep a daemon in operation, and you do not have to
host a database. The hub is a git remote: GitHub, GitLab, or a bare repo on
a NAS.

The `redthread daemon run` command is optional. It is only a local loop
that does commit-and-push at an interval.

## Which AI tools can I use with Redthread?

You can use all MCP clients that support stdio servers. [Usage](usage.md#agent-memory-mcp-server)
gives configurations that you can copy for these clients:

- Claude Code
- Claude Desktop
- Cursor
- Windsurf
- VS Code (GitHub Copilot)
- Codex CLI
- Gemini CLI
- Claude Agent SDK

You can also use the CLI and the Python API with no agent.

## Can I add a phase to a project after it starts?

Yes. Use `redthread project add-phase <name> --store ./my-store`.

This command adds the phase to `project.yaml`. By default, it also adds
the phase as `pending` to each run that is not `done` or `failed`.
Completed runs keep their initial phase-status record. Redthread does not
change this history.

To change only the runs that start after this command, add
`--no-backfill`. Refer to [Usage](usage.md#set-up-a-project).

## Is Redthread only for machine-learning pipelines?

No. Phase names are data, and each project declares its own phases.
`build,test,present` and `train,eval,present` use the same core. A CI test
makes sure that the core modules do not contain domain-specific words.

Redthread is applicable to all work that has phases, where each phase must
know what the previous phase learned.

## What occurs if two machines write at the same time?

There is no problem. Redthread has this design:

- Each entry is a separate file, and a ULID gives its name. Thus, two
  writers never use the same filename.
- If a different node pushed first, `sync` does a rebase and a push again.
  The number of attempts has a limit.

Integration tests make many appends at the same time from two clones to
make sure that this operates correctly.

## How does Redthread keep large files?

Redthread commits small artifacts inline into the store repo.

Large files (model checkpoints, datasets, build outputs) go through a
**blob backend**. The data is in a content-addressed directory, and a
sha256 hash identifies it. Git keeps only the pointer.

Each machine maps the logical name of the backend to its own local path.
Thus, the store never contains an absolute path.

## Can I keep the store in my code repo?

Yes. [Worktree mode](architecture.md#worktree-mode) attaches the store as
an orphan-branch `git worktree` of your code repo. Your active branch does
not change, and a second remote is not necessary. For this reason, the
[AGENTS.md example](agents-md.md) uses worktree mode by default.

Use a separate store repo if the store must have its own access control
or lifecycle.

## How does a new machine know if the store is a worktree or a separate repo?

A small marker file tells it. The marker is `.redthread.yaml`, and it is
committed in the code repo near `AGENTS.md`. It records the mode, the
path, and the branch (or the remote URL).

- `redthread init --worktree-repo` writes the marker *and commits it*
  automatically. It also adds a `.gitignore` entry for the store directory.
  If the host directory is not a git repo, it runs `git init` first.
- `redthread mcp-serve` reads the marker. When a tool first uses the
  store, the server attaches the store automatically.

Thus, on a second machine, you only clone the code repo and register the
same MCP command. You do not have to remember flags.

Worktree mode attaches without conditions. Repo mode must have
`--allow-clone` to clone automatically, because this runs `git clone` on a
URL from a committed file. For the full procedure, refer to [Discovering a
store on a fresh
machine](architecture.md#discovering-a-store-on-a-fresh-machine-redthreadyaml).
You can also run `redthread attach` manually at any time.

## Does Redthread operate on Windows and macOS?

Yes. The development of Redthread occurs on Windows. For each change, CI
runs the full test suite on Windows, macOS, and Ubuntu. Internally, store
paths are always POSIX-relative paths. Thus, you can move stores between
operating systems without problems.

## I registered the MCP server one time in Cursor. Now all repos get the same memory. Why?

The `--store` flag binds the server to one store. Cursor uses one global
registration for all project windows. Windsurf and the user-level
configuration of VS Code do the same. Thus, the store does not change, and
the session notes of project B go into the history of project A.

To correct this, remove `--store` from the registration. Without a
`--store` value, `mcp-serve` operates in discovery mode. For each call, it
finds the store from the committed `.redthread.yaml` marker of the
workspace. Thus, one registration gives the correct store in each repo.

If a repo has no marker, the server refuses the call. It does not give
the store of a different project. To write and commit a marker, use one of
these commands:

- For a new store: `redthread init --worktree-repo .`
- For a store that exists: `redthread attach --host-repo .`

For more information, refer to [One registration, many
projects](usage.md#one-registration-many-projects-discovery-mode).

## What is the license?

MIT. The source is at
[github.com/sina5/redthread](https://github.com/sina5/redthread). You can
send issues and pull requests.
