# Redthread

Portable, git-backed memory for AI agents and multi-phase workflows.

[![CI](https://github.com/sina5/redthread/actions/workflows/ci.yml/badge.svg)](https://github.com/sina5/redthread/actions/workflows/ci.yml)
[![Docs](https://github.com/sina5/redthread/actions/workflows/docs.yml/badge.svg)](https://sina5.github.io/redthread/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.14-blue.svg)](CHANGELOG.md)

![Redthread — a red thread running through every phase of a pipeline](docs/assets/redthread.png)

A coding agent usually keeps its memory in a local folder (`.claude/`,
`.agent/`) on one machine. Redthread replaces this folder with a
**git-backed memory store** that an MCP server gives to the agent. Each
machine that clones the store shows the same memory to the agent.

The same store also keeps the context of a multi-phase pipeline, for
example train → eval → present or build → test → present. This context is
an **append-only, content-addressed memory**. A **git remote** is its
source of truth. Any node can clone the store and continue a run. Each
phase publishes a **curated handoff** to the subsequent phase.

Phase names are data, not code. Each project declares its own pipeline in
`project.yaml`. Code below the adapter layer has no domain-specific terms.

**[Read the docs →](https://sina5.github.io/redthread/)**

## Features

- **Agent memory over MCP**: Set the MCP configuration of a coding agent
  (Claude Code, Cursor, Windsurf, VS Code, and others) to a Redthread store.
  Do not use a local `.claude`/`.agent` folder.
- **One registration for many projects**: Run `mcp-serve` without
  `--store`. Each workspace then gets the store that its committed
  `.redthread.yaml` file names. Thus, one global MCP entry (Cursor,
  Windsurf, VS Code) operates correctly in all your repos.
- **Portable by design**: The key of each entry is `project_id` /
  `run_id` / `phase` / `entry_id`. The key is never a hostname or an
  absolute path. To move a phase to a different machine during a run, use
  `redthread resume`.
- **Domain-neutral phase adapters**: The same core operates an ML
  pipeline (train/eval) and an app pipeline (build/test). It has no special
  cases for each domain.
- **Content-addressed artifacts**: Redthread commits small files inline.
  Large files go to a blob backend that you can replace. A sha256 hash
  identifies each file.
- **Curated handoffs**: Each phase publishes one small, validated
  contract for the subsequent phase. The subsequent phase does not read the
  raw entry log.
- **Report, deck, and docs from handoffs**: `redthread present` makes a
  markdown report, a slide deck, and a docs-site tree from a run.
- **Worktree mode**: The store can be an orphan-branch `git worktree` of
  your code repo. Redthread does not change the active branch of that repo.
- **Automatic attach on a new machine**: A committed `.redthread.yaml`
  marker lets `redthread mcp-serve` and `redthread attach` find and attach
  the store automatically. On a new clone, only `git clone` and the same
  MCP command are necessary. You do not have to remember flags.

## Install

```bash
pip install redthread          # or: uv tool install redthread
```

## Three ways to use Redthread

### Option 1 — Let the agent do the setup (recommended)

Copy the [AGENTS.md example](https://sina5.github.io/redthread/agents-md/)
into your project. The next time the agent opens the project, it does
these steps:

1. It installs Redthread.
2. It makes the store.
3. It registers the MCP server.

You do not do manual steps. By default, the store is an **orphan-branch git
worktree of the same repo**. Thus, you do not have to set up a second
remote, and the active branch of the repo does not change.

### Option 2 — Register the MCP server manually

Make a store:

```bash
redthread init my-project --phases build,test,present --store ./my-store
```

Then register the store with your agent. Select your client:

<details open>
<summary>🟠 Claude Code</summary>

```bash
claude mcp add redthread -- uvx redthread mcp-serve --store ./my-store
```

If `redthread` is already installed, remove `uvx`:

```bash
claude mcp add redthread -- redthread mcp-serve --store ./my-store
```

To make sure that the server operates, type `/mcp` in Claude Code. The
`redthread` server shows as connected with 19 tools.

</details>

<details>
<summary>⚫ Cursor</summary>

Cursor does not install MCP servers with a CLI command. It uses a one-click
deeplink. This command makes the deeplink and opens it. It uses only
Python, which Redthread already uses:

```bash
python -c "
import base64, json, webbrowser
config = {'command': 'uvx', 'args': ['redthread', 'mcp-serve', '--store', './my-store']}
encoded = base64.b64encode(json.dumps(config).encode()).decode()
webbrowser.open(f'cursor://anysphere.cursor-deeplink/mcp/install?name=redthread&config={encoded}')
"
```

Cursor shows an install confirmation. Accept it to complete the procedure.

</details>

<details>
<summary>🔵 VS Code (Copilot)</summary>

```bash
code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","./my-store"]}'
```

If you use the Insiders build, use `code-insiders` instead of `code`.

</details>

You can also connect Windsurf, Claude Desktop, Codex CLI, Gemini CLI, and
the Claude Agent SDK. For each client, refer to
[MCP client setup](https://sina5.github.io/redthread/usage/#connect-your-agent).

After you connect the agent, tell it to call `agents_md_bootstrap`. This
tool writes the usage policy from Option 1 into the `AGENTS.md`/`CLAUDE.md`
file of the project. Future sessions then use this memory automatically.

### Option 3 — Use the CLI (no agent necessary)

```bash
redthread run start --store ./my-store
redthread log <run_id> build note '{"msg": "hello"}' --store ./my-store
redthread read <run_id> --store ./my-store
```

If you use a source checkout, run `uv sync` first. Then put `uv run` before
each command.

## Docs

The full docs (usage, architecture, store format) are at
[sina5.github.io/redthread](https://sina5.github.io/redthread/). The
source is in `docs/`. MkDocs Material builds the site. To show the docs
locally, run this command:

```bash
uv run --group docs mkdocs serve
```

## Changelog

For release notes, refer to [CHANGELOG.md](CHANGELOG.md).

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
```
