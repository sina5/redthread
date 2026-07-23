# Redthread

Portable, git-backed memory for AI agents and multi-phase workflows.

[![CI](https://github.com/sina5/redthread/actions/workflows/ci.yml/badge.svg)](https://github.com/sina5/redthread/actions/workflows/ci.yml)
[![Docs](https://github.com/sina5/redthread/actions/workflows/docs.yml/badge.svg)](https://sina5.github.io/redthread/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.4-blue.svg)](CHANGELOG.md)

![Redthread — a red thread running through every phase of a pipeline](docs/assets/redthread.png)

Your coding agent's memory lives in a local folder (`.claude/`, `.agent/`)
on one machine. Redthread replaces it with a **git-backed memory store
served over MCP**: the same memory is visible to your agent on every machine
that clones the store. The same store carries cross-phase pipeline context
(e.g. train → eval → present, or build → test → present) as an
**append-only, content-addressed memory** whose source of truth is a
**git remote** — any node can clone the store and continue a run, and each
phase publishes a **curated handoff** to the next.

Phase names are data, not code: every project declares its own pipeline in
`project.yaml`. Nothing domain-specific lives below the adapter layer.

**[Read the docs →](https://sina5.github.io/redthread/)**

## Features

- **Agent memory over MCP** — point a coding agent's MCP config (Claude
  Code, Cursor, Windsurf, VS Code, ...) at a Redthread store instead of a
  local `.claude`/`.agent` folder.
- **Portable by construction** — every entry is keyed by `project_id` /
  `run_id` / `phase` / `entry_id`, never by hostname or absolute path. Swap
  the machine running a phase mid-run with `redthread resume`.
- **Domain-neutral phase adapters** — the same core drives an ML pipeline
  (train/eval) and an app pipeline (build/test) with zero special-casing.
- **Content-addressed artifacts** — small files commit inline; large ones go
  through a pluggable blob backend, referenced by sha256.
- **Curated handoffs** — each phase publishes one small, validated contract
  for the next phase to consume, never the raw entry log.
- **Report, deck, and docs from handoffs** — `redthread present` renders a
  markdown report, a slide deck, and a docs-site tree from any run.
- **Worktree mode** — run the store as an orphan-branch `git worktree` of
  your existing code repo, so its active branch is never touched.

## Install

```bash
pip install redthread          # or: uv tool install redthread
```

## Three ways to use it

### Option 1 — Paste-and-go: let the agent set itself up (recommended)

Copy the [AGENTS.md example](https://sina5.github.io/redthread/agents-md/)
into your project and your agent installs Redthread, creates the store,
and registers the MCP server itself the next time it opens this project —
no manual steps at all. By default the store is an **orphan-branch git
worktree of this same repo**, so there's no second remote to provision
and this repo's active branch is never touched.

### Option 2 — Register the MCP server yourself

Prefer to do it by hand instead of pasting a file? Create a store, then
register it with your agent — pick your client:

```bash
redthread init my-project --phases build,test,present --store ./my-store
```

<details open>
<summary>🟠 Claude Code</summary>

```bash
claude mcp add redthread -- uvx redthread mcp-serve --store ./my-store
```

Already have `redthread` installed? Drop `uvx`:

```bash
claude mcp add redthread -- redthread mcp-serve --store ./my-store
```

Verify with `/mcp` inside Claude Code — `redthread` should show as connected
with 15 tools.

</details>

<details>
<summary>⚫ Cursor</summary>

Cursor installs MCP servers via a one-click deeplink rather than a CLI
command. This generates one and opens it, using only Python (already a
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

</details>

<details>
<summary>🔵 VS Code (Copilot)</summary>

```bash
code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","./my-store"]}'
```

Use `code-insiders` instead of `code` if you're on the Insiders build.

</details>

Windsurf, Claude Desktop, Codex CLI, Gemini CLI, and the Claude Agent SDK
connect just as easily — see
[MCP client setup](https://sina5.github.io/redthread/usage/#connect-your-agent)
for each.

Once connected, ask the agent to call `agents_md_bootstrap` — it writes the
same usage policy as Option 1 above into this project's
`AGENTS.md`/`CLAUDE.md` itself, so future sessions use this memory
automatically without being told.

### Option 3 — Drive it from the CLI (no agent required)

```bash
redthread run start --store ./my-store
redthread log <run_id> build note '{"msg": "hello"}' --store ./my-store
redthread read <run_id> --store ./my-store
```

Working from a source checkout instead: `uv sync`, then prefix each command
with `uv run`.

## Docs

Full docs (usage, architecture, store format) are published at
[sina5.github.io/redthread](https://sina5.github.io/redthread/) and live in
`docs/`, built with MkDocs Material:

```bash
uv run --group docs mkdocs serve
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release notes.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```
