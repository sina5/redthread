---
title: AGENTS.md example — set up Redthread as your project's agent memory
description: An AGENTS.md (or CLAUDE.md) file that you can copy. It installs Redthread with uv or pip, registers its MCP server, and tells your coding agent how to use Redthread as the memory for the project.
---

# AGENTS.md example

Most coding agents read `AGENTS.md` first to get project instructions.
Claude Code reads `CLAUDE.md` for the same purpose.

When you register the MCP server, the agent gets only the *capability* to
use Redthread. Nothing tells the agent to use these tools. A section like
the example below in `AGENTS.md` gives the agent the *habit*. The section
contains:

- A policy that tells the agent when to read and write memory.
- A CLI alternative for when the MCP server is not connected.
- Install steps, so that a new clone can do its own setup.

Is the MCP server already registered? Then you do not have to paste the
text manually. Tell the agent to call the `agents_md_bootstrap` tool. This
tool writes the same policy into the `AGENTS.md`/`CLAUDE.md` file of the
project. The tool is idempotent. Thus, the agent can safely call it in each
session.

Use the full example below for a project that does not have Redthread yet.

## Full example

Copy this text into `AGENTS.md` (or `CLAUDE.md`) in the root of your
project. Change the store path and the namespaces as necessary.

Put the text near the top of the file. Agents give more importance to
instructions that come first, and this text controls the first tool call of
the session.

By default, the example makes the store as an **orphan-branch git worktree
of the same repo**. Thus, a second remote is not necessary, and the active
branch of the repo does not change. For more information, refer to
[Worktree mode](architecture.md#worktree-mode). To use a separate store
repo, refer to [Use a separate store repo](#use-a-separate-store-repo)
below.

````markdown
## Agent memory (Redthread)

The long-term memory of this project is a **Redthread store**. The store is
a git repo. All sessions, machines, and agents that work on this project
use it. Use only this memory for this project.

If the `redthread` MCP server is not connected in this session, use the CLI
(refer to the table below). If `redthread` is not installed, do the
one-time setup before you do other work.

### Rules

1. **Load memory before you change anything.** At the start of the
   session, call `context_bootstrap` first. This one call gives the
   pipeline, the recent runs, and the memory index. Then use `memory_read`
   to read the entries that apply to the task.
2. **Make sure that you use the correct store before you write.** The
   store of this project is `<project_id>`. If `context_bootstrap` shows a
   different `project.project_id`, or if `store.binding` is not `ok`, STOP.
   The MCP server uses the store of a different project. Tell the user and
   do not write. Memory that you write there goes to the wrong project, and
   this project cannot see it.
3. **Do not record long-term knowledge in other locations.** Do not use
   the memory directory of the harness (for example,
   `~/.claude/projects/**/memory/`). Do not use a scratch `NOTES.md` file
   or a code comment. Other sessions, machines, and agents cannot see these
   locations. Write all important knowledge with `memory_write`.
4. **Write memory after each important task.** An important task changed
   behavior, had more than two steps, or has information that the next
   session must otherwise find again. Use the namespace `sessions` and the
   key `YYYY-MM-DD_short-slug`. Always add a one-line `description`. In the
   body, write what changed, why, how you validated it, and what work
   remains. Write when the task is complete, not at the end of the session.
   Do not wait for the user to tell you.
5. **Put long-term rules and decisions in the `notes` namespace.** First,
   use `memory_search`. If an entry about the same topic exists, update it.
   Do not add an almost identical entry.
6. **Do not store secrets.** The store is a git repo with a shared remote.
7. **`memory_write` commits the entry and pushes it in the background.**
   Examine the `sync` field that it returns. If the field shows `failed`,
   or if a subsequent call shows that a previous push failed, tell the
   user and correct the problem. Do not leave the entry only on this
   machine.
8. **Subagents do not get this file.** When you give important work to a
   subagent, tell it to call `context_bootstrap`. Also tell it to report
   the information that must go into memory.

### If the MCP server is not connected

Use the CLI. It uses the same store and the same data. Thus, a missing MCP
connection is not a reason to skip memory. Each command uses
`--store ./redthread-store` by default. If your store is in a different
location, add `--store <path>`.

| MCP tool | CLI equivalent |
| --- | --- |
| `context_bootstrap` | `redthread bootstrap` |
| `memory_list` | `redthread memory list [namespace]` |
| `memory_search` | `redthread memory search <query>` |
| `memory_read` | `redthread memory read <namespace> <key>` |
| `memory_write` | `redthread memory write <namespace> <key> <file> --description "..."` |

### Git safety

The store is an orphan-branch worktree of this repo. It is already checked
out at `./redthread-store`. Do not use `git checkout` or `git switch` with
the memory branch in the working tree of this repo. Always get to memory
through the tools above or through the worktree path. Then the branch that
you work on does not change.

### One-time setup

Do these steps only if `redthread` is not installed or if
`./redthread-store` does not exist. Install Redthread:

```bash
uv tool install -U redthread   # or: pip install -U redthread
```

Make the store as an orphan-branch worktree of this repo:

```bash
redthread init this-project --phases build,test,present \
  --store ./redthread-store --worktree-repo .
```

This command does the remaining setup:

- If this directory is not a git repo, the command runs `git init`.
- It adds `redthread-store/` to `.gitignore`.
- It commits the `.redthread.yaml` marker to the current branch. With this
  marker, a future clone of this repo finds the store automatically.

The command commits only these two files. It does not change the files
that you staged before.

Register the MCP server. Run only the block for your platform:

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

Sync the store. Then the memory goes with the project to other machines.
The remote of the store is the `origin` of this repo. Thus, you do not have
to set up a different remote:

```bash
redthread sync --store ./redthread-store
```
````

!!! danger "Do not store secrets"
    The memory store is a git repo. Usually, you push it to a shared
    remote. Use the same security rules as for all other repos. If you
    write API keys, tokens, or credentials with `memory_write`, git
    commits them to the history. All persons with access to the store can
    then see them.

## Why the example has this structure

Four parts of the example make the agent obey it in each session. If you
write your own version, keep these parts:

- **The policy comes before the setup.** The setup occurs one time, but the
  rules apply in each session. Thus, the rules come first and the install
  commands come last. An agent that reads the file quickly finds the
  rules first.
- **The example prohibits other memory files.** Most harnesses have their
  own local memory. For example, Claude Code writes to
  `~/.claude/projects/**/memory/`. An agent uses this memory if you do not
  tell it to stop. Then the memory stays on one machine, in one harness,
  and nobody else can see it. The example names this path to prevent this
  problem.
- **Each MCP tool has a CLI alternative.** If the MCP server is not
  connected and the agent has no alternative, the agent does not use memory
  for that session. It also does not tell you. The table gives the agent a
  different command to use.
- **The example tells the agent when to write.** The instruction "After
  you complete an important task" alone is not clear, and agents often
  postpone it. The example tells the agent *when* (at the end of the task,
  not at the end of the session), *where* (`sessions`,
  `YYYY-MM-DD_short-slug`), and *what* (the change, the reason, the
  validation, the remaining work). Thus, you can make sure that the agent
  obeys it.

## On a different machine

After you commit `.redthread.yaml`, the setup on each subsequent machine
is short. Clone the code repo and register the MCP server:

```bash
git clone <this-repo-url>
claude mcp add redthread -- redthread mcp-serve --store ./redthread-store
```

When a tool first uses the store, the MCP server reads `.redthread.yaml`
and attaches the worktree branch automatically. You do not run
`redthread init`, and you do not have to remember the
`--worktree-repo`/`--branch` flags.

For the full procedure, refer to [Discovering a store on a fresh
machine](architecture.md#discovering-a-store-on-a-fresh-machine-redthreadyaml).
This page also tells about repo mode, which must have `--allow-clone`.
When Redthread clones a URL from a committed file, this is a security
boundary. Thus, Redthread does not do it by default.

## Use a separate store repo

The example above uses worktree mode by default, because worktree mode
uses only the repo that you already have. You do not have to make a second
remote or know its URL before you start.

Use a separate store repo if the store must have its own access control or
lifecycle, independent of the code. For more information, refer to
[Worktree mode](architecture.md#worktree-mode). In this case, replace the
"One-time setup" commands with these commands:

```bash
redthread init this-project --phases build,test,present --store ./redthread-store
git -C ./redthread-store remote add origin <your-store-remote-url>
redthread sync --store ./redthread-store
```

Also remove the `.gitignore` line from the setup text. The store is a
separate repo, not a directory in the working tree of this repo.

## Why the install steps are in AGENTS.md

An agent that reads `AGENTS.md` on a new clone or a new machine cannot
know if `redthread` is on the `PATH`. The install command makes sure that
the first action of the agent is to install its memory tools. Without it,
the MCP server cannot start, and the agent does not use memory for that
session.

`uv tool install` and `pip install` do the same thing here. Use the tool
that your team already uses.

If you do not want an install step, replace the `mcp add` line with the
line that uses `uvx` (refer to [Usage](usage.md#connect-your-agent)). With
`uvx`, the first start gets `redthread` from PyPI. A separate install
step is not necessary:

```bash
claude mcp add redthread -- uvx redthread mcp-serve --store ./redthread-store
```

## Source-checkout version

Do you use a Redthread source checkout and not an installed package? Then
replace the install and registration steps with these commands:

```bash
uv sync
claude mcp add redthread -- uv run --directory /path/to/checkout redthread mcp-serve --store ./redthread-store
```

## Where this page fits

This page gives the full version of the text. It contains the install
steps, the MCP registration, and the usage policy in one block. Paste it
into a project that does not have Redthread yet.

If the `AGENTS.md` file of your project already contains the setup, use
only the memory-usage policy. For this shorter text, refer to
[Usage](usage.md#make-your-agent-use-the-memory-agentsmd).
