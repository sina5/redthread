---
title: Usage — CLI and MCP reference for Redthread
description: The full reference for Redthread. The MCP agent-memory server with setup for each client, and the commands for runs, logs, artifacts, blob backends, sync, resume, and present.
---

# Usage

Each command accepts `--store PATH`. The default is `./redthread-store`.

This page is the full reference. It starts with the MCP agent-memory
server. Then it shows the CLI commands in groups, by function.

## Set up a project

```bash
redthread init <project_id> --phases build,test,present [--store PATH] [--name NAME]
```

This command makes a store and declares its **phase pipeline**. The
pipeline is a list of names in sequence. You can use all names.
`build,test,present` and `train,eval,present` are both correct. Use the
names that apply to your project. All subsequent commands make sure that
each `phase` is in this list.

### Worktree mode — a separate repo is not necessary

```bash
redthread init demo --phases build,test,present \
  --store ./store-wt --worktree-repo /path/to/your/code-repo --branch redthread-store
```

In this mode, the store is not a separate repo. It is an **orphan-branch
git worktree** of a repo that you already have, usually your code repo.

- `--store` is the location where git checks out the worktree.
- The active branch of the `--worktree-repo` repo never changes or moves.

Worktree mode is a good default if you do not want to set up a second
remote. But the frequent auto-commits of the store go into the same repo as
your code. For the full comparison, refer to
[Worktree mode](architecture.md#worktree-mode). The
[AGENTS.md example](agents-md.md) uses this mode by default, because it
uses only a repo that you already have.

On a new project, this mode is even easier. If `--worktree-repo` is not a
git repo yet, `init` first runs `git init -b main` on it. Thus, a new
project directory can keep memory without a separate git setup.

Then `init` completes the setup:

- It adds the store directory to the `.gitignore` file of the host repo.
  The store is a worktree. It is not content of the host branch.
- It commits `.redthread.yaml` to the current branch.

This commit is a pathspec commit. It changes only these two paths. Files
that you staged before stay staged and are not committed. To stage and
commit the files yourself, add `--no-commit-marker`.

If the commit is not successful, `init` shows a warning but exits with
code 0. The store exists and you can use it. The usual cause is a missing
git identity.

### Find the store again on a different machine

`--worktree-repo` always writes a small marker, `.redthread.yaml`, into
the host repo. The marker records the mode, the path, and the branch.
`init` also commits the marker. Thus, a second machine that clones the
code repo can attach the store. It does not have to give
`--worktree-repo` or `--branch`:

```bash
redthread attach [--store PATH] [--host-repo PATH] [--allow-clone]
```

The default value of `--host-repo` is the current directory.

For a plain store (not a worktree), also give `--host-repo` to `init`.
Then `init` writes the marker, also without `--worktree-repo`:

```bash
redthread init demo --phases build,test,present --store ./my-store --host-repo .
```

`attach` also fills in the `url` of a repo-mode marker after you add a
remote. Run `git remote add origin ...`, then run `attach` again. It copies
the URL of the store remote into the marker. A separate update command is
not necessary.

`redthread mcp-serve` also reads this marker automatically. Refer to
[Agent memory (MCP server)](#agent-memory-mcp-server). For the full
procedure, refer to
[Discovering a store on a fresh machine](architecture.md#discovering-a-store-on-a-fresh-machine-redthreadyaml).

### Add a phase later

```bash
redthread project add-phase <phase> [--store PATH] [--no-backfill]
```

This command adds a new phase to the pipeline of the project after the
project starts.

By default, the command also adds the new phase as `pending` to each run
that is not `done` or `failed`. Thus, a run that is in progress can log to
the new phase immediately. Completed runs keep their initial phase-status
record without changes.

To change only the runs that start after this command, add
`--no-backfill`.

```bash
redthread project add-phase deploy --store ./my-store
```

## Agent memory (MCP server)

```bash
redthread mcp-serve [--store PATH] [--host-repo PATH] [--allow-clone]
redthread mcp-serve   # discovery mode: one registration, every project
```

This command starts an MCP server (stdio). The server makes the store
available as 19 tools:

- `context_bootstrap` (start with this tool).
- `store_init`.
- `run_start`/`run_list`.
- `context_log`/`context_read`.
- `artifact_put`/`artifact_get`.
- `summary_update`/`summary_get`.
- `handoff_publish`/`handoff_get`.
- `memory_write`/`memory_read`/`memory_list`/`memory_search`/`memory_import`,
  for long-term memory that is not related to a run.
- `sync_status`, to show the push state of the store.
- `agents_md_bootstrap` (refer to the text below).

Set the MCP configuration of a coding agent to this server, not to its
local `.claude`/`.agent` folder. Then each machine that clones the store
shows the same memory.

Know these five functions before you connect an agent:

- **Start with `context_bootstrap`.** One call returns the phase pipeline,
  the recent runs and their status, the published handoffs, and the full
  memory index with a description for each entry. Without this tool, a new
  agent must make four or five calls to get this information, and usually
  it does not make them. `redthread bootstrap --store PATH` shows the same
  data for persons.
- **The `run_id` is optional on all run tools.** If you do not give it,
  the tool uses the newest `active` run of the store. The response
  contains the `run_id` that the tool used. Thus, the agent always knows
  which run it wrote to. If runs on different machines are in progress at
  the same time, give the `run_id`.
- **Memory entries contain their own descriptions.** Give a one-line
  `description` to `memory_write`. Redthread keeps it as YAML frontmatter.
  `memory_list` returns these descriptions. Thus, an agent can find the
  important entries and does not have to read all entries.
  `memory_search` searches keys, descriptions, tags, and bodies.
- **When you write memory, Redthread publishes it.** For details, refer to
  the subsequent section.
- **You can import memory that you already have.** `memory_import` (or
  `redthread memory import <path>`) changes a file or a directory of notes
  into memory entries. Each text file becomes one entry. The memory can
  be in the directory of a harness, in a `docs/decisions/` folder, or in
  the `memory/` tree of a different store. You do not type it again. Refer to [Import memory that you already
  have](#import-memory-that-you-already-have).

### How `memory_write` publishes memory

`memory_write` commits the entry immediately and pushes it in the
background. This is because an agent does not always remember to call
`sync` a second time. Memory that is not pushed is not available on the
next machine, and portability is the purpose of the store.

The call returns at the speed of the local disk. The response contains a
`sync.status` value:

- `pushing`: The commit is complete and the push is in progress.
- `committed`: The store has no remote.
- `failed`, with a `detail` field: The commit was not successful.

If a background push is not successful, the next call on the store
reports it in `sync.previous`. The `sync_status` tool shows the push in
progress, the result of the last push, and the number of commits that are
not published.

To write many entries and sync only one time at the end, give
`push=False`. Redthread commits the entry in both cases. Thus, if you do
not publish, you do not lose data.

The CLI runs a new process for each command. Thus, `redthread memory
write` pushes immediately, unless you add `--no-push`.

### MCP resources

The server also makes the same data available as MCP **resources**. Some
clients can attach context without a tool call. These are the resources:

- `redthread://project`
- `redthread://memory`
- `redthread://bootstrap`
- `redthread://memory/{namespace}/{key}`
- `redthread://handoff/{run_id}/{phase}`
- `redthread://summary/{run_id}/{phase}`

### Automatic attach

Sometimes `--store` does not exist, but `--host-repo` has a
`.redthread.yaml` marker. The default `--host-repo` is the current
directory. In this case, the first tool call attaches the store
automatically:

- In worktree mode, it always attaches the store.
- In repo mode, it attaches the store only with `--allow-clone`. When
  Redthread clones a URL from a committed file, this is a real security
  boundary.

Thus, the setup on a second machine is short: clone the code repo and
register the same MCP command. If the store already exists on a remote,
you do not run `redthread init` or `attach`. Refer to [Find the store
again on a different machine](#find-the-store-again-on-a-different-machine).

### One registration, many projects (discovery mode)

`--store` binds the server to one store for all of its life.

- This is correct for clients that register MCP servers for each project,
  for example the `.mcp.json` file of Claude Code.
- This is not correct for clients that use one global registration for
  all windows. Examples are `~/.cursor/mcp.json` of Cursor, Windsurf, and
  the user-level `mcp.json` of VS Code. With these clients, one `--store`
  value causes all repos to use the store of the *first* repo.

If you do not give `--store`, the server operates in **discovery mode**.
It finds the store for each call, not for each process.

```bash
redthread mcp-serve
```

For each call, the server finds a workspace. Then it goes up the
directory tree to the nearest `.redthread.yaml` file. It uses the store
that this marker names. The server uses the first workspace that it finds
in this list:

1. The `workspace` argument of `context_bootstrap`. `store_init`,
   `memory_write`, and `agents_md_bootstrap` also accept it. The agent
   gives the absolute path of the project that it has open. The server
   keeps this value for the remaining session. Thus, subsequent calls do
   not have to give it again.
2. The MCP **roots** that the client declares. The server asks for them
   automatically when `context_bootstrap` has no `workspace` argument.
3. `REDTHREAD_WORKSPACE`. Use this for clients that can put a workspace
   variable into the `env` of a server.
4. The directory where the server started (`--host-repo`, default `.`).

If the workspace and its parent directories have no marker, the server
refuses the call. The error message gives the `redthread init` or
`redthread attach` command that corrects the problem. The server never
uses the store of a different project. A fallback of this type causes
the incorrect memory records that this mode prevents.

Thus, each repo that must have memory must have a committed marker.
`redthread init --worktree-repo .` and `redthread attach --host-repo .`
both write and commit a marker.

!!! note "Pinned mode does not change"
    If you give `--store`, the server operates as before. This includes
    the `store.binding` check. This check shows a warning when the store
    does not belong to the workspace. Discovery mode does not remove this
    check, but the warning is not necessary. By design, discovery mode
    always selects the store that the workspace declares.

!!! tip "You do not have to paste AGENTS.md manually"
    After you register the server, tell the agent to call
    `agents_md_bootstrap`. This tool writes the policy from [Make your
    agent use the memory](#make-your-agent-use-the-memory-agentsmd) into
    the `AGENTS.md` (or `CLAUDE.md`) file of the project. The tool is
    idempotent. Thus, the agent can safely call it at the start of each
    session. If the instructions are already in the file, the tool does
    nothing.

### Connect your agent

Select your client. You can paste the text in each tab without changes.

=== "🟠 Claude Code"

    ```bash
    claude mcp add redthread -- uvx redthread mcp-serve --store /path/to/my-store
    ```

    On the first start, `uvx` gets `redthread` from PyPI. Thus, a
    checkout or an install before this step is not necessary.

    If `redthread` is already installed (`pip install redthread` or
    `uv tool install redthread`), remove `uvx`:

    ```bash
    claude mcp add redthread -- redthread mcp-serve --store /path/to/my-store
    ```

    By default, this command registers the server only for the current
    project. To use it in all your projects, add `--scope user`. To write a
    `.mcp.json` file that you can commit and share with your team, add
    `--scope project`.

    To make sure that the server operates, type `/mcp` in Claude Code. The
    `redthread` server shows as connected with 19 tools. For a quick test,
    tell the agent to call `context_bootstrap`.

    To use a source checkout, replace `uvx redthread` with
    `uv run --directory /path/to/checkout redthread`.

=== "⚫ Cursor"

    Cursor does not have a CLI `add` command. It uses a one-click install
    deeplink. This command makes the deeplink and opens it. It uses only
    Python, which Redthread already uses. Thus, you do not install more
    software:

    ```bash
    python -c "
    import base64, json, webbrowser
    config = {'command': 'uvx', 'args': ['redthread', 'mcp-serve', '--store', '/path/to/my-store']}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    webbrowser.open(f'cursor://anysphere.cursor-deeplink/mcp/install?name=redthread&config={encoded}')
    "
    ```

    Cursor shows an install confirmation. Accept it to complete the
    procedure.

    If `redthread` is already installed, replace `'command': 'uvx'` with
    `'command': 'redthread'`. Then remove `redthread` from the start of
    `args`.

    To do the configuration manually, use one of these procedures:

    - Go to Settings → MCP (or *MCP & Integrations*) → *Add Custom MCP*.
    - Edit `.cursor/mcp.json` (for one project, and you can share it).
    - Edit `~/.cursor/mcp.json` (for all projects).

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

    **Do you register the server globally?** Cursor uses one
    `~/.cursor/mcp.json` entry for all project windows. If the entry
    contains a fixed `--store`, the memory of all repos goes to the store
    of the first repo. Thus, remove `--store`. Then the `.redthread.yaml`
    file of each project selects its store:

    ```json
    {
      "mcpServers": {
        "redthread": {
          "command": "uvx",
          "args": ["redthread", "mcp-serve"]
        }
      }
    }
    ```

    Refer to [One registration, many
    projects](#one-registration-many-projects-discovery-mode). This also
    applies to Windsurf and to the user-level `mcp.json` of VS Code.

=== "🔵 VS Code (Copilot)"

    ```bash
    code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","/path/to/my-store"]}'
    ```

    If `redthread` is already installed, remove `uvx`:

    ```bash
    code --add-mcp '{"name":"redthread","command":"redthread","args":["mcp-serve","--store","/path/to/my-store"]}'
    ```

    If you use the Insiders build, use `code-insiders` instead of `code`.

    To do the configuration manually, run **MCP: Add Server** in the
    Command Palette, or make a `.vscode/mcp.json` file. VS Code uses a
    `servers` key with an explicit type. It does not use `mcpServers`:

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

=== "Windsurf"

    Windsurf has no CLI command for this. Edit the configuration directly.
    Go to Settings → Cascade → MCP Servers, or edit
    `~/.codeium/windsurf/mcp_config.json`:

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

=== "Claude Desktop"

    Claude Desktop has no CLI command for this. Go to Settings → Developer
    → Edit Config. This opens `claude_desktop_config.json`. The file is in
    `%APPDATA%\Claude\` on Windows and in
    `~/Library/Application Support/Claude/` on macOS. After you save the
    file, start the app again.

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

=== "Codex CLI"

    Add a TOML table to `~/.codex/config.toml`:

    ```toml
    [mcp_servers.redthread]
    command = "uvx"
    args = ["redthread", "mcp-serve", "--store", "/path/to/my-store"]
    ```

=== "Gemini CLI"

    Add the standard `mcpServers` block to `~/.gemini/settings.json`. For
    one project, use `.gemini/settings.json` in the project:

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

=== "Claude Agent SDK"

    Give the server definition in code:

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

!!! warning "Windows"
    GUI clients do not always get the PATH of your shell. If the server
    does not start, use the absolute path to `uvx.exe` (or to the
    installed `redthread.exe`) as `command`.

### Make your agent use the memory (AGENTS.md)

When you register the server, the agent gets the *capability*. A short
note in the instructions file of your project gives it the *habit*.
Without this note, most agents do not call memory tools if you do not tell
them to.

Add this text to your `AGENTS.md` file (most coding agents read it) or to
`CLAUDE.md`. Change it as necessary:

````markdown
## Memory (Redthread)

The long-term memory of this project is a Redthread store (MCP server
"redthread"). All sessions, machines, and agents that work on this
project use it. Use only this memory for this project.

- At the start of the session, call `context_bootstrap` one time. It
  returns the pipeline, the recent runs, and the memory index of this
  project in one call. Then use `memory_read` to read the entries that
  apply before you make changes.
- Do not record long-term knowledge in other locations. Do not use the
  memory directory of the harness (for example,
  `~/.claude/projects/**/memory/`) or a scratch notes file. Other
  sessions, machines, and agents cannot see these locations.
- After you complete an important task, write a dated summary with
  `memory_write`. Always add a one-line `description`. Use the namespace
  `sessions` and a key like `2026-07-18_short-slug`. Write what changed,
  why, how you validated it, and the remaining work. Write when the task
  is complete, not at the end of the session. Do not wait for the user to
  tell you.
- `memory_write` commits your entry and pushes it in the background. Thus,
  the memory goes to other machines without a second step, and you do not
  wait for the network. Examine the `sync` field that it returns. If it
  shows `failed`, or if a subsequent call shows that a previous push
  failed, correct the problem.
- Put long-term rules and decisions in the `notes` namespace. Do not store
  secrets.
- If the MCP server is not connected, use the CLI on the same store. Do
  not skip memory. Use `redthread bootstrap` and `redthread memory
  list|search|read|write ...`.
````

You can use all namespace names. `sessions` and `notes` are only a
convention that operates well. Use the names that apply to your team.

For a full version of this file that also installs Redthread and registers
the MCP server, refer to the [AGENTS.md example](agents-md.md).

!!! danger "Do not store secrets"
    The memory store is a git repo. Usually, you push it to a shared
    remote. Use the same security rules as for all other repos. If you
    write API keys, tokens, or credentials with `memory_write`, git
    commits them to the history. All persons with access to the store can
    then see them.

## Runs

A run is one full attempt through the pipeline. A ULID identifies each run.

| Command | Effect |
|---|---|
| `redthread run start` | Starts a run and shows its `run_id` |
| `redthread run list` | Shows all run IDs in the store |
| `redthread bootstrap` | Shows the start data: pipeline, recent runs, handoffs, memory index |

```bash
run_id=$(redthread run start --store ./my-store)
redthread bootstrap --store ./my-store   # same payload the MCP context_bootstrap tool returns
```

## Long-term memory (CLI)

Memory is not related to a run. It is the long-term part of the store.

```bash
redthread memory write <namespace> <key> <file> [--description TEXT] [--tags a,b] [--no-push]
redthread memory read <namespace> <key>
redthread memory list [namespace]              # key + description per entry ('*' = uncommitted)
redthread memory search <query> [--namespace NS] [--limit N]
redthread memory import <path> [--namespace NS] [--overwrite] [--no-recursive] [--tags a,b]
```

Redthread keeps `--description` as YAML frontmatter, and `memory list`
shows it. Thus, always give a description. If nobody can identify an
entry from the list, nobody reads it again.

`memory write` commits the store and then pushes it. Thus, the entry is on
the remote immediately after you write it. The command shows one line that
tells which of these steps occurred.

To write many entries and do `redthread sync` only one time at the end,
add `--no-push`. `--no-push` stops only the *push*. Redthread still
commits the entry. A person who skips a push does not want to lose data.

If the push is not successful, Redthread shows a warning, not an error.
The entry is already committed. Thus, the command still exits with code 0.
It tells you to sync after you correct the cause.

`memory list` puts a `*` on an entry that exists only as a file in the
working tree. This mark shows the difference between "written" and
"committed". A list that reads only the working tree cannot show this
difference in a different way.

## Is my memory safe?

```bash
redthread status --store ./my-store
```

This command shows, on one screen, the items that decide if memory stays
safe and goes to other machines:

- The branch, and if it has commits.
- The remote.
- If this store publishes.
- The number of commits that are not pushed.
- Each memory entry that is not committed yet.

### Publishing

A push is a different decision from a commit, because a push has effects
outside your machine:

```bash
redthread publish --store ./my-store              # report the current setting
redthread publish --enable --store ./my-store     # publish memory to the store's remote
redthread publish --disable --store ./my-store    # commit locally, never push
redthread publish --default --store ./my-store    # go back to the default for this store
```

By default, each store publishes. Memory that stays on the machine where
you wrote it is not portable.

!!! warning "Know where a worktree store pushes"
    A **worktree store** uses the remotes of the host repo. Thus, its
    memory goes to the same location as the code of the project. If this
    is a public repository, or a location where memory must not go, run
    `redthread publish --disable`.

Redthread still commits memory locally on each write.
`init --no-publish` sets this value from the start. The setting is in the
`project.yaml` file of the store, so it moves with the store. `publish`,
`status`, and `init` all show the name of the remote that they use.

A push never stops the write that started it:

- Over MCP, the push runs in the background.
- From the CLI, `memory write` gives the push 20 seconds. Then it reports
  `committed` and the next sync does the remaining work.

Redthread records each result on the machine. If a push is not successful
or does not complete, `context_bootstrap` in the next session reports it.
It then publishes the commits that are not pushed in the background.

```bash
redthread memory write notes toolchain.md ./note.md \
  --description "Why this project uses uv, not conda" --tags toolchain --store ./my-store
redthread memory search uv --store ./my-store
```

### Import memory that you already have

Most projects already have memory in a different location when they
start to use Redthread. Usually, it is in the memory directory of a coding
agent. This memory never goes to other machines. `memory import` moves it
into the store with one command. Thus, you do not have to copy and paste
manually:

```bash
# a harness's local memory directory
redthread memory import ~/.claude/projects/my-project/memory \
  --namespace notes --store ./my-store

# a folder of decision records, keeping their structure
redthread memory import ./docs/decisions --namespace decisions --store ./my-store

# a single file
redthread memory import ./NOTES.md --namespace notes --store ./my-store
```

Agents can do the same with the `memory_import` MCP tool. The first time
you connect an agent to a project that has notes, tell it to use this
tool.

The import operates as follows:

- **Each text file becomes one entry.** The key is the path of the file
  in the source directory, without the extension. For example,
  `decisions/db.md` becomes `decisions/db`. Thus, the structure of the
  notes stays the same. Redthread skips hidden files, hidden directories,
  and files that are not text.
- **Redthread copies the content without changes.** Frontmatter in the
  files continues to operate. `memory list` and `memory search` use a
  `description:` or `tags:` block without conversion. For files without
  frontmatter, Redthread uses the first line with content, as usual.
- **The import is a copy, not a move.** The source files stay in their
  location. If an import is not correct, you lose only a namespace.
- **You can safely run the import again.** Redthread skips keys that
  exist. To overwrite them, add `--overwrite`. Redthread always skips a key
  whose content is the same. The command shows one line for each entry
  (`imported` / `skipped (exists)` / `skipped (unchanged)`) and a total.
- **One commit for all entries.** Redthread commits and pushes the full
  import one time, not one time for each entry. `--no-push` stops the
  push. The commit still occurs.
- **A bad file does not stop the import.** If a file cannot be read or is
  not UTF-8, Redthread reports it on stderr and counts it as `failed`.
  Redthread imports all other files.

!!! tip "Examine the files before you import them"
    An import writes many files to a git repo that is usually shared.
    Examine the source directory first. Old notes often contain API keys,
    and you do not want these keys in the store.

## Log context

```bash
redthread log <run_id> <phase> <type> [PAYLOAD_JSON] [--tags a,b]
```

- `type` is one of these values: `metric | decision | code_change |
  artifact_ref | error | milestone | note`.
- `PAYLOAD_JSON` is a raw JSON object string. The default is `{}`.
- Entries do not change, and you can only add them. You cannot edit or
  delete an entry.

```bash
redthread log "$run_id" build decision '{"note": "switched to strategy B"}' --store ./my-store
```

## Artifacts

This command registers a file as a content-addressed artifact pointer.
Redthread makes a sha256 hash and examines it when it reads the artifact.
You can use all `kind` values (`build`, `checkpoint`, `plot`, `docs`,
...).

```bash
redthread artifact add <run_id> <phase> <source_path> <kind> [--artifact-id ID]
```

```bash
redthread artifact add "$run_id" build ./dist/app.bin build --store ./my-store
```

## Read the history

```bash
redthread read <run_id> [--phase PHASE] [--type TYPE]
```

This command shows one JSON entry on each line, in the sequence that
Redthread made them. To read the full history of the run, do not give
`--phase` or `--type`.

```bash
redthread read "$run_id" --store ./my-store --phase build --type decision
```

## Rolling summary

Each phase has one markdown summary file that you can change. The agent
keeps this summary. It is different from the entry log, which does not
change.

```bash
redthread summary set <run_id> <phase> <markdown_file>
redthread summary get <run_id> <phase>
```

## Handoffs — the contract between phases

A phase publishes **one curated handoff**. The subsequent phase reads
*only* this handoff. It does not read the raw entry log.

```bash
redthread handoff publish <run_id> <phase> <handoff_json_file>
redthread handoff get <run_id> <phase>
```

The JSON file must contain at least `headline`. If you do not give
`run_id` and `from_phase`, Redthread uses the values from the command
arguments. This is the full schema:

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

For small files, use `artifact add`. Redthread copies them inline into the
store repo.

For large files (checkpoints, build outputs, datasets), use a **blob
backend**. Git keeps only the pointer. The data is in a content-addressed
directory, and each machine finds this directory independently.

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

`backend set` maps a **logical name** to the mount location of the
target on *this* machine. The store records only the logical name, never
the path. Thus, artifacts stay portable between nodes.

## Sync, resume, and the daemon

The store is a git repo.

- `sync` does one pull-rebase-commit-push cycle.
- `daemon run` does this cycle again at an interval.
- `resume` lets a new machine continue a run after the previous machine
  is not available.

```bash
redthread sync [--message "..."]
redthread daemon run [--interval SECONDS]
redthread resume <run_id> [--remote URL]
```

```bash
redthread sync --store ./my-store
redthread resume "$run_id" --store ./new-clone --remote git@github.com:you/my-store.git
```

If the store is not on the local machine, `resume` clones it. For
this, you must give `--remote`. If the store is on the local machine, `resume` pulls
the latest version. Then it does these steps:

1. It closes the lineage record of the previous node.
2. It opens a new lineage record for this machine.
3. It logs a `milestone` entry.

Thus, the full history shows which machine did which work, and when.

For a worktree-mode store, use `--worktree-repo` instead of `--remote`. A
separate remote URL is not necessary. The remote of the store is the
`origin` of the host (code) repo:

```bash
redthread resume "$run_id" --store ./store-wt \
  --worktree-repo /path/to/your/already-cloned/code-repo --branch redthread-store
```

## Present — report, deck, and docs from handoffs

```bash
redthread present <run_id> <output_dir> [--phase present]
```

This command makes `report.md`, `deck.pptx`, and a `docs/` markdown tree.
It uses the handoff of each upstream phase, in the pipeline sequence from
`project.yaml`. It never uses raw entries. It operates the same for all
names of upstream phases.

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

!!! warning "Windows / PowerShell"
    In PowerShell, inline JSON in a shell argument often has quoting
    problems. Write the JSON to a temporary file and use the commands that
    read files (`handoff publish`, `summary set`). Or call
    `redthread.store.LocalStore` directly from Python.
