---
title: Quickstart — give your AI agent portable memory in one minute
description: Install Redthread, make a git-backed memory store, connect it to Claude Code or a different MCP client, and publish your first phase handoff in less than one minute.
---

# Quickstart

## Install

Install from PyPI:

```bash
pip install redthread          # or: uv tool install redthread
```

Or install from a source checkout:

```bash
uv sync    # then prefix each `redthread` command below with `uv run`
```

## Give portable memory to your coding agent (MCP)

Make a store:

```bash
redthread init my-project --phases build,test,present --store ./my-store
```

Then register the store with your agent. Select your client:

=== "🟠 Claude Code"

    ```bash
    claude mcp add redthread -- uvx redthread mcp-serve --store ./my-store
    ```

    If `redthread` is already installed, remove `uvx`:

    ```bash
    claude mcp add redthread -- redthread mcp-serve --store ./my-store
    ```

    To make sure that the server operates, type `/mcp` in Claude Code. The
    `redthread` server shows as connected with 19 tools.

=== "⚫ Cursor"

    Cursor does not install MCP servers with a CLI command. It uses a
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

    If `redthread` is already installed, remove `uvx` from the
    configuration:

    ```bash
    python -c "
    import base64, json, webbrowser
    config = {'command': 'redthread', 'args': ['mcp-serve', '--store', './my-store']}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    webbrowser.open(f'cursor://anysphere.cursor-deeplink/mcp/install?name=redthread&config={encoded}')
    "
    ```

    Cursor shows an install confirmation. Accept it to complete the
    procedure.

=== "🔵 VS Code (Copilot)"

    ```bash
    code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","./my-store"]}'
    ```

    If `redthread` is already installed, remove `uvx`:

    ```bash
    code --add-mcp '{"name":"redthread","command":"redthread","args":["mcp-serve","--store","./my-store"]}'
    ```

    If you use the Insiders build, use `code-insiders` instead of `code`.

Tell the agent to call `memory_write` and then `memory_list`. The files
then show in the `memory/` directory of the store.

!!! tip "Make your agent use the memory"
    When you register the server, the agent gets only the *capability*.
    Tell the agent to call `agents_md_bootstrap`. This tool writes a short
    policy into the `AGENTS.md`/`CLAUDE.md` file of the project. The tool
    is idempotent. Thus, the agent can safely call it at the start of each
    session.

    Do you set up a new project? Then copy the [AGENTS.md
    example](agents-md.md). This one file also installs Redthread and
    registers the MCP server.

To make the memory portable, add a remote to the store and sync it:

```bash
git -C ./my-store remote add origin git@github.com:you/my-store.git
redthread sync --store ./my-store
```

Each machine, colleague, or agent that clones the store now sees the same
memory. You can also connect Windsurf, Claude Desktop, Codex CLI, Gemini
CLI, and the Claude Agent SDK. For each client, refer to the [full client
reference](usage.md#connect-your-agent).

## 60-second CLI procedure

The same store also records the runs of a multi-phase pipeline. This is
one full procedure:

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

For the full command reference, refer to [Usage](usage.md). It also
gives information about these topics:

- Artifacts.
- Blob backends for large files.
- `resume`, to continue a run on a different machine.
- `present`, to make a report, a deck, and a docs site from handoffs.

## Show these docs locally

```bash
uv run --group docs mkdocs serve
```
