"""Ask PyPI, at most once a day, whether a newer redthread is published.

This is a courtesy, never a gate. Every failure path — no network, PyPI down,
a malformed response, an unreadable cache — resolves to "no message" rather
than an error, because a memory server that refuses to start because it could
not reach pypi.org would be far worse than one running a version behind.

The MCP server is the reason this exists: it is long-lived, launched by an
agent client rather than by hand, and its user never sees a release note. It
is also why nothing here may write to stdout — that is the MCP protocol
channel, and a stray line on it corrupts the session.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from redthread import constants
from redthread.config_dir import default_config_dir

DISABLE_ENV_VAR = "REDTHREAD_NO_UPDATE_CHECK"
"""Set to any non-empty value to silence the check entirely.

For air-gapped machines, CI, and the test suite — none of which should be
making an outbound request to pypi.org as a side effect of reading memory.
"""


def _parse_version(text: str) -> tuple[int, ...] | None:
    """Numeric release tuple, or None if this isn't a plain X.Y.Z version.

    Deliberately narrow: anything with a pre-release or local segment returns
    None, which suppresses the notice. Being quiet about an unusual version
    is a much better failure than nagging someone to "upgrade" to something
    that isn't actually newer.
    """
    parts = text.strip().split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def latest_version(package: str = constants.PACKAGE_NAME) -> str | None:
    """The newest stable version on PyPI, or None if it can't be determined."""
    url = constants.PYPI_JSON_URL.format(package=package)
    try:
        with urllib.request.urlopen(  # noqa: S310 - fixed https URL from constants
            url, timeout=constants.UPDATE_CHECK_TIMEOUT_SECONDS
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    version = payload.get("info", {}).get("version")
    return version if isinstance(version, str) else None


def _cache_path() -> Path:
    return default_config_dir() / constants.UPDATE_CHECK_CACHE_FILE


def _checked_recently(cache: Path) -> bool:
    try:
        stamp = json.loads(cache.read_text(encoding="utf-8")).get("checked_at", 0)
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
    return (time.time() - float(stamp)) < constants.UPDATE_CHECK_INTERVAL_SECONDS


def _remember_check(cache: Path) -> None:
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"checked_at": time.time()}), encoding="utf-8")
    except OSError:
        pass  # a cache we can't write just means we check again next time


def update_message(current: str, force: bool = False) -> str | None:
    """ "A newer version exists, here's how to get it" — or None.

    None means every case that isn't an unambiguous upgrade: already current,
    ahead of PyPI (a local dev build), unparseable versions, no network, or
    simply checked too recently. `force` skips only the once-a-day throttle.
    """
    if os.environ.get(DISABLE_ENV_VAR):
        return None
    cache = _cache_path()
    if not force and _checked_recently(cache):
        return None
    _remember_check(cache)

    latest = latest_version()
    if latest is None:
        return None
    have, theirs = _parse_version(current), _parse_version(latest)
    if have is None or theirs is None or theirs <= have:
        return None
    return (
        f"redthread {latest} is available (you have {current}). "
        f"Update with:  uv pip install --upgrade {constants.PACKAGE_NAME}  "
        f"(or:  pip install --upgrade {constants.PACKAGE_NAME} ). "
        f"If you installed it as a tool:  uv tool install --reinstall {constants.PACKAGE_NAME}"
    )
