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
for the trade-off in full). This is the default the
[AGENTS.md example](agents-md.md) sets up, since it needs nothing beyond a
repo you already have.

It needs even less than that on a brand-new project: if `--worktree-repo`
isn't a git repo yet, `init` runs `git init -b main` on it first, so a
project directory you created five minutes ago can host memory without any
git setup of its own.

`init` then finishes the job — it adds the store directory to the host
repo's `.gitignore` (the store is a worktree, not content of the host
branch) and commits `.redthread.yaml` to the branch you're on. That commit
is a pathspec commit touching those two paths only: whatever else you had
staged stays staged and uncommitted. Pass `--no-commit-marker` if you'd
rather stage and commit it yourself. If the commit fails — no configured
git identity, most often — `init` warns and still exits 0, because the
store itself is created and usable.

### Finding the store again on another machine

`--worktree-repo` always writes a small marker, `.redthread.yaml`, into the
host repo recording the mode, path, and branch — and commits it, so a
second machine that just clones the code repo can attach without ever
passing `--worktree-repo`/`--branch` itself:

```bash
redthread attach [--store PATH] [--host-repo PATH] [--allow-clone]
```

`--host-repo` defaults to the current directory. For a plain (non-worktree)
store, pass `--host-repo` to `init` too, so the marker gets written even
though there's no `--worktree-repo` to imply it:

```bash
redthread init demo --phases build,test,present --store ./my-store --host-repo .
```

`attach` also doubles as the way a repo-mode marker's `url` gets filled in
once you've added a remote — run it again after `git remote add origin
...` and it syncs the marker from the store's actual remote, no separate
update command needed. `redthread mcp-serve` reads this marker
automatically too; see [below](#agent-memory-mcp-server). Full mechanics:
[Discovering a store on a fresh machine](architecture.md#discovering-a-store-on-a-fresh-machine-redthreadyaml).

### Adding a phase later

```bash
redthread project add-phase <phase> [--store PATH] [--no-backfill]
```

Appends a new phase to the project's pipeline after the fact. By default
every run that isn't already `done`/`failed` is backfilled with the new
phase as `pending`, so a mid-flight run can log against it immediately;
completed runs keep their original phase-status snapshot untouched. Pass
`--no-backfill` to only affect runs started after the change.

```bash
redthread project add-phase deploy --store ./my-store
```

## Agent memory (MCP server)

```bash
redthread mcp-serve [--store PATH] [--host-repo PATH] [--allow-clone]
redthread mcp-serve   # discovery mode: one registration, every project
```

Runs an MCP server (stdio) exposing the store as 18 tools:
`context_bootstrap` (start here), `store_init`, `run_start`/`run_list`,
`context_log`/`context_read`, `artifact_put`/`artifact_get`,
`summary_update`/`summary_get`, `handoff_publish`/`handoff_get`,
`memory_write`/`memory_read`/`memory_list`/`memory_search`/`memory_import`
for long-term memory not tied to any run, and `agents_md_bootstrap`
(below). Point a coding agent's MCP config at this instead of its local
`.claude`/`.agent` folder — the same memory becomes visible on every
machine that clones the store.

Five conveniences worth knowing before you wire an agent up:

- **`context_bootstrap` is the front door.** One call returns the phase
  pipeline, recent runs and their status, published handoffs, and the full
  memory index with a description per entry — the orientation a cold agent
  would otherwise need four or five calls to assemble, and usually skips.
  `redthread bootstrap --store PATH` prints the same payload for humans.
- **`run_id` is optional on every run-scoped tool.** Omitted, it resolves
  to the store's newest `active` run, and the id it resolved to comes back
  in the response — so an agent is never guessing which run it wrote to.
  Pass it explicitly when several runs are in flight across machines.
- **Memory is self-describing.** Pass a one-line `description` to
  `memory_write` and it's stored as YAML frontmatter; `memory_list` returns
  those descriptions so an agent can tell what's worth opening without
  reading every entry. `memory_search` covers keys, descriptions, tags, and
  bodies.
- **Writing memory publishes it.** `memory_write` commits the entry
  synchronously and pushes in the background, because an agent that has to
  remember a second `sync` call sometimes won't — and unpushed memory is
  invisible to the next machine, which is the point of the store. The call
  returns at local-disk speed with `sync.status: "pushing"` (`committed`
  when the store has no remote, `failed` with a `detail` when the commit
  itself failed); a failed background push is surfaced by the next call on
  the store under `sync.previous`, and the `sync_status` tool reports the
  in-flight state, last push outcome, and unpublished-commit count on
  demand. Pass `push=False` to batch several writes and sync once at the
  end — the entry is committed either way, so declining to publish never
  costs you durability. The CLI runs one-shot processes, so `redthread
  memory write` still pushes synchronously unless you pass `--no-push`.
- **Memory you already have can be ported in.** `memory_import` (or
  `redthread memory import <path>`) turns a file or a directory of notes
  into memory entries — one text file per entry — so a project that arrives
  with memory in a harness's own directory, a `docs/decisions/` folder, or
  another store's `memory/` tree doesn't have to be re-typed. See
  [Porting existing memory in](#porting-existing-memory-in).

The same reads are also exposed as MCP **resources**, for clients that can
attach context without spending a tool call: `redthread://project`,
`redthread://memory`, `redthread://bootstrap`, and the templated
`redthread://memory/{namespace}/{key}`,
`redthread://handoff/{run_id}/{phase}`,
`redthread://summary/{run_id}/{phase}`.

If `--store` doesn't exist yet but `--host-repo` (defaults to the current
directory) has a `.redthread.yaml` marker, the first tool call attaches
the store automatically — worktree mode always, repo mode only with
`--allow-clone` (cloning a URL read from a committed file is a real trust
boundary). This is what makes a second machine's setup just "clone the
code repo, register the same MCP command" — no `redthread init`/`attach`
step required if the store already exists somewhere. See [Finding the
store again on another machine](#finding-the-store-again-on-another-machine).

### One registration, many projects (discovery mode)

`--store` pins the server to one store for its whole life. That is right
for clients that register MCP servers per project (Claude Code's
`.mcp.json`), and wrong for clients that keep a single global registration
and reuse it for every window they open — Cursor's `~/.cursor/mcp.json`,
Windsurf, VS Code's user-level `mcp.json`. There, one `--store` means every
repo talks to the *first* repo's store.

Omit `--store` and the server runs in **discovery mode**: it decides the
store per call instead of per process.

```bash
redthread mcp-serve
```

Each call resolves a workspace, walks up from it to the nearest
`.redthread.yaml`, and serves the store that marker names. The workspace
comes from the first of these that answers:

1. the `workspace` argument on `context_bootstrap` (also accepted by
   `store_init`, `memory_write`, and `agents_md_bootstrap`) — the agent
   passes the absolute path of the project it has open. It sticks for the
   rest of the session, so later calls need not repeat it.
2. the client's declared MCP **roots**, asked for automatically when
   `context_bootstrap` is called without a `workspace`.
3. `REDTHREAD_WORKSPACE`, for clients that can expand a workspace variable
   into a server's `env`.
4. the directory the server was launched in (`--host-repo`, default `.`).

A workspace with no marker in it or any parent is refused, with the
`redthread init` / `redthread attach` command that would fix it — the
server never falls back to some other project's store, because a silent
fallback is exactly the misfiled memory this mode exists to prevent. So
every repo that should have memory needs its marker committed; `redthread
init --worktree-repo .` and `redthread attach --host-repo .` both write and
commit one.

!!! note "Pinned mode is unchanged"
    Passing `--store` keeps the old behaviour exactly, including the
    `store.binding` check that warns when the served store doesn't belong
    to the workspace. Discovery mode makes that warning unnecessary rather
    than replacing it: the store it picks is by construction the one the
    workspace declares.

!!! tip "Skip the manual AGENTS.md paste"
    Once the server is registered, ask the agent to call
    `agents_md_bootstrap` — it writes the same policy shown in [Make your
    agent actually use it](#make-your-agent-actually-use-it-agentsmd)
    straight into this project's `AGENTS.md` (or `CLAUDE.md`) for you.
    It's idempotent, so it's safe to have the agent call it at the start
    of every session — a no-op once the instructions are already there.

### Connect your agent

Pick your client — each tab is ready to paste as-is.

=== "🟠 Claude Code"

    ```bash
    claude mcp add redthread -- uvx redthread mcp-serve --store /path/to/my-store
    ```

    `uvx` fetches `redthread` from PyPI on first launch, so no checkout or
    prior install is needed. Already installed (`pip install redthread` or
    `uv tool install redthread`)? Drop `uvx`:

    ```bash
    claude mcp add redthread -- redthread mcp-serve --store /path/to/my-store
    ```

    By default this registers the server for the current project only. Add
    `--scope user` to make it available in all your projects, or
    `--scope project` to write a `.mcp.json` you can commit and share with
    your team.

    Verify with `/mcp` inside Claude Code — `redthread` should show as
    connected with 18 tools. A quick smoke test is asking the agent to call
    `context_bootstrap`.

    To run from a source checkout instead, replace `uvx redthread` with
    `uv run --directory /path/to/checkout redthread`.

=== "⚫ Cursor"

    Cursor doesn't have a CLI `add` command — the closest equivalent is a
    one-click install deeplink. This generates one and opens it, using only
    Python (already a Redthread dependency, so nothing extra to install):

    ```bash
    python -c "
    import base64, json, webbrowser
    config = {'command': 'uvx', 'args': ['redthread', 'mcp-serve', '--store', '/path/to/my-store']}
    encoded = base64.b64encode(json.dumps(config).encode()).decode()
    webbrowser.open(f'cursor://anysphere.cursor-deeplink/mcp/install?name=redthread&config={encoded}')
    "
    ```

    Cursor opens with an install confirmation — accept it to finish.
    Already have `redthread` installed? Swap `'command': 'uvx'` for
    `'command': 'redthread'` and drop `redthread` from the front of `args`.

    To configure by hand instead: Settings → MCP (or *MCP & Integrations*)
    → *Add Custom MCP*, or edit `.cursor/mcp.json` (project, shareable) /
    `~/.cursor/mcp.json` (all projects):

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

    **Registering globally?** Cursor reuses one `~/.cursor/mcp.json` entry
    for every project window, so a hard-coded `--store` sends every repo's
    memory to the first repo's store. Drop `--store` instead and let each
    project's own `.redthread.yaml` pick its store:

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

    See [One registration, many
    projects](#one-registration-many-projects-discovery-mode). The same
    applies to Windsurf and to VS Code's user-level `mcp.json`.

=== "🔵 VS Code (Copilot)"

    ```bash
    code --add-mcp '{"name":"redthread","command":"uvx","args":["redthread","mcp-serve","--store","/path/to/my-store"]}'
    ```

    Already have `redthread` installed? Drop `uvx`:

    ```bash
    code --add-mcp '{"name":"redthread","command":"redthread","args":["mcp-serve","--store","/path/to/my-store"]}'
    ```

    Use `code-insiders` instead of `code` if you're on the Insiders build.

    To configure by hand instead: run **MCP: Add Server** in the Command
    Palette, or create `.vscode/mcp.json`. VS Code uses a `servers` key
    with an explicit type instead of `mcpServers`:

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

    No CLI equivalent — edit the config directly: Settings → Cascade → MCP
    Servers, or `~/.codeium/windsurf/mcp_config.json`:

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

    No CLI equivalent — Settings → Developer → Edit Config, which opens
    `claude_desktop_config.json` (`%APPDATA%\Claude\` on Windows,
    `~/Library/Application Support/Claude/` on macOS). Restart the app
    after saving.

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

    Add the standard `mcpServers` block to `~/.gemini/settings.json` (or
    `.gemini/settings.json` in the project):

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

    Pass the server definition programmatically:

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
    GUI clients don't always inherit your shell's PATH. If a server fails
    to spawn, use the absolute path to `uvx.exe` (or the installed
    `redthread.exe`) as `command`.

### Make your agent actually use it (AGENTS.md)

Registering the server gives the agent the *capability*; a short note in
your project's instructions file gives it the *habit* — without one, most
agents won't call memory tools unprompted. Add this to your `AGENTS.md`
(read by most coding agents) or `CLAUDE.md` and adjust to taste:

````markdown
## Memory (Redthread)

This project's long-term memory is a Redthread store (MCP server
"redthread") shared by every session, machine, and agent working on it.
It is the only memory that counts here.

- At session start, call `context_bootstrap` once — it returns this
  project's pipeline, recent runs, and the memory index in one call — then
  `memory_read` whatever looks relevant before making changes.
- Never record durable knowledge anywhere else: not in the harness's own
  memory directory (e.g. `~/.claude/projects/**/memory/`), not in a scratch
  notes file. Those are invisible to other sessions, machines, and agents.
- After completing a non-trivial task, write a dated summary with
  `memory_write` (always with a one-line `description`; namespace
  `sessions`, key like `2026-07-18_short-slug`): what changed, why,
  validation done, follow-ups. Write when the task finishes, not batched at
  the end of the session, and without being asked.
- `memory_write` commits your entry and pushes it in the background, so
  memory reaches other machines without a second step and without waiting
  on the network. Check the `sync` field it returns and fix it if it says
  `failed` — or if a later call reports a previous push failed.
- Store durable conventions and decisions under the `notes` namespace;
  never store secrets.
- If the MCP server isn't connected, use the CLI on the same store rather
  than skipping memory: `redthread bootstrap`, `redthread memory
  list|search|read|write ...`.
````

Namespaces are free-form — `sessions` and `notes` are just a convention
that has worked well; pick whatever fits your team. For a self-contained
version of this file that also covers installing Redthread and registering
the MCP server, see the [AGENTS.md example](agents-md.md).

!!! danger "Never store secrets"
    The memory store is a git repo, usually pushed to a shared remote —
    treat it like any other repo. API keys, tokens, and credentials
    written to `memory_write` are committed to history and visible to
    everyone with access to the store.

## Runs

A run is one end-to-end attempt through the pipeline, identified by a ULID.

| Command | Effect |
|---|---|
| `redthread run start` | Start a run; prints its `run_id` |
| `redthread run list` | List all run ids in the store |
| `redthread bootstrap` | Print the orientation payload: pipeline, recent runs, handoffs, memory index |

```bash
run_id=$(redthread run start --store ./my-store)
redthread bootstrap --store ./my-store   # same payload the MCP context_bootstrap tool returns
```

## Long-term memory (CLI)

Memory isn't tied to any run — it's the durable half of the store.

```bash
redthread memory write <namespace> <key> <file> [--description TEXT] [--tags a,b] [--no-push]
redthread memory read <namespace> <key>
redthread memory list [namespace]              # key + description per entry ('*' = uncommitted)
redthread memory search <query> [--namespace NS] [--limit N]
redthread memory import <path> [--namespace NS] [--overwrite] [--no-recursive] [--tags a,b]
```

`--description` is stored as YAML frontmatter and is what `memory list`
shows, so it's worth passing every time — an entry nobody can identify from
a listing is an entry nobody reads again.

`memory write` commits the store and pushes it afterwards, so the entry is
on the remote as soon as it's written, and it prints one line saying which
of those happened. Pass `--no-push` to write several entries and `redthread
sync` once at the end: `--no-push` declines the *push* only — the entry is
still committed, because nobody skipping a push is asking to lose their
data. A failed push is a warning, not an error: the entry is already
committed, so the command still exits 0 and tells you to sync once you've
fixed the cause.

`memory list` marks an entry with `*` when it exists only as a working-tree
file. That is the difference between written and durable, and it is the one
thing a listing that reads the working tree cannot otherwise tell you.

## Is my memory actually safe?

```bash
redthread status --store ./my-store
```

One screen of the things that decide whether memory survives and travels:
the branch (and whether it has any commits at all), the remote, whether
this store publishes, how many commits are unpushed, and any memory entry
that isn't committed yet.

### Publishing

Pushing is a separate decision from committing, because it is the one with
consequences beyond your machine:

```bash
redthread publish --store ./my-store              # report the current setting
redthread publish --enable --store ./my-store     # publish memory to the store's remote
redthread publish --disable --store ./my-store    # commit locally, never push
redthread publish --default --store ./my-store    # go back to the default for this store
```

A store with its own repo publishes by default. A **worktree store does
not**: it shares the host repo's remotes, so an unqualified push would send
memory wherever the project publishes its code — which is often a public
repository nobody chose as a memory destination. Memory is committed
locally on every write, and `redthread publish --enable` turns publishing
on once you've decided that remote should hold it. The setting lives in the
store's `project.yaml`, so it travels with the store.

```bash
redthread memory write notes toolchain.md ./note.md \
  --description "Why this project uses uv, not conda" --tags toolchain --store ./my-store
redthread memory search uv --store ./my-store
```

### Porting existing memory in

Most projects meet Redthread with memory already written somewhere —
usually a coding agent's own memory directory, which is exactly the memory
that never leaves the machine it was written on. `memory import` moves it
into the store in one command, so adopting Redthread doesn't start with an
afternoon of copy-paste:

```bash
# a harness's local memory directory
redthread memory import ~/.claude/projects/my-project/memory \
  --namespace notes --store ./my-store

# a folder of decision records, keeping their structure
redthread memory import ./docs/decisions --namespace decisions --store ./my-store

# a single file
redthread memory import ./NOTES.md --namespace notes --store ./my-store
```

Agents can do the same through the `memory_import` MCP tool — worth asking
for explicitly the first time you point one at a project that has notes
lying around.

How it behaves:

- **One text file, one entry.** The key is the file's path under the source
  with the extension dropped, so `decisions/db.md` becomes `decisions/db`
  and whatever structure the notes had survives. Hidden files and
  directories are skipped, as are non-text extensions.
- **Content is copied verbatim.** Frontmatter the files already had keeps
  working — a `description:` or `tags:` block is picked up by `memory list`
  and `memory search` with no conversion step. Files without frontmatter
  fall back to their first meaningful line, as usual.
- **It's a copy, not a move.** Source files are left exactly where they
  are, so a bad import costs you a namespace and nothing else.
- **Re-running is safe.** Existing keys are skipped rather than
  overwritten unless you pass `--overwrite`, and a key whose content
  already matches is skipped either way. The command prints one line per
  entry (`imported` / `skipped (exists)` / `skipped (unchanged)`) and a
  tally.
- **One commit for the batch.** The whole import is committed and pushed
  once, not once per entry. `--no-push` opts out of the push; the commit
  still happens.
- **A bad file doesn't sink the batch.** Anything unreadable or non-UTF-8
  is reported on stderr and counted as `failed`; everything else still
  lands.

!!! tip "Check what you're importing"
    An import is a bulk write to a git repo that's usually shared. Skim the
    source directory first — old notes are exactly the kind of place a
    stray API key ends up, and the store is not where you want it to land.

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

!!! warning "Windows / PowerShell"
    Passing inline JSON as a shell argument is quoting-fragile in PowerShell.
    Write the JSON to a temp file and use the file-based commands
    (`handoff publish`, `summary set`), or call `redthread.store.LocalStore`
    directly from Python.
