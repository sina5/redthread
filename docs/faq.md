---
title: FAQ — Redthread agent memory and pipeline context
description: Common questions about Redthread — how it compares to local agent memory folders, which MCP clients work, how concurrent writes merge, large-file handling, and Windows support.
---

# FAQ

## What is Redthread?

A portable, git-backed memory store for AI agents and multi-phase
pipelines. Context entries, artifacts, long-term agent memory, and
phase-to-phase handoffs live in a git repository whose remote is the source
of truth — so memory follows the project, not the machine.

## How is this different from my agent's local memory folder?

A `.claude/` or `.agent/` folder is bound to one directory on one machine.
A Redthread store is a git repo: clone it anywhere and the agent sees the
same memory — on your laptop, a dev server, or a teammate's machine. It's
also append-only and content-addressed, so history is never silently
overwritten and concurrent writers merge cleanly.

## Do I need to run a server?

No. There is no daemon you must keep alive and no database to host. The hub
is any git remote — GitHub, GitLab, or a bare repo on a NAS. The optional
`redthread daemon run` is just a local convenience loop that batches
commit-and-push on an interval.

## Which AI tools work with it?

Any MCP client that supports stdio servers: Claude Code, Claude Desktop,
Cursor, Windsurf, VS Code (GitHub Copilot), Codex CLI, Gemini CLI, and the
Claude Agent SDK are all covered with copy-paste configs in
[Usage](usage.md#agent-memory-mcp-server). The CLI and Python API work
with no agent at all.

## Can I add a phase to a project after it's already running?

Yes: `redthread project add-phase <name> --store ./my-store`. It appends
the phase to `project.yaml` and, by default, backfills it as `pending`
into every run that isn't already `done`/`failed` — completed runs keep
their original phase-status snapshot as a historical record rather than
being rewritten. Pass `--no-backfill` to only affect runs started after
the change. See [Usage](usage.md#set-up-a-project).

## Is it only for machine-learning pipelines?

No. Phase names are data, declared per project — `build,test,present` and
`train,eval,present` run on the exact same core, and a CI guard keeps
domain vocabulary out of the core modules. If your work has phases and the
next phase needs what the last one learned, it fits.

## What happens if two machines write at the same time?

Nothing bad — that's the design. Every entry is its own file named by a
ULID, so concurrent writers never collide on a filename, and `sync` does a
rebase-and-push with bounded retry when another node pushed first. This is
covered by integration tests that deliberately hammer concurrent appends
from two clones.

## How are large files handled?

Small artifacts commit inline into the store repo. Large ones — model
checkpoints, datasets, build outputs — go through a **blob backend**: the
bytes live in a content-addressed directory (referenced by sha256) and only
the pointer is committed to git. Each machine maps the backend's logical
name to its own local path, so no absolute path ever enters the store.

## Can I keep the store inside my existing code repo?

Yes — [worktree mode](architecture.md#worktree-mode) attaches the store as
an orphan-branch `git worktree` of your code repo. Your active branch is
never touched, and no second remote needs provisioning. A dedicated store
repo is still the better choice once the store needs its own access control
or lifecycle.

## Does it run on Windows?

Yes. Redthread is developed on Windows and CI runs the full test suite on
both Windows and Ubuntu. Store paths are always POSIX-relative internally,
so stores move cleanly between operating systems.

## What's the license?

MIT. The source is at
[github.com/sina5/redthread](https://github.com/sina5/redthread) —
issues and pull requests are welcome.
