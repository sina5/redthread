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

## Three ways to use it

### Option 1 — Paste-and-go: let the agent set itself up (recommended)

Drop this into `AGENTS.md` (or `CLAUDE.md`) and your agent installs
Redthread, creates the store, and registers the MCP server itself the
next time it opens this project — no manual steps at all. By default the
store is an **orphan-branch git worktree of this same repo**, so there's
no second remote to provision and this repo's active branch is never
touched.

<div class="scrollable-code" markdown="1">
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

Create the store as an orphan-branch worktree of this repo (skip if
`./redthread-store` already exists):

```bash
redthread init this-project --phases build,test,present \
  --store ./redthread-store --worktree-repo .
```

Keep it out of this repo's own working tree status:

```bash
echo redthread-store/ >> .gitignore
```

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
</div>

See the [full AGENTS.md example](agents-md.md) for variants — a
no-install `uvx` version, one for a Redthread source checkout, and one
for a separate (non-worktree) store repo.

!!! danger "Never store secrets"
    The memory store is a git repo, usually pushed to a shared remote —
    treat it like any other repo. API keys, tokens, and credentials
    written to `memory_write` are committed to history and visible to
    everyone with access to the store.

### Option 2 — Register the MCP server yourself

Prefer to do it by hand instead of pasting a file? Create a store, then
register it with your agent — pick your client, every command below is
ready to paste as-is:

```bash
redthread init my-project --phases build,test,present --store ./my-store
```

=== "🟠 Claude Code"

    ```bash
    claude mcp add redthread -- uvx redthread mcp-serve --store ./my-store
    ```

    Already have `redthread` installed? Drop `uvx`:

    ```bash
    claude mcp add redthread -- redthread mcp-serve --store ./my-store
    ```

    Verify with `/mcp` inside Claude Code — `redthread` should show as
    connected with 15 tools.

=== "⚫ Cursor"

    Cursor installs MCP servers via a deeplink rather than a CLI command.
    This generates one and opens it, using only Python (already a
    Redthread dependency):

    ```bash
    python -c "
    import base64, json, webbrowser
    config = {'command': 'uvx', 'args': ['redthread', 'mcp-serve', '--store', './my-store']}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    webbrowser.open(f'cursor://anysphere.cursor-deeplink/mcp/install?name=redthread&config={encoded}')
    "
    ```

    Accept the install confirmation Cursor opens with to finish.

=== "🔵 VS Code (Copilot)"

    ```bash
    code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","./my-store"]}'
    ```

    Use `code-insiders` instead of `code` if you're on the Insiders build.

That's it — the agent now reads and writes memory through Redthread's MCP
tools (`memory_write`, `memory_read`, `context_log`, ...). Push the store to
any git remote and every machine that clones it sees the same memory.
[Windsurf, Claude Desktop, Codex CLI, Gemini CLI, and the Claude Agent
SDK](usage.md#connect-your-agent) connect just as easily.

Then ask the agent to call `agents_md_bootstrap` — it writes the same
policy shown in Option 1 above into this project's `AGENTS.md` for you,
so future sessions use this memory automatically without being told.

### Option 3 — Drive it from the CLI (no agent required)

No MCP client at all? The store and its multi-phase pipeline tracking work
the same from a terminal or a script:

```bash
run_id=$(redthread run start --store ./my-store)
redthread log "$run_id" build note '{"msg": "hello"}' --store ./my-store
redthread read "$run_id" --store ./my-store
```

See the [Quickstart](quickstart.md) for the full 60-second walkthrough —
logging, handoffs, and reading history back.

Prefer to keep the store inside your existing code repo instead of a
separate one? [Worktree mode](architecture.md#worktree-mode) runs it as an
orphan branch of that repo — no second remote to provision, and your
active branch is never touched.

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
- [AGENTS.md example](agents-md.md) — a copy-paste file for your project
- [FAQ](faq.md) — common questions, compared alternatives
- [Architecture](architecture.md) — data model, store layout, sync design
- [Store format](store-format.md) — the on-disk schema reference
