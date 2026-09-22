"""Append a content hash to extra_css / extra_javascript URLs.

MkDocs serves these files at fixed, unhashed paths, so after a deploy a
browser can keep applying its cached copy — Safari did exactly that with
stylesheets/extra.css, rendering the front-page terminal demo unstyled.
A ?v=<hash> that changes only when the file changes forces a refetch
without anyone remembering to bump a version.
"""

import hashlib
from pathlib import Path


def _versioned(path: str, docs_dir: Path) -> str:
    source = docs_dir / path.split("?", 1)[0]
    if "?" in path or "://" in path or not source.is_file():
        return path
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
    return f"{path}?v={digest}"


def on_config(config):
    docs_dir = Path(config["docs_dir"])
    config["extra_css"] = [_versioned(p, docs_dir) for p in config["extra_css"]]
    # Plain entries are strings; ones with options (defer, async) are objects.
    scripts = []
    for script in config["extra_javascript"]:
        if isinstance(script, str):
            script = _versioned(script, docs_dir)
        else:
            script.path = _versioned(script.path, docs_dir)
        scripts.append(script)
    config["extra_javascript"] = scripts
    return config
