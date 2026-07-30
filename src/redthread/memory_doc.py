"""Optional YAML frontmatter on memory entries, so memory is self-describing.

A memory entry is plain text; nothing here is required. But a leading
``---`` block lets ``memory_list`` tell an agent what a key holds without
opening every file, which is the difference between memory that gets read
and memory that rots. Entries written without frontmatter still get a
description: the first meaningful line stands in for one.
"""

from typing import Any

import yaml

_FENCE = "---"


def split(text: str) -> tuple[dict[str, Any], str]:
    """Split leading YAML frontmatter from the body.

    Returns ``({}, text)`` unchanged for anything that isn't a well-formed
    mapping between two ``---`` fences — a body opening with a horizontal
    rule is not frontmatter.
    """
    # keepends so a body's own trailing newline survives the round trip.
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FENCE:
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() != _FENCE:
            continue
        try:
            meta = yaml.safe_load("".join(lines[1:i])) or {}
        except yaml.YAMLError:
            return {}, text
        if not isinstance(meta, dict):
            return {}, text
        return meta, "".join(lines[i + 1 :]).lstrip("\n")
    return {}, text


def with_frontmatter(
    content: str, description: str | None = None, tags: list[str] | None = None
) -> str:
    """Return `content` with `description`/`tags` merged into its frontmatter.

    A no-op when there's nothing to add, so writing an entry without
    metadata never rewrites the caller's bytes.
    """
    if description is None and not tags:
        return content
    meta, body = split(content)
    if description is not None:
        meta["description"] = description
    if tags:
        meta["tags"] = sorted({*meta.get("tags", []), *tags})
    dumped = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{_FENCE}\n{dumped}\n{_FENCE}\n\n{body}"


def tags_of(text: str) -> list[str]:
    """Declared tags, normalized to a list (a bare scalar counts as one tag)."""
    meta, _ = split(text)
    raw = meta.get("tags")
    if isinstance(raw, str):
        return [raw]
    return [str(t) for t in raw] if isinstance(raw, list) else []


def describe(text: str, max_len: int = 160) -> str | None:
    """A one-line summary of an entry: its declared description, or failing
    that the first line that carries meaning (a heading counts)."""
    meta, body = split(text)
    declared = meta.get("description")
    if isinstance(declared, str) and declared.strip():
        return _clip(declared.strip(), max_len)
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith((_FENCE, "```", "<!--")):
            continue
        return _clip(line.lstrip("#").strip() or line, max_len)
    return None


def _clip(value: str, max_len: int) -> str:
    return value if len(value) <= max_len else value[: max_len - 1].rstrip() + "…"
