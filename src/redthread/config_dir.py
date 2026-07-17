"""Resolves this machine's Redthread config directory.

Honors REDTHREAD_CONFIG_DIR so tests (and anyone running multiple isolated
node identities on one machine) never touch the real per-user config dir.
"""

import os
from pathlib import Path

from platformdirs import user_config_dir


def default_config_dir() -> Path:
    override = os.environ.get("REDTHREAD_CONFIG_DIR")
    return Path(override) if override else Path(user_config_dir("redthread"))
