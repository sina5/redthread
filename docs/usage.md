---
title: Usage — CLI and MCP reference for Redthread
description: Full reference for Redthread — the MCP agent-memory server with per-client setup, plus runs, logging, artifacts, blob backends, sync, resume, and present.
---

# Usage

Every command takes `--store PATH` (defaults to `./redthread-store`). This
page is the full reference: the MCP agent-memory server first, then the CLI
grouped by what each command group does.

## Set up a project

```bash
redthread init <project_id> --phases build,test,present [--store PATH] [--name NAME]
```

Creates a store and declares its **phase pipeline** — an ordered list of
arbitrary names. `build,test,present` and `train,eval,present` are equally
valid; use whatever names fit your project. Every later command validates
`phase` against this list.

### Worktree mode — no separate repo needed

```bash
redthread init demo --phases build,test,present \
  --store ./store-wt --worktree-repo /path/to/your/code-repo --branch redthread-store
```

Instead of its own repo, the store becomes an **orphan-branch git worktree**
of a repo you already have — typically your code repo. `--store` is where
the worktree gets checked out; `--worktree-repo` never has its active branch
touched or moved. Good default when you don't want to provision a second
remote; trades that off against the store's frequent auto-commits landing in
the same repo as your code (see [Worktree mode](architecture.md#worktree-mode)
for the trade-off in full).

## Agent memory (MCP server)

```bash
redthread mcp-serve [--store PATH]
```

Runs an MCP server (stdio) exposing the store as 14 tools: `store_init`,
`run_start`/`run_list`, `context_log`/`context_read`,
`artifact_put`/`artifact_get`, `summary_update`/`summary_get`,
`handoff_publish`/`handoff_get`, and `memory_write`/`memory_read`/
`memory_list` for long-term memory not tied to any run. Point a coding
agent's MCP config at this instead of its local `.claude`/`.agent` folder —
the same memory becomes visible on every machine that clones the store.

### Claude Code

Register the server with one command — `uvx` fetches `redthread` from
PyPI on first launch, so no checkout or prior install is needed:

```bash
claude mcp add redthread -- uvx redthread mcp-serve --store /path/to/my-store
```

By default this registers the server for the current project only. Add
`--scope user` to make it available in all your projects, or
`--scope project` to write a `.mcp.json` you can commit and share with
your team:

```json
{
  "mcpServers": {
    "redthread": {
      "command": "uvx",
      "args": ["redthread", "mcp-serve", "--store", "/path/to/my-store"]
    }
  }
}
```

Verify with `/mcp` inside Claude Code — `redthread` should show as
connected with 14 tools. A quick smoke test is asking the agent to call
`run_list` or `memory_list`.

If the CLI is already installed (`pip install redthread` or
`uv tool install redthread`), the command shortens to:

```bash
claude mcp add redthread -- redthread mcp-serve --store /path/to/my-store
```

To run from a source checkout instead, replace `uvx redthread` with
`uv run --directory /path/to/checkout redthread` in any example.

### Other MCP clients

Any client that supports stdio command servers works. Most reuse the
exact `mcpServers` JSON block shown above; they differ only in where the
config file lives.

**Cursor** — Settings → MCP (or *MCP & Integrations*) → *Add Custom MCP*,
or edit the file directly: `.cursor/mcp.json` in the project root
(shareable, per-project) or `~/.cursor/mcp.json` (all projects). Same
`mcpServers` block as above.

**Windsurf** — Settings → Cascade → MCP Servers, or edit
`~/.codeium/windsurf/mcp_config.json`. Same `mcpServers` block.

**Claude Desktop** — Settings → Developer → Edit Config, which opens
`claude_desktop_config.json` (`%APPDATA%\Claude\` on Windows,
`~/Library/Application Support/Claude/` on macOS). Same `mcpServers`
block; restart the app to take effect.

**VS Code (GitHub Copilot)** — run the **MCP: Add Server** command, or
create `.vscode/mcp.json`. VS Code uses a `servers` key with an explicit
type instead of `mcpServers`:

```json
{
  "servers": {
    "redthread": {
      "type": "stdio",
      "command": "uvx",
      "args": ["redthread", "mcp-serve", "--store", "/path/to/my-store"]
    }
  }
}
```

**Codex CLI** — add a TOML table to `~/.codex/config.toml`:

```toml
[mcp_servers.redthread]
command = "uvx"
args = ["redthread", "mcp-serve", "--store", "/path/to/my-store"]
```

**Gemini CLI** — add the standard `mcpServers` block to
`~/.gemini/settings.json` (or `.gemini/settings.json` in the project).

**Claude Agent SDK** — pass the server definition programmatically:

```python
from claude_agent_sdk import ClaudeAgentOptions

options = ClaudeAgentOptions(
    mcp_servers={
        "redthread": {
            "command": "uvx",
            "args": ["redthread", "mcp-serve", "--store", "/path/to/my-store"],
        }
    }
)
```

!!! note "Windows"
    GUI clients don't always inherit your shell's PATH. If the server
    fails to spawn, use the absolute path to `uvx.exe` (or the installed
    `redthread.exe`) as `command`.

### Make your agent actually use it (AGENTS.md)

Registering the server gives the agent the *capability*; a short note in
your project's instructions file gives it the *habit* — without one, most
agents won't call memory tools unprompted. Add this to your `AGENTS.md`
(read by most coding agents) or `CLAUDE.md` and adjust to taste:

````markdown
## Memory (Redthread)

This project's agent memory lives in a Redthread store (MCP server
"redthread"), not in local files.

- At session start, call `memory_list` / `memory_read` to load relevant
  context before making changes.
- After completing a non-trivial task, write a dated summary with
  `memory_write` (namespace `sessions`, key like `2026-07-18_short-slug`):
  what changed, why, validation done, follow-ups.
- Store durable conventions and decisions under the `notes` namespace;
  never store secrets.
````

Namespaces are free-form — `sessions` and `notes` are just a convention
that has worked well; pick whatever fits your team.

## Runs

A run is one end-to-end attempt through the pipeline, identified by a ULID.

| Command | Effect |
|---|---|
| `redthread run start` | Start a run; prints its `run_id` |
| `redthread run list` | List all run ids in the store |

```bash
run_id=$(redthread run start --store ./my-store)
```

## Logging context

```bash
redthread log <run_id> <phase> <type> [PAYLOAD_JSON] [--tags a,b]
```

- `type` is one of `metric | decision | code_change | artifact_ref | error |
  milestone | note`.
- `PAYLOAD_JSON` is a raw JSON object string (defaults to `{}`).
- Entries are immutable and append-only — there is no edit or delete.

```bash
redthread log "$run_id" build decision '{"note": "switched to strategy B"}' --store ./my-store
```

## Artifacts

Register a file as a content-addressed artifact pointer (sha256, verified on
resolve). `kind` is open-ended (`build`, `checkpoint`, `plot`, `docs`, ...).

```bash
redthread artifact add <run_id> <phase> <source_path> <kind> [--artifact-id ID]
```

```bash
redthread artifact add "$run_id" build ./dist/app.bin build --store ./my-store
```

## Reading back

```bash
redthread read <run_id> [--phase PHASE] [--type TYPE]
```

Prints one JSON entry per line, in creation order. Omit `--phase`/`--type` to
read the full run history.

```bash
redthread read "$run_id" --store ./my-store --phase build --type decision
```

## Rolling summary

A single mutable markdown file per phase — the agent-maintained digest,
distinct from the immutable entry log.

```bash
redthread summary set <run_id> <phase> <markdown_file>
redthread summary get <run_id> <phase>
```

## Handoffs — the phase-to-phase contract

A phase publishes **one curated handoff**, and the next phase should read
*only* that — never the raw entry log.

```bash
redthread handoff publish <run_id> <phase> <handoff_json_file>
redthread handoff get <run_id> <phase>
```

The JSON file needs at minimum `headline`; `run_id` and `from_phase` are
filled in from the command arguments if omitted. Full schema:

```json
{
  "headline": "build ok",
  "key_results": {"warnings": 0},
  "best_artifacts": ["app-bin"],
  "decisions": ["..."],
  "open_questions": ["..."],
  "figures": ["..."]
}
```

## Large artifacts (blob backends)

Small files go through `artifact add` (inline, copied into the store repo).
For large files — checkpoints, build outputs, datasets — use a **blob
backend** instead: only the pointer is committed to git; the bytes live in a
content-addressed directory that every machine resolves independently.

```bash
redthread backend set <name> <local_or_mounted_path>   # per-machine, not in the store
redthread backend list

redthread artifact add-blob <run_id> <phase> <source_path> <kind> --backend <name>
redthread artifact get <run_id> <artifact_id> [--dest PATH]   # resolves inline or blob-backed
```

```bash
redthread backend set objects /mnt/shared/redthread-objects --store ./my-store
redthread artifact add-blob "$run_id" build ./dist/app.bin build --backend objects --store ./my-store
```

`backend set` maps a **logical name** to wherever that target happens to be
mounted on *this* machine — the store itself only ever records the logical
name, never the path, which is what keeps artifacts portable across nodes.

## Sync, resume, and the daemon

The store is a git repo. `sync` does one pull-rebase-commit-push cycle;
`daemon run` repeats that on an interval; `resume` is how a new machine picks
up a run after the one running it is gone.

```bash
redthread sync [--message "..."]
redthread daemon run [--interval SECONDS]
redthread resume <run_id> [--remote URL]
```

```bash
redthread sync --store ./my-store
redthread resume "$run_id" --store ./new-clone --remote git@github.com:you/my-store.git
```

`resume` clones the store if it isn't present locally (needs `--remote`),
otherwise pulls the latest; either way it closes out the previous node's
lineage stint, opens a new one for this machine, and logs a `milestone`
entry — so the full history shows exactly which machine did what, when.

For a worktree-mode store, use `--worktree-repo` instead of `--remote` — no
separate remote URL is needed, since the store's remote is whatever `origin`
the host (code) repo already has:

```bash
redthread resume "$run_id" --store ./store-wt \
  --worktree-repo /path/to/your/already-cloned/code-repo --branch redthread-store
```

## Present — report, deck, and docs from handoffs

```bash
redthread present <run_id> <output_dir> [--phase present]
```

Renders `report.md`, `deck.pptx`, and a `docs/` markdown tree from every
upstream phase's handoff (in pipeline order, as declared in `project.yaml`)
— never from raw entries. Works the same regardless of what your upstream
phases were called.

```bash
redthread present "$run_id" ./out --store ./my-store
```

## Typical session

```bash
redthread init demo --phases build,test,present --store ./s
run_id=$(redthread run start --store ./s)

redthread log "$run_id" build note '{"msg": "start"}' --store ./s
redthread artifact add "$run_id" build ./dist/app.bin build --store ./s

echo '{"headline": "build ok", "key_results": {"warnings": 0}}' > handoff.json
redthread handoff publish "$run_id" build handoff.json --store ./s

redthread handoff get "$run_id" build --store ./s   # consumed by the test phase
redthread read "$run_id" --store ./s                # full raw history
```

!!! note "Windows / PowerShell"
    Passing inline JSON as a shell argument is quoting-fragile in PowerShell.
    Write the JSON to a temp file and use the file-based commands
    (`handoff publish`, `summary set`), or call `redthread.store.LocalStore`
    directly from Python.
