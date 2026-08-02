---
title: AGENTS.md example — set up Redthread as your project's agent memory
description: A copy-paste AGENTS.md (or CLAUDE.md) file that installs Redthread via uv or pip, registers its MCP server, and tells your coding agent how to use it as memory for this project.
---

# AGENTS.md example

`AGENTS.md` (also read as `CLAUDE.md` by Claude Code) is the file most
coding agents check first for project-specific instructions. MCP
registration alone only gives an agent the *capability* to use Redthread —
nothing tells it to actually reach for those tools. Putting a section like
this in `AGENTS.md` gives it the *habit*: a policy on when to read and
write memory, a CLI fallback for when the MCP server isn't connected, and
install steps so a fresh clone can bootstrap itself.

Already have the MCP server registered? Skip the manual paste below and
just ask the agent to call the `agents_md_bootstrap` tool — it writes the
same policy section into this project's `AGENTS.md`/`CLAUDE.md` itself,
and it's idempotent, so it's safe to have the agent call it every session.
The full example below is for bootstrapping a project that doesn't have
Redthread set up at all yet.

## Full example

Copy this into `AGENTS.md` (or `CLAUDE.md`) at your project root and adjust
the store path and namespaces to taste. Put it near the top of the file —
agents weight early instructions more heavily, and this one governs the
first tool call of the session. By default it creates the store as an
**orphan-branch git worktree of this same repo** — no second remote to
provision, and this repo's active branch is never touched (see [Worktree
mode](architecture.md#worktree-mode) for how that works). Prefer an
independent store repo instead? See [Prefer a separate store
repo](#prefer-a-separate-store-repo) below.

````markdown
## Agent memory (Redthread)

This project's long-term memory is a **Redthread store** — a git-backed
store shared by every session, machine, and agent working on this project.
It is the only memory that counts here. If the `redthread` MCP server isn't
connected this session, use the CLI fallback below; if `redthread` isn't
installed at all, run the one-time setup first, before other work.

### Rules

1. **Load memory before touching anything.** First action of the session:
   `context_bootstrap` (one call — pipeline, recent runs, and the memory
   index), then `memory_read` the entries that look relevant to the task.
2. **Never record durable knowledge anywhere else.** Not in the harness's
   own memory directory (e.g. `~/.claude/projects/**/memory/`), not in a
   scratch `NOTES.md`, not in a comment. Those are invisible to other
   sessions, machines, and agents, and they defeat the point of the store.
   Anything worth remembering goes to `memory_write`.
3. **Write after every non-trivial task** — anything that changed behavior,
   took more than a couple of steps, or that the next session would have to
   rediscover. Namespace `sessions`, key `YYYY-MM-DD_short-slug`, always
   with a one-line `description`; body covers what changed, why, how it was
   validated, and what's left. Do it when the task finishes, not batched at
   the end of the session, and without being asked.
4. **Put durable conventions and decisions in the `notes` namespace.**
   Update the existing entry rather than adding a near-duplicate — check
   `memory_search` first.
5. **Never store secrets.** The store is a git repo with a shared remote.
6. **`memory_write` commits and pushes for you.** Check the `sync` field it
   returns; if it says `failed`, say so and fix it instead of leaving the
   entry stranded on this machine.
7. **Subagents don't inherit this file.** When delegating work worth
   remembering, tell the subagent to call `context_bootstrap` too, and to
   report back what belongs in memory.

### If the MCP server isn't connected

Use the CLI — same store, same data, so a missing MCP connection is never a
reason to skip memory. Each command defaults to `--store ./redthread-store`;
pass `--store <path>` if yours lives elsewhere.

| MCP tool | CLI equivalent |
| --- | --- |
| `context_bootstrap` | `redthread bootstrap` |
| `memory_list` | `redthread memory list [namespace]` |
| `memory_search` | `redthread memory search <query>` |
| `memory_read` | `redthread memory read <namespace> <key>` |
| `memory_write` | `redthread memory write <namespace> <key> <file> --description "..."` |

### Git safety

The store is an orphan-branch worktree of this repo, already checked out at
`./redthread-store`. Never `git checkout`/`git switch` the memory branch in
this repo's working tree — always reach memory through the tools above or
that worktree path, so the branch you're working on stays untouched.

### One-time setup

Only needed if `redthread` isn't installed or `./redthread-store` doesn't
exist yet. Install Redthread:

```bash
uv tool install -U redthread   # or: pip install -U redthread
```

Create the store as an orphan-branch worktree of this repo:

```bash
redthread init this-project --phases build,test,present \
  --store ./redthread-store --worktree-repo .
```

That command does the rest of the setup itself: it `git init`s this repo if
it isn't one yet, adds `redthread-store/` to `.gitignore`, and commits the
`.redthread.yaml` marker to the branch you're on — which is what lets a
future clone of this repo find the store without anyone repeating any of
this. It commits those two files and nothing else, so whatever you had
staged is left alone.

Register the MCP server — run whichever block below matches the platform
you're running on (skip the rest):

```bash
# Claude Code
claude mcp add redthread -- redthread mcp-serve --store ./redthread-store
```

```bash
# Cursor has no CLI add command; this opens a one-click install deeplink
python -c "
import base64, json, webbrowser
config = {'command': 'redthread', 'args': ['mcp-serve', '--store', './redthread-store']}
encoded = base64.b64encode(json.dumps(config).encode()).decode()
webbrowser.open(f'cursor://anysphere.cursor-deeplink/mcp/install?name=redthread&config={encoded}')
"
```

```bash
# VS Code (GitHub Copilot) — use code-insiders instead of code on Insiders
code --add-mcp '{"name":"redthread","command":"redthread","args":["mcp-serve","--store","./redthread-store"]}'
```

Sync it so memory follows the project across machines instead of staying
stuck on this one — the store's remote is simply this repo's own
`origin`, so there's no separate remote to set up:

```bash
redthread sync --store ./redthread-store
```
````

!!! danger "Never store secrets"
    The memory store is a git repo, usually pushed to a shared remote —
    treat it like any other repo. API keys, tokens, and credentials
    written to `memory_write` are committed to history and visible to
    everyone with access to the store.

## Why it's written that way

Four details in the example do most of the work of getting an agent to
actually follow it, session after session. Keep them if you rewrite it:

- **Policy before setup.** The usage rules come first and the install
  commands last, because setup runs once and the rules run every session.
  An agent skimming the file hits the part that applies today.
- **An explicit ban on other memory files.** Most harnesses ship their own
  local memory (Claude Code writes under `~/.claude/projects/**/memory/`),
  and an agent will happily use it unless told not to — leaving memory
  stranded on one machine, in one harness, invisible to everyone else.
  Naming that path in the file is what closes the gap.
- **A CLI fallback for every MCP tool.** If the MCP server isn't connected,
  an agent with no alternative just drops memory for that session and says
  nothing. The table turns "unavailable" into "use the other command".
- **Concrete write triggers.** "After completing a non-trivial task" alone
  is vague enough to always be deferred; spelling out *when* (task done,
  not end of session), *where* (`sessions`, `YYYY-MM-DD_short-slug`), and
  *what* (changed, why, validation, follow-ups) makes it checkable.

## On another machine

Once `.redthread.yaml` is committed, every machine after the first gets
this for free — clone the code repo and register the MCP server, nothing
else:

```bash
git clone <this-repo-url>
claude mcp add redthread -- redthread mcp-serve --store ./redthread-store
```

The MCP server reads `.redthread.yaml` and attaches the worktree branch
automatically the first time a tool needs the store — no `redthread init`,
no `--worktree-repo`/`--branch` flags to remember or redocument. See
[Discovering a store on a fresh
machine](architecture.md#discovering-a-store-on-a-fresh-machine-redthreadyaml)
for exactly how that works, including the repo-mode case (which needs
`--allow-clone` — cloning a URL read from a committed file is a real trust
boundary, not a default to cross silently).

## Prefer a separate store repo?

Worktree mode is the default above because it needs nothing beyond a repo
you already have — no second remote to create or know in advance. A
dedicated store repo is still the better choice once the store needs its
own access control or lifecycle independent of the code it corresponds to
(see the trade-off in [Worktree mode](architecture.md#worktree-mode)).
Swap the "One-time setup" commands for:

```bash
redthread init this-project --phases build,test,present --store ./redthread-store
git -C ./redthread-store remote add origin <your-store-remote-url>
redthread sync --store ./redthread-store
```

(drop the `.gitignore` line — the store is its own repo, not a directory
inside this one's working tree.)

## Why bake install steps into AGENTS.md

An agent reading `AGENTS.md` on a fresh clone or a new machine can't
assume `redthread` is already on `PATH`. Including the install command
means the *first* thing the agent does with an unfamiliar repo is make
its own memory tooling available, rather than silently skipping memory for
that session because the MCP server failed to spawn.

`uv tool install` and `pip install` are equivalent here — pick whichever
your team already standardizes on. If you'd rather not require a prior
install at all, swap the `mcp add` line for the `uvx`-based one from
[Usage](usage.md#connect-your-agent), which fetches `redthread` from PyPI
on first launch with no separate install step:

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
