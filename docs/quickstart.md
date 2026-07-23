---
title: Quickstart — give your AI agent portable memory in one minute
description: Install Redthread, create a git-backed memory store, connect it to Claude Code or another MCP client, and publish your first phase handoff — in under a minute.
---

# Quickstart

## Install

From PyPI:

```bash
pip install redthread          # or: uv tool install redthread
```

Or from a source checkout:

```bash
uv sync    # then prefix each `redthread` command below with `uv run`
```

## Give your coding agent portable memory (MCP)

Create a store, then register it with your agent — pick your client:

```bash
redthread init my-project --phases build,test,present --store ./my-store
```

=== "Claude Code"

    ```bash
    claude mcp add redthread -- uvx redthread mcp-serve --store ./my-store
    ```

    Already have `redthread` installed? Drop `uvx`:

    ```bash
    claude mcp add redthread -- redthread mcp-serve --store ./my-store
    ```

    Verify with `/mcp` inside Claude Code — `redthread` should show as
    connected with 14 tools.

=== "Cursor"

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

=== "VS Code (Copilot)"

    ```bash
    code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","./my-store"]}'
    ```

    Use `code-insiders` instead of `code` if you're on the Insiders build.

Ask the agent to call `memory_write`, then `memory_list`, and you'll see
the files land under `memory/` in the store.

Then make the agent use its memory *unprompted*: add a short policy note
to your project's `AGENTS.md` or `CLAUDE.md` — copy the
[ready-made AGENTS.md example](agents-md.md), which also covers installing
Redthread and registering the MCP server in one paste.

To make that memory portable, give the store a remote and sync it:

```bash
git -C ./my-store remote add origin git@github.com:you/my-store.git
redthread sync --store ./my-store
```

Any other machine — or teammate, or agent — that clones the store now sees
the same memory. Windsurf, Claude Desktop, Codex CLI, Gemini CLI, and the
Claude Agent SDK connect just as easily; see the
[full per-client reference](usage.md#connect-your-agent) for each.

## 60-second CLI walkthrough

The same store tracks multi-phase pipeline runs. One end-to-end pass:

```bash
# a run is one attempt through your declared phases
run_id=$(redthread run start --store ./my-store)

# append immutable context entries as a phase works
redthread log "$run_id" build note '{"msg": "kicked off build"}' --store ./my-store

# publish the build phase's curated handoff for the next phase
echo '{"headline": "build ok", "key_results": {"warnings": 0}}' > handoff.json
redthread handoff publish "$run_id" build handoff.json --store ./my-store

# the test phase reads only the handoff — never build's raw log
redthread handoff get "$run_id" build --store ./my-store

# full raw history, one JSON entry per line
redthread read "$run_id" --store ./my-store
```

See [Usage](usage.md) for the full command reference — artifacts, blob
backends for large files, `resume` for continuing a run on another machine,
and `present` for rendering a report, deck, and docs site from handoffs.

## Serve these docs locally

```bash
uv run --group docs mkdocs serve
```
