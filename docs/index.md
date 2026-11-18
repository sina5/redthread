---
title: Redthread — portable, git-backed memory for AI agents (MCP)
description: Give your AI coding agent portable, git-backed memory over MCP. Redthread syncs agent memory, pipeline context, and artifacts between machines through a git remote. It operates with Claude Code, Cursor, Windsurf, and other clients.
---

# Redthread

![Redthread — a red thread running through every phase of a pipeline](assets/redthread.png)

**Portable, git-backed memory for AI agents and multi-phase workflows.**

A coding agent usually keeps its memory in a local folder (`.claude/`,
`.agent/`) on one machine. Redthread replaces this folder with a
**git-backed memory store** that an MCP server gives to the agent. Your
agent sees the same memory on your laptop, on a dev server, and on each
machine that clones the store.

The same store also keeps the context of a multi-phase pipeline, for
example build → test or train → eval. Between the phases, it keeps a
curated handoff.

<div class="rt-term-window">
<div class="rt-term-bar"><span class="rt-term-dot"></span><span class="rt-term-dot"></span><span class="rt-term-dot"></span><span class="rt-term-title">redthread — one project, two machines</span><button class="rt-term-toggle" id="rt-term-toggle" type="button" hidden aria-pressed="false" aria-label="Pause the terminal demo"><svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg><span>Pause</span></button></div>
<pre class="rt-term" tabindex="0" role="region" aria-label="Terminal transcript: make a Redthread store, write memory, and read the same memory on a second machine"><span class="rt-term-note"># One-time setup. The store is an orphan branch of this repo. A second remote is not necessary.</span><span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread init my-project --phases build,test,present --store ./redthread-store --worktree-repo .</span>
<span class="rt-term-out">initialized store at redthread-store (phases: build, test, present)</span>
<span class="rt-term-out">committed the store's scaffolding</span>
<span class="rt-term-out">committed .redthread.yaml to the host repo (and gitignored the store directory)</span>
<span class="rt-term-out">publishes: yes — the store has no remote, so nothing can leave this machine</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">claude mcp add --scope user redthread -- redthread mcp-serve</span>
<span class="rt-term-out">Added stdio MCP server redthread with command: redthread mcp-serve to user config</span>
<span class="rt-term-note"># Memory syncs through the remote of this repo. To keep it local, use `publish --disable`.</span><span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread publish</span>
<span class="rt-term-out">publishes: yes — this store is a worktree of its host repo and pushes to</span>
<span class="rt-term-out">that repo's remote (git@github.com:acme/myproj.git)</span>
<span class="rt-term-note"># Your agent does the steps below over MCP: memory_write, memory_search, context_log.</span><span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread memory write notes db-choice notes.md --description "Why we picked Postgres"</span>
<span class="rt-term-out">written (pushed) — remote: git@github.com:acme/myproj.git</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread memory list</span>
<span class="rt-term-out">  notes/db-choice	Why we picked Postgres</span>
<span class="rt-term-out">  sessions/2026-09-22_add-eval-worker	Added the eval worker; 412 tests green</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread memory search postgres</span>
<span class="rt-term-out">notes/db-choice	Postgres over SQLite: the eval workers need concurrent writers.</span>
<span class="rt-term-note"># The same store keeps the pipeline context (build → test → present).</span><span class="rt-term-prompt">$</span> <span class="rt-term-cmd">run_id=$(redthread run start)</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread log $run_id build note '{"msg": "compiled 412 files in 31s"}'</span>
<span class="rt-term-out">01M34YFZ5K3T10D0CBJYDVW13P</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread handoff publish $run_id build handoff.json</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread sync</span>
<span class="rt-term-out">synced (pushed to git@github.com:acme/myproj.git)</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread status</span>
<span class="rt-term-out">store	~/code/myproj/redthread-store (my-project)</span>
<span class="rt-term-out">branch	redthread-store [worktree]</span>
<span class="rt-term-out">commits	yes</span>
<span class="rt-term-out">remote	git@github.com:acme/myproj.git</span>
<span class="rt-term-out">publishes	yes — publishing is enabled for this store</span>
<span class="rt-term-out">unpushed	0 commit(s)</span>
<span class="rt-term-out">uncommitted	nothing</span>
<span class="rt-term-note rt-term-rule"># A different machine. It has only a git clone.</span><span class="rt-term-prompt">$</span> <span class="rt-term-cmd">git clone git@github.com:acme/myproj.git &amp;&amp; cd myproj</span>
<span class="rt-term-out">Cloning into 'myproj'...</span>
<span class="rt-term-out">done.</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread attach</span>
<span class="rt-term-out">attached redthread-store (worktree mode)</span>
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">redthread memory list</span>
<span class="rt-term-out">  notes/db-choice	Why we picked Postgres</span>
<span class="rt-term-out">  sessions/2026-09-22_add-eval-worker	Added the eval worker; 412 tests green</span></pre>
</div>

## Install

```bash
pip install redthread          # or: uv tool install redthread
```

## Three ways to use Redthread

### Option 1 — Let the agent do the setup (recommended)

Put this text into `AGENTS.md` (or `CLAUDE.md`), and replace
`<project_id>`. The next time an agent opens the project, it uses
Redthread as its memory. If Redthread is not installed on the machine, the
agent stops and asks you to install it. If the repo has no store yet, the
agent asks you, and then makes one as an **orphan-branch git worktree of the
same repo**. Thus, you do not have to set up a second remote, and the
active branch of the repo does not change.

<div class="scrollable-code" markdown="1">
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
</div>

For the reasons behind this structure, refer to the [AGENTS.md
example](agents-md.md).

After you commit `.redthread.yaml`, the setup on each subsequent machine is
short. Clone the code repo and register the same MCP server command. The
store then attaches automatically. You do not run `redthread init` or
`--worktree-repo` again. Refer to [Discovering a store on a fresh
machine](architecture.md#discovering-a-store-on-a-fresh-machine-redthreadyaml).

!!! danger "Do not store secrets"
    The memory store is a git repo. Usually, you push it to a shared
    remote. Use the same security rules as for all other repos. If you
    write API keys, tokens, or credentials with `memory_write`, git
    commits them to the history. All persons with access to the store can
    then see them.

### Option 2 — Register the MCP server manually

Register the server one time. You do not make a store first, and you do not
give a `--store` path: the same registration serves every project. The first
time an agent uses Redthread in a repo, it asks you, then calls `store_init`,
which makes the store as an orphan-branch worktree at `./redthread-store`.
Select your client. You can paste each command without changes:

=== "🟠 Claude Code"

    ```bash
    claude mcp add --scope user redthread -- uvx redthread mcp-serve
    ```

    If `redthread` is already installed, remove `uvx`:

    ```bash
    claude mcp add --scope user redthread -- redthread mcp-serve
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
    config = {'command': 'uvx', 'args': ['redthread', 'mcp-serve']}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    webbrowser.open(f'cursor://anysphere.cursor-deeplink/mcp/install?name=redthread&config={encoded}')
    "
    ```

    Cursor shows an install confirmation. Accept it to complete the
    procedure.

=== "🔵 VS Code (Copilot)"

    ```bash
    code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve"]}'
    ```

    If you use the Insiders build, use `code-insiders` instead of `code`.

The agent now reads and writes memory through the MCP tools of Redthread
(`memory_write`, `memory_read`, `context_log`, and others). Push the store
to a git remote. Each machine that clones it then sees the same memory.
You can also connect [Windsurf, Claude Desktop, Codex CLI, Gemini CLI, and
the Claude Agent SDK](usage.md#connect-your-agent).

Then tell the agent to call `agents_md_bootstrap`. This tool writes the
policy from Option 1 into the `AGENTS.md` file of the project. Future
sessions then use this memory automatically.

### Option 3 — Use the CLI (no agent necessary)

You do not have to use an MCP client. The store and its multi-phase
pipeline records operate the same from a terminal or a script:

```bash
run_id=$(redthread run start --store ./my-store)
redthread log "$run_id" build note '{"msg": "hello"}' --store ./my-store
redthread read "$run_id" --store ./my-store
```

For the full 60-second procedure (logs, handoffs, and history), refer to
the [Quickstart](quickstart.md).

You can also keep the store in your code repo. [Worktree
mode](architecture.md#worktree-mode) keeps the store on an orphan branch of
that repo. A second remote is not necessary, and your active branch does
not change.

## Why use Redthread?

Usually, the memory of an agent or a pipeline is **bound to one folder and
one machine**. The machine can change: a team replaces a dev server, you
move from a remote computer to your laptop, or a colleague continues the
run. Then the context stays on the old machine. Redthread makes memory
**logical, not physical**:

- **Portable by design**: The key of each entry is `project_id` /
  `run_id` / `phase` / `entry_id`. The key is never a hostname or an
  absolute path. To continue a run on a new machine, use
  `redthread resume`.
- **The git remote is the source of truth**: You do not operate a server
  or a database. A git remote (GitHub, GitLab, or a bare repo on a NAS) is
  the hub.
- **Append-only, with no merge conflicts**: Each entry is a file that
  does not change. A ULID gives the name of the file. Thus, when two
  machines write at the same time, git merges the changes without
  conflicts.
- **Curated handoffs between phases**: Each phase publishes one small,
  validated contract for the subsequent phase. It does not send all the raw
  data. `redthread present` changes these handoffs into a report, a slide
  deck, and a docs tree.

## Any multi-phase pipeline

Phase names are **data**. Each project declares its own phases.
`build → test → present` and `train → eval → present` use the same core.
Code below the [adapter layer](architecture.md#phase-adapters-handoff-contracts)
has no domain-specific terms.

## Where to go next

- [Quickstart](quickstart.md): Install Redthread, connect an agent, and use
  the CLI.
- [Usage](usage.md): The full CLI and MCP reference.
- [AGENTS.md example](agents-md.md): A file that you can copy into your
  project.
- [FAQ](faq.md): Frequently asked questions and a comparison with
  alternatives.
- [Architecture](architecture.md): The data model, the store layout, and
  the sync design.
- [Store format](store-format.md): The reference for the on-disk schema.
