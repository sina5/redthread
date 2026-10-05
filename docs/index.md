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
<span class="rt-term-prompt">$</span> <span class="rt-term-cmd">claude mcp add redthread -- redthread mcp-serve --store ./redthread-store</span>
<span class="rt-term-out">Added stdio MCP server redthread with command: redthread mcp-serve</span>
<span class="rt-term-out">--store ./redthread-store to local config</span>
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

Put this text into `AGENTS.md` (or `CLAUDE.md`). The next time the agent
opens the project, it installs Redthread, makes the store, and registers
the MCP server. You do not do manual steps.

By default, the store is an **orphan-branch git worktree of the same
repo**. Thus, you do not have to set up a second remote, and the active
branch of the repo does not change.

<div class="scrollable-code" markdown="1">
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
2. **Do not record long-term knowledge in other locations.** Do not use
   the memory directory of the harness (for example,
   `~/.claude/projects/**/memory/`). Do not use a scratch `NOTES.md` file
   or a code comment. Other sessions, machines, and agents cannot see these
   locations. Write all important knowledge with `memory_write`.
3. **Write memory after each important task.** An important task changed
   behavior, had more than two steps, or has information that the next
   session must otherwise find again. Use the namespace `sessions` and the
   key `YYYY-MM-DD_short-slug`. Always add a one-line `description`. In the
   body, write what changed, why, how you validated it, and what work
   remains. Write when the task is complete, not at the end of the session.
   Do not wait for the user to tell you.
4. **Put long-term rules and decisions in the `notes` namespace.** First,
   use `memory_search`. If an entry about the same topic exists, update it.
   Do not add an almost identical entry.
5. **Do not store secrets.** The store is a git repo with a shared remote.
6. **`memory_write` commits the entry and pushes it in the background.**
   Examine the `sync` field that it returns. If the field shows `failed`,
   or if a subsequent call shows that a previous push failed, tell the
   user and correct the problem. Do not leave the entry only on this
   machine.
7. **Subagents do not get this file.** When you give important work to a
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
</div>

The [full AGENTS.md example](agents-md.md) has more versions of this
text:

- A version that uses `uvx` and has no install step.
- A version for a Redthread source checkout.
- A version for a separate store repo (not a worktree).

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

Make a store:

```bash
redthread init my-project --phases build,test,present --store ./my-store
```

Then register the store with your agent. Select your client. You can paste
each command without changes:

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

    Cursor shows an install confirmation. Accept it to complete the
    procedure.

=== "🔵 VS Code (Copilot)"

    ```bash
    code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","./my-store"]}'
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
