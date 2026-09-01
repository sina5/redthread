"""Every tunable default and well-known name in one place.

If a value is a knob someone might want to find, change, or reason
about, it lives here rather than as a literal in the module that happens to
use it. Modules import from here; a few re-export under their own name where
that reads better at the call site, but this file stays the single definition.

Domain vocabularies (the valid run statuses, entry types, artifact backends)
live here too. They are constants in exactly the same sense, and having to
guess whether a given frozenset lives with its model or with the other
constants is the confusion this module exists to remove.
"""

PACKAGE_NAME = "redthread"

# ----- well-known names on disk ---------------------------------------------

MARKER_FILENAME = ".redthread.yaml"
"""Committed into a host repo to say which store belongs to it."""

DEFAULT_STORE_DIRNAME = "redthread-store"
DEFAULT_STORE_BRANCH = "redthread-store"
"""Orphan branch used when a store lives as a worktree of its host repo."""

NODE_ID_FILE = "node_id"
PATHS_MAP_FILE = "paths.json"
PROJECT_FILENAME = "project.yaml"

GITATTRIBUTES = "* text=auto eol=lf\n*.ndjson merge=union\n"
"""Normalize line endings, and union-merge the append-only logs.

Without `merge=union` two nodes appending entries in the same second produce
a conflict in a file that has no semantic conflict at all.
"""

INIT_COMMIT_MESSAGE = "redthread: initialize store"
"""First commit on a new store's branch.

Made at `init` time so the branch is a real ref from the start: an unborn
branch has no `git log`, is missing from `git branch -a`, and leaves every
file in the store untracked — indistinguishable, by inspection, from a
setup that failed.
"""

MEMORY_DOC_FENCE = "---"
AGENTS_MD_MARKER = "<!-- redthread:agent-instructions -->"

WORKSPACE_ENV_VAR = "REDTHREAD_WORKSPACE"
"""Names the project directory for a globally-registered MCP server.

Clients that keep one MCP registration for every window (Cursor,
Windsurf, VS Code) launch the server with a working directory that says
nothing about which project is open. Where such a client can expand a
workspace variable into a server's `env`, this is the knob that tells
discovery mode where to start looking."""

# ----- git transport --------------------------------------------------------

GIT_TIMEOUT_SECONDS = 60
"""Budget for one git invocation.

Local operations finish in milliseconds, so anything near this is a hang
rather than slow work. Network operations get the same budget deliberately: a
memory store is small, and a remote that cannot answer within a minute is one
the caller should hear about rather than wait on. Clone is the exception —
see the clone settings below.
"""

GIT_REAP_TIMEOUT_SECONDS = 5
"""How long to wait for a killed git process to be collected."""

CLONE_PROGRESS_INTERVAL_SECONDS = 5
"""How often a running clone reports that it is still going.

Clone is the one operation with no wall-clock cap, so it is also the one that
has to say so out loud. Anything faster than this floods the caller; anything
slower and a long clone looks indistinguishable from a hang.
"""

CLONE_STALL_LIMIT_BYTES_PER_SECOND = 1000
CLONE_STALL_LIMIT_SECONDS = 60
"""Git's own stall guard, in place of a wall-clock timeout on clone.

A clone of a big store is legitimately slow, so capping it on elapsed time
punishes the honest case. What is never legitimate is a transfer that has
effectively stopped: these two make git abort itself if throughput stays
under the byte floor for this many seconds. Progress keeps the clone alive
for as long as it takes; a dead socket still fails instead of hanging.
"""

SYNC_MAX_RETRIES = 5
SYNC_RETRY_BACKOFF_SECONDS = 0.5
SYNC_RETRY_BACKOFF_CAP_SECONDS = 5
"""Rebase-and-retry budget when another node pushed first."""

SYNC_DAEMON_INTERVAL_SECONDS = 10.0
"""Poll interval for the auto-commit daemon (architecture target: 5-15s)."""

BACKGROUND_SYNC_DRAIN_SECONDS = 30.0
"""How long process exit waits for in-flight background pushes. Long enough
for a healthy push to finish, short enough that a dead network can't hold
the process hostage — a stranded push costs nothing but latency, since the
commit is local and the next sync from anywhere publishes it."""

# ----- adapters -------------------------------------------------------------

METRIC_BATCH_SIZE = 50
METRIC_BATCH_INTERVAL_SECONDS = 60.0
"""Metrics are buffered and flushed as one entry, to keep git churn down."""

# ----- MCP surface ----------------------------------------------------------

BOOTSTRAP_RECENT_RUNS = 5
BOOTSTRAP_MEMORY_LIMIT = 100
MEMORY_SEARCH_LIMIT = 20

# ----- update check ---------------------------------------------------------

PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"
UPDATE_CHECK_TIMEOUT_SECONDS = 3.0
"""Deliberately short: the check is a courtesy and must never delay startup."""

UPDATE_CHECK_INTERVAL_SECONDS = 60 * 60 * 24
"""Check PyPI at most once a day; the answer changes far more slowly."""

UPDATE_CHECK_CACHE_FILE = "last_update_check.json"

# ----- domain vocabularies --------------------------------------------------

RUN_STATUSES = frozenset({"created", "active", "done", "failed"})
PHASE_STATUSES = frozenset({"pending", "active", "done", "failed"})

# Domain-neutral event vocabulary. "metric" means any measured result:
# val_acc for an ML run, coverage or bundle size for an app build.
ENTRY_TYPES = frozenset(
    {
        "metric",
        "decision",
        "code_change",
        "artifact_ref",
        "error",
        "milestone",
        "note",
    }
)

ARTIFACT_BACKENDS = frozenset({"s3", "minio", "rsync", "gitlfs", "inline"})

TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt", ".mdx", ""})
"""Suffixes `memory import` treats as importable text."""
