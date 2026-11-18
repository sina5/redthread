---
title: AGENTS.md example — set up Redthread as your project's agent memory
description: An AGENTS.md (or CLAUDE.md) section that you can copy. It tells your coding agent to use Redthread as the project memory, and to ask you to install Redthread when it is missing.
---

# AGENTS.md example

Most coding agents read `AGENTS.md` first to get project instructions.
Claude Code reads `CLAUDE.md` for the same purpose.

When you register the MCP server, the agent gets only the *capability* to
use Redthread. The section below gives the agent the *habit*. It tells the
agent what to do in each session, and what to do when Redthread is not
installed on the machine.

You do not have to paste the text manually. If the MCP server is
registered, tell the agent to call `agents_md_bootstrap`. This tool writes
the same section into `AGENTS.md` (or `CLAUDE.md`, if only that file
exists). The tool is idempotent. Thus, the agent can safely call it in each
session.

## The section

Copy this text near the top of `AGENTS.md` or `CLAUDE.md`. Replace
`<project_id>` with the `project_id` of your store. Agents give more
importance to instructions that come first.

````markdown
## Agent memory (Redthread)

This project's long-term memory is a Redthread store (MCP server `redthread`).
Every session, machine, and agent on this project shares it. Use no other memory.

**If Redthread is missing** (no `redthread` MCP tools and no `redthread` command),
STOP and ask the user to install it before you continue. Do not fall back to
another memory. Suggest these commands, then starting a new session:

```bash
uv tool install redthread    # or: pip install redthread
claude mcp add --scope user redthread -- redthread mcp-serve
```

Other clients: https://sina5.github.io/redthread/usage/#connect-your-agent

If only the MCP tools are missing, suggest the `claude mcp add` line, and
until then use the CLI from the repo root: `redthread bootstrap`,
`redthread memory list|search|read|write`.

**Each session:**

1. Call `context_bootstrap` first, with this repo's absolute path as `workspace`.
   Then `memory_read` the entries that apply to the task.
2. If `project.project_id` is not `<project_id>`, or `store.binding` is not `ok`,
   STOP: the server has another project's store. Tell the user. Do not write.
3. If this repo has no store yet, ask the user, then call `store_init`.

**Writing memory:**

- After each non-trivial task, without being asked, call `memory_write`:
  namespace `sessions`, key `YYYY-MM-DD_short-slug`, a one-line `description`,
  and a body with what changed, why, how you validated it, and what is left.
- Put durable rules and decisions in `notes`. Call `memory_search` first and
  update the existing entry instead of adding a near-duplicate.
- If the returned `sync` field says `failed`, tell the user.
- Never write memory anywhere else (`~/.claude/projects/**/memory/`, scratch
  notes files). Never store secrets: the store is a git repo with a remote.
- Never check out the `redthread-store` branch here. Use the tools.
- Subagents do not read this file. Tell them to call `context_bootstrap`.
````

## Why the section has this structure

- **The install check comes first.** On a new clone or a new machine, the
  agent cannot know if Redthread is installed. Without this check, the
  agent silently uses no memory, or it uses the local memory of the
  harness. The section tells it to stop and ask you. The agent does not
  install software without your permission.
- **The section prohibits other memory locations.** Most harnesses have
  their own local memory, for example `~/.claude/projects/**/memory/` in
  Claude Code. Memory there stays on one machine, and nobody else can see
  it.
- **Each MCP tool has a CLI alternative.** If the MCP server is not
  connected, the agent uses the CLI on the same store. It does not skip
  memory for the session.
- **The section tells the agent when and where to write.** "After an
  important task" alone is not clear, and agents often postpone it. The
  section gives the namespace, the key format, and the content.
- **The project id check stops writes to the wrong store.** `AGENTS.md`
  goes with the repo. Thus, the agent can find a server that uses the store
  of a different project.

## Setup that the section refers to

The agent suggests these commands when Redthread is missing:

```bash
uv tool install redthread    # or: pip install redthread
claude mcp add --scope user redthread -- redthread mcp-serve
```

For Cursor, VS Code, and other clients, refer to [Connect your
agent](usage.md#connect-your-agent). To use Redthread without an install
step, register the server with `uvx redthread mcp-serve`. To use a source
checkout, use `uv run --directory /path/to/checkout redthread mcp-serve`.

You do not make the store before the first session. In a repo without a
store, the agent asks you, and then calls `store_init`. This tool makes
the store as an orphan-branch worktree at `./redthread-store`, and commits
`.redthread.yaml`. On a different machine, clone the repo and register the
server. The server reads `.redthread.yaml` and attaches the store
automatically. For more information, refer to [Discovering a store on a
fresh machine](architecture.md#discovering-a-store-on-a-fresh-machine-redthreadyaml).

Does the store use a separate repo, or a path other than
`./redthread-store`? Then `agents_md_bootstrap` adds the correct `--store`
value to the CLI line. If you copy the section manually, add
`--store <path>` yourself.

!!! danger "Do not store secrets"
    The memory store is a git repo. Usually, you push it to a shared
    remote. If you write API keys, tokens, or credentials with
    `memory_write`, git commits them to the history. All persons with
    access to the store can then see them.
