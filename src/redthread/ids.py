"""Identity primitives: ULIDs for logical identity, a stable per-machine node id.

Logical identity (project/run/entry ids) must never depend on hostnames or
paths. The node id exists only for provenance metadata and is a persisted
random token, deliberately not derived from the hostname.
"""

import secrets
from pathlib import Path

from ulid import ULID

from redthread.config_dir import default_config_dir

_NODE_ID_FILE = "node_id"


def new_ulid() -> str:
    """Mint a new ULID string (lexicographically sortable by creation time)."""
    return str(ULID())


def get_node_id(config_dir: Path | None = None) -> str:
    """Return this machine's stable node id, creating it on first use.

    The id is random, not hostname-derived, so re-imaging or renaming a
    machine changes nothing about identity semantics.
    """
    base = config_dir if config_dir is not None else default_config_dir()
    path = base / _NODE_ID_FILE
    if path.exists():
        node_id = path.read_text(encoding="utf-8").strip()
        if node_id:
            return node_id
    node_id = f"node-{secrets.token_hex(6)}"
    base.mkdir(parents=True, exist_ok=True)
    path.write_text(node_id + "\n", encoding="utf-8")
    return node_id
