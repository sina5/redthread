#!/usr/bin/env python3
"""Verify every `uses:` ref in .github/workflows resolves to a real tag/SHA.

Catches "Unable to resolve action X, unable to find version Y" before merge
instead of when the workflow runs. Set GITHUB_TOKEN to avoid API rate limits.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

USES = re.compile(r"^\s*-?\s*uses:\s*['\"]?([^'\"\s#]+)")
WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"


def collect() -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for line in path.read_text().splitlines():
            match = USES.match(line)
            if match and not match.group(1).startswith(("./", "docker://")):
                refs.setdefault(match.group(1), []).append(path.name)
    return refs


def resolves(repo: str, ref: str) -> bool:
    for endpoint in (f"git/ref/tags/{ref}", f"commits/{ref}"):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/{endpoint}",
            headers={"Accept": "application/vnd.github+json"},
        )
        if token := os.environ.get("GITHUB_TOKEN"):
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                json.load(response)
                return True
        except urllib.error.HTTPError as error:
            if error.code not in (404, 422):
                raise
    return False


def main() -> int:
    failures = []
    for uses, files in collect().items():
        owner_repo, _, ref = uses.partition("@")
        repo = "/".join(owner_repo.split("/")[:2])
        if not ref:
            failures.append(f"{uses} ({', '.join(files)}): missing @version")
            continue
        if resolves(repo, ref):
            print(f"ok   {uses}")
        else:
            failures.append(f"{uses} ({', '.join(files)}): version not found")

    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
